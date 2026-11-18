import math
import sys
from pathlib import Path
from typing import Any

# Add project root to sys.path so config is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from core.ledger import Ledger

VALID_AREAS = {"venue", "schedule", "food", "judging", "budget"}


def affected_areas(items: list[dict]) -> list[str]:
    """
    Router determining affected areas from extracted items.
    Pure Python lookup according to README §5.
    """
    areas = set()
    for item in items:
        k = item.get("k")
        if k in ("attendance", "team_size"):
            areas.update(VALID_AREAS)
        elif k in ("venue", "venue_need", "venue_unavailable"):
            areas.update(["venue", "budget"])
        elif k in ("event_minutes", "break", "fixed_time"):
            areas.add("schedule")
        elif k in ("food_price", "food_fee", "food_order", "food_need"):
            areas.update(["food", "budget"])
        elif k in ("judges_confirmed", "judge_change", "judge_fee", "judge_minutes", "judge_max_teams", "judge_delay"):
            areas.update(["judging", "schedule", "budget"])
        elif k in ("committed", "budget_total", "proposal", "approve", "cap"):
            areas.add("budget")
        elif k == "rule":
            a = item.get("a")
            if a in VALID_AREAS:
                areas.add(a)
            else:
                areas.update(VALID_AREAS)
    return sorted(list(areas))


def plan(ledger: Ledger) -> dict:
    """
    Deterministic domain engine for event planning.
    Uses active facts only. Arithmetic and constraint validation in pure Python.
    Returns plan dictionary with five areas, checks, unknowns, and assumptions.
    """
    assumptions: list[str] = []
    unknowns: list[str] = []
    checks: list[dict] = []

    # --- 1. Core Counts and Attendance ---
    students_facts = [f for f in ledger.active("attendance") if f.get("name") == "students"]
    students = students_facts[0]["value"] if students_facts and students_facts[0]["value"] is not None else None
    if students is None:
        unknowns.append("Student count is unknown")

    # Team size or stated teams
    team_size_facts = ledger.active("team_size")
    team_size = team_size_facts[0]["value"] if team_size_facts and team_size_facts[0]["value"] is not None else None
    
    teams_facts = [f for f in ledger.active("attendance") if f.get("name") == "teams"]
    stated_teams = teams_facts[0]["value"] if teams_facts and teams_facts[0]["value"] is not None else None

    if stated_teams is not None:
        teams = stated_teams
    elif students is not None and team_size is not None and team_size > 0:
        teams = math.ceil(students / team_size)
    else:
        teams = None
        unknowns.append("Number of teams cannot be determined (missing team size or student count)")

    # Staff count
    staff_facts = [f for f in ledger.active("attendance") if f.get("name") == "staff"]
    if staff_facts and staff_facts[0]["value"] is not None:
        staff = staff_facts[0]["value"]
    else:
        staff = 0
        unknowns.append("Staff count is unknown (assumed 0 for planning)")

    # Judging parameters for headcount
    max_teams_facts = ledger.active("judge_max_teams")
    judge_max_teams = max_teams_facts[0]["value"] if max_teams_facts and max_teams_facts[0]["value"] is not None else None
    if judge_max_teams is None:
        unknowns.append("Maximum teams per judge is unknown")

    judge_min_facts = ledger.active("judge_minutes")
    judge_minutes = judge_min_facts[0]["value"] if judge_min_facts and judge_min_facts[0]["value"] is not None else None
    if judge_minutes is None:
        unknowns.append("Judging minutes per team is unknown")

    judge_fee_facts = ledger.active("judge_fee")
    judge_fee = judge_fee_facts[0]["price"] if judge_fee_facts and judge_fee_facts[0]["price"] is not None else None
    if judge_fee is None:
        unknowns.append("Judge honorarium fee is unknown")

    judges_conf_facts = ledger.active("judges_confirmed")
    judges_confirmed_base = judges_conf_facts[0]["value"] if judges_conf_facts and judges_conf_facts[0]["value"] is not None else None
    if judges_confirmed_base is None:
        unknowns.append("Confirmed judges count is unknown")

    # Compute judges needed
    if teams is not None and judge_max_teams is not None and judge_max_teams > 0:
        judges_needed = math.ceil(teams / judge_max_teams)
    else:
        judges_needed = None

    # Compute total headcount
    if students is not None and judges_needed is not None:
        headcount = students + staff + judges_needed
        assumptions.append(
            f"Headcount = students ({students}) + staff ({staff}) + judges_needed ({judges_needed}) = {headcount}"
        )
    else:
        headcount = None
        unknowns.append("Headcount cannot be computed")

    # --- 2. Venue Planning ---
    venue_options_raw = ledger.active("venue")
    venue_needs = {f["name"].strip().lower() for f in ledger.active("venue_need") if f.get("name")}
    venues_unavail = {f["name"].strip().lower() for f in ledger.active("venue_unavailable") if f.get("name")}

    venue_options = []
    eligible_venues = []

    if not venue_options_raw:
        unknowns.append("No venue options provided")

    for v in venue_options_raw:
        v_name = v.get("name") or "unnamed"
        cap = v.get("value") or 0
        price = v.get("price") or 0
        facs = set(v.get("facilities") or [])

        reasons = []
        is_eligible = True

        if headcount is not None and cap < headcount:
            is_eligible = False
            reasons.append(f"Capacity {cap} < headcount {headcount}")

        if v_name in venues_unavail:
            is_eligible = False
            reasons.append("Marked unavailable")

        missing_facs = [need for need in venue_needs if need not in facs]
        if missing_facs:
            is_eligible = False
            reasons.append(f"Missing required facilities: {', '.join(missing_facs)}")

        status_desc = "Eligible" if is_eligible else f"Ineligible ({'; '.join(reasons)})"
        option_info = {
            "name": v_name,
            "capacity": cap,
            "price": price,
            "facilities": list(facs),
            "eligible": is_eligible,
            "reason": status_desc,
        }
        venue_options.append(option_info)
        if is_eligible:
            eligible_venues.append(option_info)

    chosen_venue = None
    if eligible_venues:
        # Cheapest eligible venue wins
        eligible_venues.sort(key=lambda x: (x["price"], -x["capacity"]))
        chosen_venue = eligible_venues[0]

    venue_plan = {
        "chosen": chosen_venue,
        "options": venue_options,
    }

    # Venue check
    if chosen_venue:
        checks.append({
            "name": "venue fits",
            "status": "pass",
            "detail": f"Chosen {chosen_venue['name']} (cap {chosen_venue['capacity']}) fits headcount {headcount} at PKR {chosen_venue['price']:,}",
        })
    else:
        checks.append({
            "name": "venue fits",
            "status": "fail",
            "detail": "No eligible venue option available that satisfies capacity, availability, and facilities.",
        })

    # --- 3. Food Planning ---
    food_price_facts = ledger.active("food_price")
    food_fees_total = sum(f.get("price") or 0 for f in ledger.active("food_fee"))
    food_orders = ledger.active("food_order")
    superseded_food = [f for f in ledger.get("food_price") if f["status"] == "superseded"]

    if not food_price_facts:
        unknowns.append("No active food options provided")

    food_options = []
    for f in food_price_facts:
        food_options.append({
            "name": f.get("name") or "default",
            "price": f.get("price") or 0,
            "msg_id": f.get("msg_id"),
        })

    # Selection: prefer "standard", else first active
    standard_options = [opt for opt in food_options if "standard" in opt["name"].lower()]
    chosen_food = standard_options[0] if standard_options else (food_options[0] if food_options else None)

    food_cost = 0
    if chosen_food and headcount is not None:
        food_cost = (headcount * chosen_food["price"]) + food_fees_total

    food_plan = {
        "chosen": chosen_food,
        "headcount": headcount,
        "price_per_head": chosen_food["price"] if chosen_food else 0,
        "fees": food_fees_total,
        "cost": food_cost,
        "options": food_options,
        "history": [{"name": f.get("name"), "price": f.get("price"), "date": f.get("date")} for f in superseded_food],
        "notes": [],
    }

    # Check: food covers headcount
    if food_orders:
        latest_order = food_orders[-1].get("value") or 0
        if headcount is not None and latest_order < headcount:
            shortfall = headcount - latest_order
            checks.append({
                "name": "food covers headcount",
                "status": "fail",
                "detail": f"Food order {latest_order} < headcount {headcount} (short by {shortfall}).",
            })
        else:
            checks.append({
                "name": "food covers headcount",
                "status": "pass",
                "detail": f"Food order {latest_order} covers headcount {headcount}.",
            })
    else:
        checks.append({
            "name": "food covers headcount",
            "status": "pass",
            "detail": f"Catering planned for full headcount of {headcount}.",
        })

    # --- 4. Judging Planning ---
    judge_changes = sum(f.get("value") or 0 for f in ledger.active("judge_change"))
    confirmed_judges = (judges_confirmed_base or 0) + judge_changes

    judge_table = []
    if teams is not None and judges_needed is not None and judges_needed > 0:
        # Distribute teams 1..N across judges_needed
        base_teams = teams // judges_needed
        remainder = teams % judges_needed
        team_cursor = 1

        for j_idx in range(1, judges_needed + 1):
            count_for_judge = base_teams + (1 if j_idx <= remainder else 0)
            assigned_teams = list(range(team_cursor, team_cursor + count_for_judge))
            team_cursor += count_for_judge
            judge_mins = count_for_judge * (judge_minutes or 0)
            judge_table.append({
                "judge_id": f"Judge {j_idx}",
                "teams": assigned_teams,
                "team_count": count_for_judge,
                "minutes": judge_mins,
            })

    honorarium_needed = (judges_needed or 0) * (judge_fee or 0)
    honorarium_all_confirmed = confirmed_judges * (judge_fee or 0)

    # Delays and risks
    judge_delays = [f.get("value") or 0 for f in ledger.active("judge_delay")]
    max_delay = max(judge_delays) if judge_delays else 0
    risk_notes = []
    if max_delay > 0:
        risk_notes.append(f"A judge reported a potential delay of up to {max_delay} minutes; added as buffer to judging window.")

    judging_plan = {
        "judges_needed": judges_needed,
        "confirmed": confirmed_judges,
        "judge_max_teams": judge_max_teams,
        "judge_minutes": judge_minutes,
        "honorarium": honorarium_needed,
        "honorarium_all_confirmed": honorarium_all_confirmed,
        "table": judge_table,
        "max_delay": max_delay,
        "risks": risk_notes,
    }

    if judges_needed is not None and confirmed_judges >= judges_needed:
        checks.append({
            "name": "enough judges",
            "status": "pass",
            "detail": f"Confirmed judges ({confirmed_judges}) >= needed ({judges_needed}).",
        })
        if confirmed_judges > judges_needed:
            checks.append({
                "name": "unverified constraint",
                "status": "warn",
                "detail": f"Honorarium planned for {judges_needed} judges (PKR {honorarium_needed:,}); cost would be PKR {honorarium_all_confirmed:,} if all {confirmed_judges} confirmed judges attend.",
            })
    else:
        checks.append({
            "name": "enough judges",
            "status": "fail",
            "detail": f"Not enough judges confirmed: have {confirmed_judges}, need {judges_needed}.",
        })

    # --- 5. Schedule Planning ---
    event_mins_facts = ledger.active("event_minutes")
    event_duration = event_mins_facts[0]["value"] if event_mins_facts and event_mins_facts[0]["value"] is not None else None
    if event_duration is None:
        unknowns.append("Event duration is unknown")

    # Fixed block lengths
    opening_min = config.OPENING_MIN
    lunch_min = config.LUNCH_MIN
    closing_min = config.CLOSING_MIN

    break_facts = ledger.active("break")
    breaks_list = []
    for b in break_facts:
        b_name = b.get("name") or "break"
        b_len = b.get("value") or 0
        breaks_list.append({"name": b_name, "minutes": b_len})

    sum_breaks = sum(b["minutes"] for b in breaks_list)
    judging_window_min = ((judge_max_teams or 0) * (judge_minutes or 0)) + max_delay

    non_build_mins = opening_min + sum_breaks + lunch_min + judging_window_min + closing_min
    schedule_blocks = []
    build_a_min = 0
    build_b_min = 0
    build_total = 0

    if event_duration is not None:
        build_total = event_duration - non_build_mins
        if build_total >= 0:
            build_a_min = math.floor(build_total / 2)
            build_b_min = build_total - build_a_min
        else:
            build_a_min = 0
            build_b_min = 0

    # Build sequence in fixed order
    sequence = [
        {"name": "Opening", "duration": opening_min, "note": "planning default"},
        {"name": "Build A", "duration": build_a_min, "note": "hackathon build phase 1"},
    ]
    for b in breaks_list:
        sequence.append({"name": f"{b['name'].capitalize()} break", "duration": b["minutes"], "note": "required break"})
    sequence.append({"name": "Lunch", "duration": lunch_min, "note": "planning default"})
    sequence.append({"name": "Build B", "duration": build_b_min, "note": "hackathon build phase 2"})
    sequence.append({"name": "Judging", "duration": judging_window_min, "note": f"evaluations ({judging_window_min - max_delay}m + {max_delay}m delay buffer)"})
    sequence.append({"name": "Closing", "duration": closing_min, "note": "planning default"})

    current_offset = 0
    for block in sequence:
        start_off = current_offset
        end_off = current_offset + block["duration"]
        schedule_blocks.append({
            "name": block["name"],
            "duration": block["duration"],
            "start_offset": start_off,
            "end_offset": end_off,
            "note": block["note"],
        })
        current_offset = end_off

    # Schedule validation
    schedule_valid = True
    schedule_detail = ""

    if event_duration is None:
        schedule_valid = False
        schedule_detail = "Event duration unknown."
    elif build_total < 0:
        schedule_valid = False
        schedule_detail = f"Required blocks exceed event duration by {-build_total} minutes."
    elif current_offset != event_duration:
        schedule_valid = False
        schedule_detail = f"Schedule total {current_offset}m != duration {event_duration}m."
    else:
        schedule_detail = f"Valid 4-hour timeline ({event_duration}m total, {build_total}m build split {build_a_min}m/{build_b_min}m)."

    if schedule_valid:
        status_sched = "pass"
        if build_total < 60:
            status_sched = "warn"
            schedule_detail += " Warning: Total build time is under 60 minutes."
        checks.append({
            "name": "schedule valid",
            "status": status_sched,
            "detail": schedule_detail,
        })
    else:
        checks.append({
            "name": "schedule valid",
            "status": "fail",
            "detail": schedule_detail,
        })

    schedule_plan = {
        "duration": event_duration,
        "blocks": schedule_blocks,
        "build_minutes": build_total,
        "build_a": build_a_min,
        "build_b": build_b_min,
        "judging_window": judging_window_min,
    }

    # --- 6. Budget Planning ---
    budget_facts = ledger.active("budget_total")
    budget_total = budget_facts[0]["price"] if budget_facts and budget_facts[0]["price"] is not None else None
    if budget_total is None:
        unknowns.append("Budget total is unknown")

    # Committed items
    committed_facts = ledger.active("committed")
    committed_items = []
    committed_sum = 0
    for c in committed_facts:
        c_name = c.get("name") or "unnamed"
        c_price = c.get("price") or 0
        committed_items.append({"name": c_name, "price": c_price})
        committed_sum += c_price

    # Proposals & Approvals
    proposal_facts = ledger.active("proposal")
    approve_facts = ledger.active("approve")
    approved_labels = {a.get("name").strip().lower() for a in approve_facts if a.get("name")}

    approved_proposals = []
    unapproved_proposals = []
    approved_proposals_sum = 0

    for p in proposal_facts:
        p_name = p.get("name") or "proposal"
        p_price = p.get("price") or 0
        # Approved if approve fact contains proposal name or vice versa
        is_approved = any(app in p_name.lower() or p_name.lower() in app for app in approved_labels)
        if is_approved:
            approved_proposals.append({"name": p_name, "price": p_price})
            approved_proposals_sum += p_price
        else:
            unapproved_proposals.append({"name": p_name, "price": p_price})

    venue_cost = chosen_venue["price"] if chosen_venue else 0
    selected_sum = venue_cost + food_cost + honorarium_needed + approved_proposals_sum
    projected_total = committed_sum + selected_sum
    remaining_budget = (budget_total - projected_total) if budget_total is not None else None

    # Check if budget breaks with standard food, and switch if cheaper food exists
    if budget_total is not None and projected_total > budget_total and len(food_options) > 1:
        cheapest_food = min(food_options, key=lambda x: x["price"])
        if chosen_food and cheapest_food["price"] < chosen_food["price"] and headcount is not None:
            diff = (chosen_food["price"] - cheapest_food["price"]) * headcount
            food_cost_cheapest = (headcount * cheapest_food["price"]) + food_fees_total
            projected_cheapest = committed_sum + venue_cost + food_cost_cheapest + honorarium_needed + approved_proposals_sum
            if projected_cheapest <= budget_total:
                chosen_food = cheapest_food
                food_cost = food_cost_cheapest
                food_plan["chosen"] = chosen_food
                food_plan["cost"] = food_cost
                food_plan["notes"].append("Switched to cheapest food option to stay within budget.")
                selected_sum = venue_cost + food_cost + honorarium_needed + approved_proposals_sum
                projected_total = committed_sum + selected_sum
                remaining_budget = budget_total - projected_total

    # Remaining after each unapproved proposal
    unapproved_with_remaining = []
    for up in unapproved_proposals:
        rem_after = (remaining_budget - up["price"]) if remaining_budget is not None else None
        unapproved_with_remaining.append({
            "name": up["name"],
            "price": up["price"],
            "remaining_after": rem_after,
        })

    # Check spending caps
    cap_facts = ledger.active("cap")
    for cap_f in cap_facts:
        cap_area = (cap_f.get("name") or "").strip().lower()
        cap_limit = cap_f.get("price") or 0
        area_spend = 0
        if cap_area == "food":
            area_spend = food_cost
        elif cap_area == "venue":
            area_spend = venue_cost
        elif cap_area == "judging":
            area_spend = honorarium_needed
        if area_spend > cap_limit:
            checks.append({
                "name": "within budget",
                "status": "fail",
                "detail": f"Spend in area '{cap_area}' (PKR {area_spend:,}) exceeds cap limit of PKR {cap_limit:,}.",
            })

    # Budget Check
    if budget_total is not None:
        if projected_total <= budget_total:
            checks.append({
                "name": "within budget",
                "status": "pass",
                "detail": f"Projected PKR {projected_total:,} is within budget of PKR {budget_total:,} (remaining PKR {remaining_budget:,}).",
            })
        else:
            overrun = projected_total - budget_total
            checks.append({
                "name": "within budget",
                "status": "fail",
                "detail": f"Projected total PKR {projected_total:,} exceeds budget PKR {budget_total:,} by PKR {overrun:,}.",
            })
    else:
        checks.append({
            "name": "within budget",
            "status": "fail",
            "detail": "Budget total is unknown.",
        })

    # --- 7. Additional Mandatory Checks ---
    # Independent recalculation for "correct figures"
    indep_sum = 0
    for c in committed_items:
        indep_sum += c["price"]
    indep_sum += (chosen_venue["price"] if chosen_venue else 0)
    indep_sum += (headcount * chosen_food["price"] + food_fees_total) if (chosen_food and headcount) else 0
    indep_sum += (judges_needed * judge_fee) if (judges_needed and judge_fee) else 0
    for ap in approved_proposals:
        indep_sum += ap["price"]

    if indep_sum == projected_total:
        checks.append({
            "name": "correct figures",
            "status": "pass",
            "detail": f"Independent recalculation matches projected total exactly: PKR {projected_total:,}.",
        })
    else:
        checks.append({
            "name": "correct figures",
            "status": "fail",
            "detail": f"Discrepancy in arithmetic: primary={projected_total}, independent={indep_sum}.",
        })

    # "all areas covered"
    covered = (chosen_venue is not None) and (chosen_food is not None) and (judges_needed is not None) and (len(schedule_blocks) > 0) and (budget_total is not None)
    if covered:
        checks.append({
            "name": "all areas covered",
            "status": "pass",
            "detail": "All five areas (venue, schedule, food, judging, budget) planned and validated.",
        })
    else:
        checks.append({
            "name": "all areas covered",
            "status": "fail",
            "detail": "One or more planning areas are missing required facts.",
        })

    # "evidence present"
    unverified_facts = [f for f in ledger.get() if f["status"] == "unverified"]
    if not unverified_facts:
        checks.append({
            "name": "evidence present",
            "status": "pass",
            "detail": "Every active fact is supported by verified verbatim evidence from messages.",
        })
    else:
        checks.append({
            "name": "evidence present",
            "status": "warn",
            "detail": f"{len(unverified_facts)} fact(s) have unverified evidence quotes.",
        })

    # Unverified constraints for generic 'rule' or 'food_need'
    for r in ledger.active("rule"):
        checks.append({
            "name": "unverified constraint",
            "status": "warn",
            "detail": f"Constraint rule noted: '{r.get('name')}' (area: {r.get('area')}).",
        })
    for fn in ledger.active("food_need"):
        checks.append({
            "name": "unverified constraint",
            "status": "warn",
            "detail": f"Dietary need noted: '{fn.get('name')}' (count: {fn.get('value')}).",
        })

    # Validity determination
    has_failed_check = any(c["status"] == "fail" for c in checks)
    is_valid = (not has_failed_check) and (len(unknowns) == 0)

    budget_plan = {
        "budget_total": budget_total,
        "committed": committed_items,
        "committed_total": committed_sum,
        "venue_cost": venue_cost,
        "food_cost": food_cost,
        "honoraria": honorarium_needed,
        "approved_proposals": approved_proposals,
        "selected_total": selected_sum,
        "projected_total": projected_total,
        "remaining": remaining_budget,
        "unapproved_proposals": unapproved_with_remaining,
    }

    return {
        "assumptions": assumptions,
        "unknowns": unknowns,
        "venue": venue_plan,
        "schedule": schedule_plan,
        "food": food_plan,
        "judging": judging_plan,
        "budget": budget_plan,
        "checks": checks,
        "valid": is_valid,
    }


def try_update(ledger_before: Ledger, candidate_items: list[dict], messages: list[dict]) -> dict:
    """
    Applies candidate items to a COPY of the ledger to evaluate validity.
    Accepts if plan remains valid. Rejects if previously valid plan breaks.
    Never mutates ledger_before.
    """
    plan_before = plan(ledger_before)
    copy_ledger = ledger_before.copy()
    copy_ledger.add_items(candidate_items, messages)
    plan_after = plan(copy_ledger)

    before_valid = plan_before["valid"]
    after_valid = plan_after["valid"]

    # Check for hard food shortfall
    food_check = next((c for c in plan_after["checks"] if c["name"] == "food covers headcount"), None)
    if food_check and food_check["status"] == "fail":
        return {
            "accepted": False,
            "reason": food_check["detail"],
            "violated": "food covers headcount",
            "plan_before": plan_before,
            "plan_after": plan_after,
        }

    if before_valid and not after_valid:
        failed_checks = [c for c in plan_after["checks"] if c["status"] == "fail"]
        viol_name = failed_checks[0]["name"] if failed_checks else "constraint violation"
        viol_detail = failed_checks[0]["detail"] if failed_checks else "Candidate update invalidates plan"
        return {
            "accepted": False,
            "reason": viol_detail,
            "violated": viol_name,
            "plan_before": plan_before,
            "plan_after": plan_after,
        }

    return {
        "accepted": True,
        "reason": "Plan remains valid with candidate update",
        "violated": None,
        "plan_before": plan_before,
        "plan_after": plan_after,
    }


def render_markdown(plan_dict: dict) -> str:
    """
    Renders human-readable markdown with the six core sections.
    """
    lines = []
    lines.append("# OpsWeave Event Plan")
    status_str = "VALID" if plan_dict.get("valid") else "INVALID"
    lines.append(f"**Status**: `{status_str}`\n")

    # Assumptions & Unknowns
    if plan_dict.get("assumptions"):
        lines.append("### Assumptions")
        for a in plan_dict["assumptions"]:
            lines.append(f"- {a}")
        lines.append("")

    if plan_dict.get("unknowns"):
        lines.append("### Unknowns")
        for u in plan_dict["unknowns"]:
            lines.append(f"- ⚠️ {u}")
        lines.append("")

    # 1. Venue
    v = plan_dict.get("venue", {})
    chosen_v = v.get("chosen")
    lines.append("## 1. Venue")
    if chosen_v:
        lines.append(f"- **Selected**: {chosen_v['name'].title()} (Capacity: {chosen_v['capacity']}, Price: PKR {chosen_v['price']:,})")
    else:
        lines.append("- **Selected**: None")
    lines.append("- **Options Evaluated**:")
    for opt in v.get("options", []):
        lines.append(f"  - {opt['name'].title()}: Cap {opt['capacity']}, PKR {opt['price']:,} — {opt['reason']}")
    lines.append("")

    # 2. Schedule
    s = plan_dict.get("schedule", {})
    lines.append("## 2. Schedule")
    lines.append(f"- **Duration**: {s.get('duration', 0)} minutes")
    lines.append("- **Timeline**:")
    for b in s.get("blocks", []):
        lines.append(f"  - `{b['start_offset']:03d}m - {b['end_offset']:03d}m` ({b['duration']:02d}m): **{b['name']}** — *{b['note']}*")
    lines.append("")

    # 3. Food
    f = plan_dict.get("food", {})
    chosen_f = f.get("chosen")
    lines.append("## 3. Food & Catering")
    if chosen_f:
        lines.append(f"- **Option**: {chosen_f['name'].title()} at PKR {chosen_f['price']:,} / head")
        lines.append(f"- **Total Catering Cost**: PKR {f.get('cost', 0):,} (Headcount: {f.get('headcount', 0)}, Delivery/Fees: PKR {f.get('fees', 0):,})")
    lines.append("")

    # 4. Judging
    j = plan_dict.get("judging", {})
    lines.append("## 4. Judging")
    lines.append(f"- **Judges**: {j.get('confirmed', 0)} confirmed, {j.get('judges_needed', 0)} needed")
    lines.append(f"- **Honorarium**: PKR {j.get('honorarium', 0):,} (PKR {j.get('honorarium_all_confirmed', 0):,} if all confirmed attend)")
    if j.get("risks"):
        for r in j["risks"]:
            lines.append(f"- **Risk Note**: {r}")
    lines.append("")

    # 5. Budget
    b = plan_dict.get("budget", {})
    lines.append("## 5. Budget Summary")
    lines.append(f"- **Total Budget**: PKR {b.get('budget_total', 0):,}")
    lines.append(f"- **Committed Costs**: PKR {b.get('committed_total', 0):,}")
    for ci in b.get("committed", []):
        lines.append(f"  - {ci['name'].title()}: PKR {ci['price']:,}")
    lines.append(f"- **Selected Costs**: PKR {b.get('selected_total', 0):,}")
    lines.append(f"  - Venue: PKR {b.get('venue_cost', 0):,}")
    lines.append(f"  - Food: PKR {b.get('food_cost', 0):,}")
    lines.append(f"  - Judging Honoraria: PKR {b.get('honoraria', 0):,}")
    for ap in b.get("approved_proposals", []):
        lines.append(f"  - Approved proposal ({ap['name'].title()}): PKR {ap['price']:,}")
    lines.append(f"- **Projected Total**: PKR {b.get('projected_total', 0):,}")
    lines.append(f"- **Remaining Balance**: PKR {b.get('remaining', 0):,}")
    if b.get("unapproved_proposals"):
        lines.append("- **Optional Proposals (Unapproved)**:")
        for up in b["unapproved_proposals"]:
            lines.append(f"  - {up['name'].title()}: PKR {up['price']:,} (Balance after: PKR {up.get('remaining_after', 0):,})")
    lines.append("")

    # 6. Checks
    lines.append("## 6. Validation Checklist")
    for chk in plan_dict.get("checks", []):
        icon = "✅" if chk["status"] == "pass" else ("⚠️" if chk["status"] == "warn" else "❌")
        lines.append(f"- {icon} **{chk['name'].upper()}**: {chk['detail']}")

    return "\n".join(lines)
