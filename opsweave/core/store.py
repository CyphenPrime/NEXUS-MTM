import json
from pathlib import Path
from core.engine import render_markdown


def load_state(path: str = "data/state.json") -> dict | None:
    """
    Loads saved state from JSON file. Returns None if file does not exist or is invalid.
    """
    state_file = Path(path)
    if not state_file.exists():
        return None
    try:
        content = state_file.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def save_state(state: dict, path: str = "data/state.json"):
    """
    Saves state to JSON file, creating parent directory if necessary.
    """
    state_file = Path(path)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def save_outputs(
    plan: dict,
    trace,
    rejected: list[dict],
    history: list[dict],
    trace_text: str,
    output_dir: str = "outputs"
):
    """
    Writes persistent output artifacts into outputs/:
    - plan.json
    - plan.md
    - trace.json
    - rejected.json
    - final_submission.txt (plan markdown + rejected messages + full trace text)
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. plan.json
    (out_path / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    # 2. plan.md & plan.txt
    plan_md = render_markdown(plan)
    (out_path / "plan.md").write_text(plan_md, encoding="utf-8")
    (out_path / "plan.txt").write_text(plan_md, encoding="utf-8")

    # 3. trace.json & trace.txt
    trace_data = trace.to_dict() if hasattr(trace, "to_dict") else trace
    (out_path / "trace.json").write_text(json.dumps(trace_data, indent=2), encoding="utf-8")
    (out_path / "trace.txt").write_text(trace_text, encoding="utf-8")

    # 4. rejected.json
    (out_path / "rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")

    # 5. final_submission.txt
    sub_lines = []
    sub_lines.append(plan_md)
    sub_lines.append("\n" + "=" * 60)
    sub_lines.append("REJECTED MESSAGES")
    sub_lines.append("=" * 60)
    if rejected:
        for r in rejected:
            sub_lines.append(f"- Message {r.get('message_id')}: {r.get('reason')} (Previous plan retained)")
            sub_lines.append(f"  Exact raw: {r.get('text')}")
    else:
        sub_lines.append("None. All messages accepted or informational.")
    sub_lines.append("\n" + "=" * 60)
    sub_lines.append("EXECUTION TRACE")
    sub_lines.append("=" * 60)
    sub_lines.append(trace_text)

    (out_path / "final_submission.txt").write_text("\n".join(sub_lines), encoding="utf-8")
