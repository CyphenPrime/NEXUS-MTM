import os
import sys
import threading
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from core.pipeline import run
from core.store import load_state, save_outputs
from core.trace import Trace

_active_trace = None


def _timeout_handler(timeout_seconds: int):
    """Watchdog handler triggered if run exceeds hard timeout."""
    sys.stderr.write(f"\n[FATAL TIMEOUT] Execution exceeded hard cut-off of {timeout_seconds} seconds. Aborting.\n")
    if _active_trace:
        try:
            save_outputs({}, _active_trace, [], [], _active_trace.render_text())
        except Exception:
            pass
    # Exit code 2 for watchdog kill
    os._exit(2)


def print_compact_summary(plan: dict):
    """Prints a clear compact summary of the five plan areas and checklist."""
    print("\n" + "=" * 70)
    print("OPSWEAVE EVENT PLAN SUMMARY")
    print("=" * 70)

    # 1. Venue & Headcount
    v = plan.get("venue", {}).get("chosen")
    v_str = f"{v['name'].title()} (Cap {v['capacity']}, PKR {v['price']:,})" if v else "None"
    f = plan.get("food", {})
    hc = f.get("headcount", "Unknown")
    print(f"VENUE    : {v_str}")
    print(f"HEADCOUNT: {hc} attendees")

    # 2. Food
    f_opt = f.get("chosen")
    f_str = f"{f_opt['name'].title()} @ PKR {f_opt['price']:,}/head (Total PKR {f.get('cost', 0):,})" if f_opt else "None"
    print(f"FOOD     : {f_str}")

    # 3. Judging
    j = plan.get("judging", {})
    print(
        f"JUDGING  : {j.get('judges_needed', 0)} needed ({j.get('confirmed', 0)} confirmed) | "
        f"Honorarium: PKR {j.get('honorarium', 0):,}"
    )

    # 4. Budget
    b = plan.get("budget", {})
    b_tot = b.get("budget_total", 0)
    b_comm = b.get("committed_total", 0)
    b_sel = b.get("selected_total", 0)
    b_proj = b.get("projected_total", 0)
    b_rem = b.get("remaining", 0)
    print(
        f"BUDGET   : PKR {b_tot:,} Total | Committed: PKR {b_comm:,} | Selected: PKR {b_sel:,} | "
        f"Projected: PKR {b_proj:,} | Remaining: PKR {b_rem:,}"
    )

    # 5. Schedule Table
    s = plan.get("schedule", {})
    print("\nSCHEDULE TIMELINE:")
    for blk in s.get("blocks", []):
        print(f"  [{blk['start_offset']:03d}m - {blk['end_offset']:03d}m] ({blk['duration']:02d}m) {blk['name']} ({blk['note']})")

    # 6. Checks
    print("\nVALIDATION CHECKLIST:")
    for chk in plan.get("checks", []):
        status_label = chk["status"].upper()
        icon = "[PASS]" if status_label == "PASS" else ("[WARN]" if status_label == "WARN" else "[FAIL]")
        print(f"  {icon:<6} {chk['name']:<22} : {chk['detail']}")

    overall = "VALID" if plan.get("valid") else "INVALID"
    print(f"\nOVERALL STATUS: {overall}")
    print("=" * 70)


def main():
    global _active_trace

    # Determine timeout depending on expected mode
    saved = load_state()
    timeout_s = config.UPDATE_TIMEOUT_S if saved else config.FULL_RUN_TIMEOUT_S

    watchdog = threading.Timer(timeout_s, _timeout_handler, args=[timeout_s])
    watchdog.daemon = True
    watchdog.start()

    try:
        messages_path = Path(__file__).resolve().parent / "data" / "messages.txt"
        res = run(str(messages_path))
        watchdog.cancel()

        trace = res["trace"]
        _active_trace = trace
        plan = res["plan"]
        rejected = res.get("rejected", [])

        # (a) Model calls part of the trace
        calls_text = trace.render_calls_text()
        if calls_text:
            print(calls_text)

        # (b) SYSTEM EVENT lines
        events_text = trace.render_events_text()
        if events_text:
            print(events_text)

        # (c) Compact plan summary
        print_compact_summary(plan)

        # (d) Rejected messages if any
        if rejected:
            print("\n" + "=" * 70)
            print("REJECTED MESSAGES")
            print("=" * 70)
            for r in rejected:
                print(f"- Message {r.get('message_id')}: {r.get('reason')} (Previous plan retained)")
                print(f"  Raw text: {r.get('text')}")
            print("=" * 70)

        # (e) The VERY LAST line must be TOTAL TOKENS
        print(trace.totals_line())
        return 0

    except Exception as e:
        watchdog.cancel()
        sys.stderr.write(f"\n[FATAL ERROR] {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
