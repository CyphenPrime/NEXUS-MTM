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
    """Prints a clear compact summary of the five plan areas covering all requirements."""
    print("\n" + "=" * 70)
    print("OPSWEAVE EVENT PLAN (THE ANSWER)")
    print("=" * 70)

    # 1. Venue: which hall, its seats and its cost
    v = plan.get("venue", {}).get("chosen")
    if v:
        v_str = f"{v['name'].title()} | Seats: {v['capacity']} | Cost: Rs {v['price']:,}"
    else:
        v_str = "None (No eligible venue found)"
    print(f"Venue   : {v_str}")

    # 2. Schedule: the timeline, including the prayer break and judging
    s = plan.get("schedule", {})
    print(f"Schedule: {s.get('duration', 0)} min total timeline")
    for blk in s.get("blocks", []):
        print(f"  - [{blk['start_offset']:03d}m - {blk['end_offset']:03d}m] ({blk['duration']:02d}m) {blk['name']} ({blk['note']})")

    # 3. Food: box type, quantity and cost
    f = plan.get("food", {})
    f_opt = f.get("chosen")
    if f_opt:
        qty = f.get("order_quantity") or f.get("headcount")
        f_str = f"Type: {f_opt['name'].title()} | Quantity: {qty} boxes | Cost: Rs {f.get('cost', 0):,} (at Rs {f_opt['price']:,}/head + Rs {f.get('fees', 0):,} delivery)"
    else:
        f_str = "None"
    print(f"Food    : {f_str}")

    # 4. Judging: number of judges and their cost
    j = plan.get("judging", {})
    j_count = j.get("judges_needed", 0)
    j_cost = j.get("honorarium", 0)
    print(f"Judging : Number of Judges: {j_count} needed ({j.get('confirmed', 0)} confirmed) | Cost: Rs {j_cost:,}")

    # 5. Budget: the total against Rs 400,000, and whether it fits
    b = plan.get("budget", {})
    b_tot = b.get("budget_total", 0)
    b_proj = b.get("projected_total", 0)
    b_fits = "FITS" if (b_tot is not None and b_proj <= b_tot) else "DOES NOT FIT"
    print(f"Budget  : Total Projected: Rs {b_proj:,} against Budget: Rs {b_tot:,} -> Status: {b_fits}")

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
