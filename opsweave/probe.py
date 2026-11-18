import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.reader import read_messages
from core.llm import call_model
from core.ledger import build_prompt_for_reading, parse_reading_output, Ledger, ParseError
from core.trace import Trace


def run_probe():
    messages_path = Path(__file__).resolve().parent / "data" / "messages.txt"
    messages = read_messages(str(messages_path))
    trace = Trace()

    sys_prompt, user_prompt = build_prompt_for_reading(messages)

    # First attempt call
    call_dict = call_model(area="reading", system=sys_prompt, user=user_prompt)
    trace.add_call(call_dict)

    items = []
    successful_output = None

    if call_dict["status"] == "success":
        try:
            items = parse_reading_output(call_dict["output"])
            successful_output = call_dict["output"]
        except ParseError as pe:
            trace.add_event(f"ParseError on first call: {pe}. Retrying once...")
            # Retry ONCE as a separate recorded call
            retry_dict = call_model(area="reading", system=sys_prompt, user=user_prompt)
            trace.add_call(retry_dict)
            if retry_dict["status"] == "success":
                items = parse_reading_output(retry_dict["output"])
                successful_output = retry_dict["output"]
            else:
                trace.add_event(f"Retry call failed with error: {retry_dict['error']}")
    else:
        trace.add_event(f"Initial model call failed: {call_dict['error']}")

    ledger = Ledger()
    if items:
        ledger.add_items(items, messages)

    # Print Table of Active Facts
    print("\n" + "=" * 95)
    print(f"{'FID':<5} | {'KIND':<18} | {'NAME':<15} | {'VAL':<6} | {'PRICE':<8} | {'MSG':<4} | {'STATUS':<10} | {'EVIDENCE'}")
    print("=" * 95)
    for f in ledger.active():
        name_str = str(f['name']) if f['name'] is not None else ""
        val_str = str(f['value']) if f['value'] is not None else ""
        price_str = str(f['price']) if f['price'] is not None else ""
        print(
            f"{f['fid']:<5} | {f['kind']:<18} | {name_str:<15} | {val_str:<6} | {price_str:<8} | "
            f"{f['msg_id']:<4} | {f['status']:<10} | {f['evidence'][:30]}"
        )
    print("=" * 95)

    # Print full execution trace
    print("\n--- EXECUTION TRACE ---")
    print(trace.render_text())
    print("-----------------------\n")

    # Save real output to tests/fixtures/sample_reading_output.json
    if successful_output:
        fixtures_dir = Path(__file__).resolve().parent / "tests" / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture_file = fixtures_dir / "sample_reading_output.json"
        
        # Save prettified JSON for clean inspection
        try:
            parsed = json.loads(successful_output)
            fixture_file.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        except Exception:
            fixture_file.write_text(successful_output, encoding="utf-8")
            
        print(f"Saved real model response to: {fixture_file}")

    return 0 if items else 1


if __name__ == "__main__":
    sys.exit(run_probe())
