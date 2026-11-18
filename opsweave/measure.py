import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "data" / "state.json"
TRACE_FILE = BASE_DIR / "outputs" / "trace.json"


def run_measure():
    """
    Deletes data/state.json, executes main.py with hard 120s kill,
    measures runtime and provider tokens from outputs/trace.json.
    """
    if STATE_FILE.exists():
        STATE_FILE.unlink()

    start_time = time.perf_counter()
    finished_in_time = False

    try:
        proc = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        elapsed = round(time.perf_counter() - start_time, 2)
        finished_in_time = (proc.returncode == 0) and (elapsed <= 120)
    except subprocess.TimeoutExpired:
        elapsed = round(time.perf_counter() - start_time, 2)
        print(f"FAILED: Timed out after {elapsed}s (> 120s)")
        return None

    if not TRACE_FILE.exists():
        print("FAILED: outputs/trace.json not found")
        return None

    try:
        trace_data = json.loads(TRACE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"FAILED: Could not parse trace.json: {e}")
        return None

    calls = trace_data.get("calls", [])
    num_calls = len(calls)
    in_tok = sum(c.get("input_tokens") or 0 for c in calls)
    out_tok = sum(c.get("output_tokens") or 0 for c in calls)
    th_tok = sum(c.get("thinking_tokens") or 0 for c in calls)
    tot_tok = sum(c.get("total_tokens") or 0 for c in calls)

    print("=" * 60)
    print("MEASURE.PY BENCHMARK REPORT")
    print("=" * 60)
    print(f"Finished in time: {'yes' if finished_in_time else 'no'}")
    print(f"Seconds         : {elapsed} s")
    print(f"Model calls     : {num_calls}")
    print(f"Input tokens    : {in_tok}")
    print(f"Output tokens   : {out_tok}")
    print(f"Thinking tokens : {th_tok if th_tok > 0 else 'none'}")
    print(f"Total tokens    : {tot_tok}")
    print("=" * 60)

    return {
        "finished_in_time": finished_in_time,
        "seconds": elapsed,
        "calls": num_calls,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "thinking_tokens": th_tok,
        "total_tokens": tot_tok,
    }


if __name__ == "__main__":
    run_measure()
