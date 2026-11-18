import sys
from pathlib import Path

# Add project root to sys.path so modules are discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reader import read_messages
from core.llm import call_model
from core.ledger import build_prompt_for_reading, parse_reading_output, Ledger, ParseError
from core.trace import Trace
from core.store import load_state, save_state, save_outputs
import core.engine as engine


def run(path: str = "data/messages.txt", llm_fn=call_model) -> dict:
    """
    Unified pipeline executing full runs, prefix updates, and unchanged states.
    All logic strictly coordinates reader, LLM, ledger, engine, and store.
    """
    messages = read_messages(path)
    current_hashes = [m["hash"] for m in messages]
    saved_state = load_state()

    # 1. Mode determination
    mode = "full"
    if saved_state and "message_hashes" in saved_state:
        saved_hashes = saved_state["message_hashes"]
        if current_hashes == saved_hashes:
            mode = "unchanged"
        elif len(current_hashes) > len(saved_hashes) and current_hashes[:len(saved_hashes)] == saved_hashes:
            mode = "update"
        else:
            mode = "full"

    # --- MODE: UNCHANGED ---
    if mode == "unchanged":
        trace = Trace.from_dict(saved_state["last_trace"])
        trace.add_event("No new messages. Existing plan and trace retained.")
        plan_dict = saved_state["last_plan"]
        rejected = saved_state.get("rejected", [])
        history = saved_state.get("update_history", [])

        # Refresh outputs
        save_outputs(plan_dict, trace, rejected, history, trace.render_text())
        return {
            "mode": mode,
            "plan": plan_dict,
            "trace": trace,
            "rejected": rejected,
            "update_history": history,
        }

    # --- MODE: FULL RUN ---
    if mode == "full":
        trace = Trace()
        rejected = []
        update_history = []

        sys_prompt, user_prompt = build_prompt_for_reading(messages)
        call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
        trace.add_call(call_res)

        if call_res["status"] == "error":
            trace.add_event(f"Reading call error: {call_res['error']}. Retrying once...")
            call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
            trace.add_call(call_res)
            if call_res["status"] == "error":
                raise RuntimeError(f"Model call failed: {call_res['error']}")

        try:
            items = parse_reading_output(call_res["output"])
        except ParseError as pe:
            trace.add_event(f"Parse error: {pe}. Retrying once...")
            call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
            trace.add_call(call_res)
            items = parse_reading_output(call_res["output"])

        ledger = Ledger()
        ledger.add_items(items, messages)
        plan_dict = engine.plan(ledger)

        # Log full-run system events
        for f in ledger.get():
            if f["status"] == "superseded":
                trace.add_event(f"Fact {f['fid']} ({f['kind']}:{f['name'] or ''} PKR {f.get('price') or ''}) superseded by newer information.")
            elif f["status"] == "informational":
                trace.add_event(f"Message {f['msg_id']} marked informational: {f.get('reason', 'irrelevant')}.")
            elif f["status"] == "unverified":
                trace.add_event(f"Fact {f['fid']} quote '{f['evidence']}' unverified against message {f['msg_id']}.")

        for a in plan_dict.get("assumptions", []):
            trace.add_event(f"Assumption: {a}")

        if plan_dict["venue"]["chosen"]:
            chosen = plan_dict["venue"]["chosen"]
            trace.add_event(f"Venue choice: {chosen['name'].title()} selected (cap {chosen['capacity']}, PKR {chosen['price']:,}).")

        for chk in plan_dict.get("checks", []):
            trace.add_event(f"Check {chk['name']}: {chk['status'].upper()} — {chk['detail']}")

        # Save state and outputs
        new_state = {
            "message_hashes": current_hashes,
            "ledger": ledger.to_dict(),
            "rejected": rejected,
            "last_plan": plan_dict,
            "last_trace": trace.to_dict(),
            "update_history": update_history,
        }
        save_state(new_state)
        save_outputs(plan_dict, trace, rejected, update_history, trace.render_text())
        return {
            "mode": mode,
            "plan": plan_dict,
            "trace": trace,
            "rejected": rejected,
            "update_history": update_history,
        }

    # --- MODE: UPDATE ---
    # mode == "update"
    trace = Trace.from_dict(saved_state["last_trace"])
    ledger = Ledger.from_dict(saved_state["ledger"])
    current_plan = saved_state["last_plan"]
    rejected = saved_state.get("rejected", [])
    update_history = saved_state.get("update_history", [])

    prev_hashes = saved_state["message_hashes"]
    new_messages = messages[len(prev_hashes):]

    # Compact active-keys line
    active_keys = [f"{f['kind']}:{f['name']}" for f in ledger.active() if f.get("name")]
    active_keys_compact = sorted(list(set(active_keys)))[:15]

    sys_prompt, user_prompt = build_prompt_for_reading(new_messages, active_keys=active_keys_compact)
    call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
    trace.add_call(call_res)

    if call_res["status"] == "error":
        trace.add_event(f"Update reading call error: {call_res['error']}. Retrying once...")
        call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
        trace.add_call(call_res)
        if call_res["status"] == "error":
            raise RuntimeError(f"Update model call failed: {call_res['error']}")

    try:
        items = parse_reading_output(call_res["output"])
    except ParseError as pe:
        trace.add_event(f"Update parse error: {pe}. Retrying once...")
        call_res = llm_fn(area="reading", system=sys_prompt, user=user_prompt)
        trace.add_call(call_res)
        items = parse_reading_output(call_res["output"])

    # Process new messages one by one
    for new_msg in new_messages:
        msg_id = new_msg["id"]
        msg_items = [it for it in items if it["msg_id"] == msg_id]
        if not msg_items:
            continue

        update_eval = engine.try_update(ledger, msg_items, [new_msg])

        if update_eval["accepted"]:
            ledger.add_items(msg_items, [new_msg])
            current_plan = engine.plan(ledger)
            aff = engine.affected_areas(msg_items)
            all_areas = sorted(list(engine.VALID_AREAS))
            not_recomputed = [a for a in all_areas if a not in aff]

            trace.add_event(f"Message {msg_id} accepted. Affected areas: {', '.join(aff)}.")
            trace.add_event(f"Areas not recomputed: {', '.join(not_recomputed)} (no model call needed; Python recalculation only).")
            for it in msg_items:
                trace.add_event(f"Updated fact {it.get('k')}:{it.get('n') or ''} value={it.get('v')} price={it.get('p')}.")
            update_history.append({"message_id": msg_id, "accepted": True, "affected": aff})
        else:
            rej_record = {
                "message_id": msg_id,
                "text": new_msg["raw"],
                "reason": update_eval["reason"],
                "violated_check": update_eval["violated"],
                "affected_area": engine.affected_areas(msg_items),
                "previous_plan_retained": True,
            }
            rejected.append(rej_record)
            trace.add_event(f"Message {msg_id} rejected — {update_eval['reason']}. Previous valid plan retained.")
            update_history.append({"message_id": msg_id, "accepted": False, "reason": update_eval["reason"]})

    # Assert update makes <= 5 model calls
    saved_calls_count = len(saved_state["last_trace"].get("calls", []))
    update_calls_made = len(trace.calls) - saved_calls_count
    assert update_calls_made <= 5, f"Update made {update_calls_made} model calls, exceeding max limit of 5!"

    # Save state and outputs
    new_state = {
        "message_hashes": current_hashes,
        "ledger": ledger.to_dict(),
        "rejected": rejected,
        "last_plan": current_plan,
        "last_trace": trace.to_dict(),
        "update_history": update_history,
    }
    save_state(new_state)
    save_outputs(current_plan, trace, rejected, update_history, trace.render_text())

    return {
        "mode": mode,
        "plan": current_plan,
        "trace": trace,
        "rejected": rejected,
        "update_history": update_history,
    }
