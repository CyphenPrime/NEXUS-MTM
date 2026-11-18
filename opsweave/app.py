import json
import os
import subprocess
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

# Page Configuration
st.set_page_config(
    page_title="OpsWeave — Event Planner",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
MESSAGES_FILE = BASE_DIR / "data" / "messages.txt"
STATE_FILE = BASE_DIR / "data" / "state.json"
PLAN_FILE = BASE_DIR / "outputs" / "plan.json"
TRACE_FILE = BASE_DIR / "outputs" / "trace.json"
REJECTED_FILE = BASE_DIR / "outputs" / "rejected.json"
SUBMISSION_FILE = BASE_DIR / "outputs" / "final_submission.txt"


def run_pipeline():
    """Executes the exact same entrypoint as the judges via subprocess."""
    with st.spinner("Processing event messages through main.py..."):
        res = subprocess.run(
            [sys.executable, "main.py"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
        )
    if res.returncode == 0:
        st.sidebar.success("Pipeline executed successfully!")
    else:
        st.sidebar.error(f"Pipeline returned exit code {res.returncode}")
    if res.stdout:
        last_lines = "\n".join(res.stdout.strip().splitlines()[-4:])
        st.sidebar.caption("Last output:\n" + last_lines)
    st.rerun()


# --- SIDEBAR ---
st.sidebar.title("OpsWeave Control")
st.sidebar.caption("Deterministic Event Planning Agent")

# 1. File Uploader
uploaded_pack = st.sidebar.file_uploader("Upload .txt Message Pack", type=["txt"])
if uploaded_pack:
    if st.sidebar.button("Load Uploaded Pack", use_container_width=True):
        MESSAGES_FILE.write_bytes(uploaded_pack.getvalue())
        run_pipeline()

# 2. Run / Reprocess Button
if st.sidebar.button("Run / Reprocess", type="primary", use_container_width=True):
    run_pipeline()

# 3. Send New Message
st.sidebar.markdown("---")
new_msg = st.sidebar.text_area(
    "Send new message",
    placeholder='e.g. 9 | Finance, email | 16 Nov | "The printing bill came in at Rs 15,000"',
    height=80,
)
if st.sidebar.button("Send Message", use_container_width=True):
    if new_msg.strip():
        curr_text = MESSAGES_FILE.read_text(encoding="utf-8") if MESSAGES_FILE.exists() else ""
        sep = "\n\n" if curr_text and not curr_text.endswith("\n\n") else ""
        MESSAGES_FILE.write_text(curr_text + sep + new_msg.strip() + "\n", encoding="utf-8")
        run_pipeline()

# 4. Downloads
st.sidebar.markdown("---")
if SUBMISSION_FILE.exists():
    st.sidebar.download_button(
        "Download final_submission.txt",
        SUBMISSION_FILE.read_bytes(),
        file_name="final_submission.txt",
        mime="text/plain",
        use_container_width=True,
    )
if TRACE_FILE.exists():
    st.sidebar.download_button(
        "Download trace.json",
        TRACE_FILE.read_bytes(),
        file_name="trace.json",
        mime="application/json",
        use_container_width=True,
    )

st.sidebar.caption(f"Workspace: `{BASE_DIR.name}`\nData: `{MESSAGES_FILE.name}`")

# --- LOAD DATA ---
if not (PLAN_FILE.exists() and TRACE_FILE.exists()):
    st.info("Run the pipeline first (sidebar: Run / Reprocess)")
    st.stop()

try:
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    trace = json.loads(TRACE_FILE.read_text(encoding="utf-8"))
    rejected = json.loads(REJECTED_FILE.read_text(encoding="utf-8")) if REJECTED_FILE.exists() else []
    state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
except Exception as e:
    st.error(f"Error loading pipeline artifacts: {e}")
    st.stop()

# --- TOP KPI STRIP ---
calls_list = trace.get("calls", [])
total_calls = len(calls_list)
total_in = sum(c.get("input_tokens") or 0 for c in calls_list)
total_out = sum(c.get("output_tokens") or 0 for c in calls_list)
grand_total_tokens = sum(c.get("total_tokens") or 0 for c in calls_list)

b = plan.get("budget", {})
v = plan.get("venue", {}).get("chosen")
f = plan.get("food", {})
j = plan.get("judging", {})
is_valid = plan.get("valid", False)

kpi1, kpi2, kpi3, kpi4, kpi5, kpi6, kpi7, kpi8, kpi9 = st.columns(9)
kpi1.metric("Status", "VALID" if is_valid else "INVALID", delta="All checks pass" if is_valid else "Violations", delta_color="normal" if is_valid else "inverse")
kpi2.metric("Budget", f"PKR {b.get('budget_total', 0):,}")
kpi3.metric("Projected", f"PKR {b.get('projected_total', 0):,}")
kpi4.metric("Remaining", f"PKR {b.get('remaining', 0):,}")
kpi5.metric("Venue", v.get("name", "None").title() if v else "None")
kpi6.metric("Headcount", f.get("headcount", 0))
kpi7.metric("Judges", f"{j.get('judges_needed', 0)} / {j.get('confirmed', 0)}")
kpi8.metric("Model Calls", total_calls)
kpi9.metric("Total Tokens", f"{grand_total_tokens:,}")

st.markdown("---")

# --- TABS ---
tab_plan, tab_trace, tab_rejected = st.tabs(["📋 Plan", "🔍 Trace", "🚫 Rejected & Changes"])

# --- TAB 1: PLAN ---
with tab_plan:
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("1. Venue")
        if v:
            st.success(f"**Selected:** {v['name'].title()} (Cap: {v['capacity']}, PKR {v['price']:,})")
        else:
            st.error("No eligible venue selected.")
        v_opts = plan.get("venue", {}).get("options", [])
        if v_opts:
            df_v = pd.DataFrame([{
                "Venue": opt["name"].title(),
                "Capacity": opt["capacity"],
                "Price (PKR)": f"{opt['price']:,}",
                "Eligible": "Yes" if opt["eligible"] else "No",
                "Reason": opt["reason"],
            } for opt in v_opts])
            st.dataframe(df_v, use_container_width=True, hide_index=True)

        st.subheader("2. Schedule")
        s = plan.get("schedule", {})
        st.caption(f"Duration: {s.get('duration', 0)} min | Build: {s.get('build_minutes', 0)} min (Split: {s.get('build_a', 0)}m / {s.get('build_b', 0)}m)")
        s_blocks = s.get("blocks", [])
        if s_blocks:
            df_s = pd.DataFrame([{
                "Time Window": f"{b['start_offset']:03d}m - {b['end_offset']:03d}m",
                "Duration": f"{b['duration']} min",
                "Block Name": b["name"],
                "Note": b["note"],
            } for b in s_blocks])
            st.dataframe(df_s, use_container_width=True, hide_index=True)

        st.subheader("3. Food & Catering")
        f_opt = f.get("chosen")
        if f_opt:
            st.info(f"**Option:** {f_opt['name'].title()} @ PKR {f_opt['price']:,}/head | Total: PKR {f.get('cost', 0):,} (Fees: PKR {f.get('fees', 0):,})")
        f_hist = f.get("history", [])
        if f_hist:
            st.caption("Price History (Superseded Quotes):")
            st.dataframe(pd.DataFrame(f_hist), use_container_width=True, hide_index=True)

    with col_r:
        st.subheader("4. Judging")
        st.write(f"- **Judges Needed:** {j.get('judges_needed', 0)} | **Confirmed:** {j.get('confirmed', 0)}")
        st.write(f"- **Honorarium (Needed):** PKR {j.get('honorarium', 0):,} *(PKR {j.get('honorarium_all_confirmed', 0):,} if all confirmed attend)*")
        if j.get("risks"):
            for rk in j["risks"]:
                st.warning(rk)
        j_tbl = j.get("table", [])
        if j_tbl:
            with st.expander("Judge Assignments Table", expanded=False):
                st.dataframe(pd.DataFrame([{
                    "Judge": row["judge_id"],
                    "Teams": str(row["teams"]),
                    "Count": row["team_count"],
                    "Minutes": f"{row['minutes']}m",
                } for row in j_tbl]), use_container_width=True, hide_index=True)

        st.subheader("5. Budget Summary")
        b_df = pd.DataFrame([
            {"Area": "Committed (Pre-ordered)", "Cost (PKR)": f"{b.get('committed_total', 0):,}"},
            {"Area": "Venue", "Cost (PKR)": f"{b.get('venue_cost', 0):,}"},
            {"Area": "Food & Catering", "Cost (PKR)": f"{b.get('food_cost', 0):,}"},
            {"Area": "Judging Honoraria", "Cost (PKR)": f"{b.get('honoraria', 0):,}"},
            {"Area": "Approved Proposals", "Cost (PKR)": f"{sum(ap.get('price', 0) for ap in b.get('approved_proposals', [])):,}"},
            {"Area": "PROJECTED TOTAL", "Cost (PKR)": f"{b.get('projected_total', 0):,}"},
            {"Area": "REMAINING BALANCE", "Cost (PKR)": f"{b.get('remaining', 0):,}"},
        ])
        st.dataframe(b_df, use_container_width=True, hide_index=True)

        unapp = b.get("unapproved_proposals", [])
        if unapp:
            st.caption("Optional Proposals (Not Approved):")
            st.dataframe(pd.DataFrame([{
                "Proposal": u["name"].title(),
                "Quote (PKR)": f"{u['price']:,}",
                "Balance If Approved": f"PKR {u.get('remaining_after', 0):,}",
            } for u in unapp]), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("6. Verification Checklist & Assumptions")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**Checklist**")
        for chk in plan.get("checks", []):
            st_icon = "✅" if chk["status"] == "pass" else ("⚠️" if chk["status"] == "warn" else "❌")
            st.write(f"{st_icon} **{chk['name'].upper()}**: {chk['detail']}")
    with col_c2:
        st.markdown("**Assumptions & Unknowns**")
        for asm in plan.get("assumptions", []):
            st.write(f"• *Assumption*: {asm}")
        for unk in plan.get("unknowns", []):
            st.warning(f"Unknown: {unk}")

    # Evidence Expander
    facts_raw = state.get("ledger", {}).get("facts", [])
    if facts_raw:
        with st.expander("Evidence Trail (Active Facts from Messages)", expanded=False):
            st.dataframe(pd.DataFrame([{
                "FID": fc["fid"],
                "Kind": fc["kind"],
                "Name": fc.get("name") or "",
                "Msg": fc["msg_id"],
                "Date": fc.get("date") or "",
                "Verbatim Quote": fc.get("evidence", ""),
                "Status": fc["status"],
            } for fc in facts_raw if fc["status"] == "active"]), use_container_width=True, hide_index=True)

# --- TAB 2: TRACE ---
with tab_trace:
    st.subheader("Truthful Execution Trace")
    st.markdown(f"### **TOTAL TOKENS: Input={total_in:,} | Output={total_out:,} | Total={grand_total_tokens:,}**")

    st.markdown("#### Model Calls")
    for call in calls_list:
        c_num = call.get("call_number", 1)
        with st.expander(f"CALL #{c_num} | Model: {call.get('model')} | Area: {call.get('area')} | Time: {call.get('seconds')}s | Status: {call.get('status')}", expanded=False):
            st.caption(f"Tokens: input={call.get('input_tokens')} output={call.get('output_tokens')} thinking={call.get('thinking_tokens')} total={call.get('total_tokens')}")
            st.markdown("**INPUT:**")
            st.code(call.get("input", ""), language="text")
            st.markdown("**OUTPUT:**")
            st.code(call.get("output", ""), language="json")

    st.markdown("#### System Events")
    entries = trace.get("entries", [])
    sys_events = [e["text"] for e in entries if e.get("type") == "event"]
    if sys_events:
        for ev in sys_events:
            st.text(f"SYSTEM EVENT: {ev}")
    else:
        st.caption("No system events recorded.")

# --- TAB 3: REJECTED & CHANGES ---
with tab_rejected:
    st.subheader("Rejected Messages")
    if rejected:
        for rj in rejected:
            st.error(
                f"**Message {rj.get('message_id')} REJECTED**\n\n"
                f"- **Reason**: {rj.get('reason')}\n"
                f"- **Rule Violated**: `{rj.get('violated_check')}`\n"
                f"- **Affected Area**: `{rj.get('affected_area')}`\n"
                f"- **Previous Plan Retained**: Yes\n\n"
                f"```text\n{rj.get('text')}\n```"
            )
    else:
        st.success("No rejected messages. All incoming messages satisfied constraints.")

    st.markdown("---")
    st.subheader("Superseded Facts")
    facts_all = state.get("ledger", {}).get("facts", [])
    sup_facts = [fc for fc in facts_all if fc.get("status") == "superseded"]
    if sup_facts:
        st.dataframe(pd.DataFrame([{
            "FID": fc["fid"],
            "Kind": fc["kind"],
            "Name": fc.get("name") or "",
            "Value": fc.get("value") or "",
            "Price": f"PKR {fc['price']:,}" if fc.get("price") else "",
            "Msg ID": fc["msg_id"],
            "Date": fc.get("date") or "",
            "Evidence": fc.get("evidence", ""),
        } for fc in sup_facts]), use_container_width=True, hide_index=True)
    else:
        st.caption("No facts have been superseded yet.")

    st.markdown("---")
    st.subheader("Incremental Update History")
    hist = state.get("update_history", [])
    if hist:
        st.dataframe(pd.DataFrame(hist), use_container_width=True, hide_index=True)
    else:
        st.caption("Initial full run. No incremental updates performed yet.")
