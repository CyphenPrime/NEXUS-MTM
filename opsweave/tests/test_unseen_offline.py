from core.ledger import Ledger
from core.engine import plan, try_update


def _get_base_ledger() -> tuple[Ledger, list[dict]]:
    """Helper creating a valid base ledger (synthetic test data, offline)."""
    messages = [
        {"id": "M1", "raw": "150 students, teams of 3, 10 staff, 240m event, Rs 650000 budget, 15m prayer break", "date": "1 Nov", "order": 1},
        {"id": "M2", "raw": "Hall Alpha seats 200 at Rs 120000 with wifi and ramps. Hall Beta seats 200 at Rs 150000 with wifi.", "date": "1 Nov", "order": 2},
        {"id": "M3", "raw": "Standard lunch Rs 1200 per head", "date": "1 Nov", "order": 3},
        {"id": "M4", "raw": "20 judges confirmed, fee Rs 5000, 15 mins per team, max 3 teams", "date": "1 Nov", "order": 4},
        {"id": "M5", "raw": "Committed prizes Rs 100000", "date": "1 Nov", "order": 5},
    ]
    items = [
        {"k": "attendance", "n": "students", "v": 150, "q": "150 students", "msg_id": "M1"},
        {"k": "team_size", "v": 3, "q": "teams of 3", "msg_id": "M1"},
        {"k": "attendance", "n": "staff", "v": 10, "q": "10 staff", "msg_id": "M1"},
        {"k": "event_minutes", "v": 240, "q": "240m event", "msg_id": "M1"},
        {"k": "budget_total", "p": 650000, "q": "Rs 650000 budget", "msg_id": "M1"},
        {"k": "break", "n": "prayer", "v": 15, "q": "15m prayer break", "msg_id": "M1"},
        {"k": "venue", "n": "hall alpha", "v": 200, "p": 120000, "f": ["wifi", "ramps"], "q": "Hall Alpha seats 200 at Rs 120000", "msg_id": "M2"},
        {"k": "venue", "n": "hall beta", "v": 200, "p": 150000, "f": ["wifi"], "q": "Hall Beta seats 200 at Rs 150000", "msg_id": "M2"},
        {"k": "food_price", "n": "standard", "p": 1200, "q": "Standard lunch Rs 1200 per head", "msg_id": "M3"},
        {"k": "judges_confirmed", "v": 20, "q": "20 judges confirmed", "msg_id": "M4"},
        {"k": "judge_fee", "p": 5000, "q": "fee Rs 5000", "msg_id": "M4"},
        {"k": "judge_minutes", "v": 15, "q": "15 mins per team", "msg_id": "M4"},
        {"k": "judge_max_teams", "v": 3, "q": "max 3 teams", "msg_id": "M4"},
        {"k": "committed", "n": "prizes", "p": 100000, "q": "prizes Rs 100000", "msg_id": "M5"},
    ]
    ledger = Ledger()
    ledger.add_items(items, messages)
    return ledger, messages


def test_scenario_1_venue_unavailable():
    # Synthetic test data, offline: Hall Alpha unavailable -> switches to Hall Beta (Rs 150,000)
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Hall Alpha has suffered a power outage and is unavailable.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "venue_unavailable", "n": "hall alpha", "q": "Hall Alpha has suffered a power outage and is unavailable", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["valid"] is True
    assert res["plan_after"]["venue"]["chosen"]["name"] == "hall beta"


def test_scenario_2_new_mandatory_facility():
    # Synthetic test data, offline: Require ramps -> Hall Alpha has ramps (valid); if ramps required and no venue has it -> invalid
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Mandatory accessibility: venue must have ramps.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "venue_need", "n": "ramps", "q": "venue must have ramps", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["venue"]["chosen"]["name"] == "hall alpha"


def test_scenario_3_delivery_fee_added():
    # Synthetic test data, offline: Caterer adds Rs 5,000 delivery fee
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Delivery fee Rs 5000 added.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "food_fee", "n": "delivery", "p": 5000, "q": "Delivery fee Rs 5000", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["valid"] is True
    assert res["plan_after"]["food"]["fees"] == 5000


def test_scenario_4_judge_withdrawing_with_spares():
    # Synthetic test data, offline: 20 confirmed, 17 needed. 2 withdraw -> 18 confirmed >= 17 (valid)
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Two judges had an emergency and withdrew.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "judge_change", "v": -2, "q": "Two judges had an emergency and withdrew", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["valid"] is True
    assert res["plan_after"]["judging"]["confirmed"] == 18


def test_scenario_5_judge_withdrawing_without_spares_rejected():
    # Synthetic test data, offline: 5 judges withdraw -> 15 confirmed < 17 needed (must be rejected)
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Five judges withdrew due to weather.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "judge_change", "v": -5, "q": "Five judges withdrew", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is False
    assert res["violated"] == "enough judges"
    assert "need 17" in res["reason"]


def test_scenario_6_budget_cut_breaks_plan_rejected():
    # Synthetic test data, offline: Budget cut from 650000 to 300000 when plan costs 517400
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Budget cut: total budget is now Rs 300000.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "budget_total", "p": 300000, "q": "total budget is now Rs 300000", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is False
    assert res["violated"] == "within budget"
    assert "exceeds budget" in res["reason"]


def test_scenario_7_second_required_break():
    # Synthetic test data, offline: Add 10-minute tea break
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Please include a 10-minute tea break.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "break", "n": "tea break", "v": 10, "q": "10-minute tea break", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["valid"] is True
    sched_names = [b["name"].lower() for b in res["plan_after"]["schedule"]["blocks"]]
    assert any("tea break" in name for name in sched_names)


def test_scenario_8_proposal_approval_inside_and_exceeding_budget():
    # Synthetic test data, offline:
    ledger, msgs = _get_base_ledger()
    # 1. Proposal inside budget (Rs 40,000) -> approved and accepted
    p1_msg = [
        {"id": "M6", "raw": "Photographer quote Rs 40000.", "date": "5 Nov", "order": 6},
        {"id": "M7", "raw": "Dean approves photographer.", "date": "6 Nov", "order": 7},
    ]
    p1_items = [
        {"k": "proposal", "n": "photographer", "p": 40000, "q": "Photographer quote Rs 40000", "msg_id": "M6"},
        {"k": "approve", "n": "photographer", "q": "approves photographer", "msg_id": "M7"},
    ]
    res1 = try_update(ledger, p1_items, p1_msg)
    assert res1["accepted"] is True
    assert res1["plan_after"]["valid"] is True

    # 2. Proposal exceeding budget (Rs 500,000) -> approved but rejected due to budget overrun
    p2_msg = [
        {"id": "M8", "raw": "Drone show quote Rs 500000.", "date": "7 Nov", "order": 8},
        {"id": "M9", "raw": "Approved drone show.", "date": "8 Nov", "order": 9},
    ]
    p2_items = [
        {"k": "proposal", "n": "drone", "p": 500000, "q": "Drone show quote Rs 500000", "msg_id": "M8"},
        {"k": "approve", "n": "drone", "q": "Approved drone show", "msg_id": "M9"},
    ]
    res2 = try_update(ledger, p2_items, p2_msg)
    assert res2["accepted"] is False
    assert res2["violated"] == "within budget"


def test_scenario_9_irrelevant_message():
    # Synthetic test data, offline: Message marked irrelevant (r=0)
    ledger, msgs = _get_base_ledger()
    cand_msg = [{"id": "M6", "raw": "Weather report: heavy rain expected tomorrow.", "date": "5 Nov", "order": 6}]
    cand_items = [{"k": "informational", "n": "irrelevant", "reason": "irrelevant to event", "msg_id": "M6", "q": ""}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is True
    assert res["plan_after"]["valid"] is True


def test_scenario_10_plausible_wrong_judge_cap():
    # Synthetic test data, offline: Message claims judges can evaluate 6 teams (rule is max 3)
    # If accepted it would break judge cap rule; or if candidate attempts to increase judge_max_teams above limit
    ledger, msgs = _get_base_ledger()
    # If message claims only 5 judges needed because each covers 10 teams
    cand_msg = [{"id": "M6", "raw": "Judges can cover 6 teams each, so we only need 8 judges.", "date": "5 Nov", "order": 6}]
    # Stating judges confirmed = 8 (when 17 needed)
    cand_items = [{"k": "judges_confirmed", "v": 8, "q": "only need 8 judges", "msg_id": "M6"}]

    res = try_update(ledger, cand_items, cand_msg)
    assert res["accepted"] is False
    assert res["violated"] == "enough judges"
