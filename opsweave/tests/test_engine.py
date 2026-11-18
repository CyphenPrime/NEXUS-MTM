from core.ledger import Ledger
from core.engine import plan, affected_areas, try_update, render_markdown


def _create_base_synthetic_ledger() -> tuple[Ledger, list[dict]]:
    """Helper creating a valid base synthetic ledger for unit tests (synthetic test data)."""
    messages = [
        {"id": "M1", "raw": "100 students, teams of 2, 10 staff, 240 mins, 500000 budget", "date": "1 Nov", "order": 1},
        {"id": "M2", "raw": "Hall Alpha cap 150 price 100000", "date": "1 Nov", "order": 2},
        {"id": "M3", "raw": "Standard lunch 1000 per head", "date": "1 Nov", "order": 3},
        {"id": "M4", "raw": "20 judges confirmed, fee 2000, 15 mins per team, max 3 teams", "date": "1 Nov", "order": 4},
        {"id": "M5", "raw": "Committed prizes 50000", "date": "1 Nov", "order": 5},
    ]
    # 100 students / 2 = 50 teams. judges_needed = ceil(50/3) = 17. headcount = 100 + 10 + 17 = 127.
    items = [
        {"k": "attendance", "n": "students", "v": 100, "q": "100 students", "msg_id": "M1"},
        {"k": "team_size", "v": 2, "q": "teams of 2", "msg_id": "M1"},
        {"k": "attendance", "n": "staff", "v": 10, "q": "10 staff", "msg_id": "M1"},
        {"k": "event_minutes", "v": 240, "q": "240 mins", "msg_id": "M1"},
        {"k": "budget_total", "p": 500000, "q": "500000 budget", "msg_id": "M1"},
        {"k": "venue", "n": "hall alpha", "v": 150, "p": 100000, "f": ["generator"], "q": "Hall Alpha cap 150 price 100000", "msg_id": "M2"},
        {"k": "food_price", "n": "standard", "p": 1000, "q": "Standard lunch 1000 per head", "msg_id": "M3"},
        {"k": "judges_confirmed", "v": 20, "q": "20 judges confirmed", "msg_id": "M4"},
        {"k": "judge_fee", "p": 2000, "q": "fee 2000", "msg_id": "M4"},
        {"k": "judge_minutes", "v": 15, "q": "15 mins per team", "msg_id": "M4"},
        {"k": "judge_max_teams", "v": 3, "q": "max 3 teams", "msg_id": "M4"},
        {"k": "committed", "n": "prizes", "p": 50000, "q": "Committed prizes 50000", "msg_id": "M5"},
    ]
    ledger = Ledger()
    ledger.add_items(items, messages)
    return ledger, messages


def test_affected_areas_router():
    # Synthetic test data: test router mapping
    assert affected_areas([{"k": "venue"}]) == ["budget", "venue"]
    assert affected_areas([{"k": "event_minutes"}]) == ["schedule"]
    assert affected_areas([{"k": "attendance"}]) == ["budget", "food", "judging", "schedule", "venue"]
    assert affected_areas([{"k": "committed"}]) == ["budget"]
    assert affected_areas([{"k": "rule", "a": "schedule"}]) == ["schedule"]


def test_venue_too_small_and_missing_facility_and_unavailable():
    # Synthetic test data
    ledger, msgs = _create_base_synthetic_ledger()
    # Add small venue, unavailable venue, and facility requirement
    extra_msgs = [
        {"id": "M6", "raw": "Room Small cap 50 price 20000. Need projector. Hall Alpha unavailable.", "date": "2 Nov", "order": 6}
    ]
    extra_items = [
        {"k": "venue", "n": "room small", "v": 50, "p": 20000, "f": [], "q": "Room Small cap 50 price 20000", "msg_id": "M6"},
        {"k": "venue_need", "n": "projector", "q": "Need projector", "msg_id": "M6"},
        {"k": "venue_unavailable", "n": "hall alpha", "q": "Hall Alpha unavailable", "msg_id": "M6"},
    ]
    ledger.add_items(extra_items, extra_msgs)
    res = plan(ledger)

    # Hall alpha is unavailable and room small is cap 50 < 127
    assert res["valid"] is False
    venue_check = next(c for c in res["checks"] if c["name"] == "venue fits")
    assert venue_check["status"] == "fail"


def test_superseded_price():
    # Synthetic test data: earlier price 1000, later price 1200
    ledger, msgs = _create_base_synthetic_ledger()
    update_msg = [{"id": "M6", "raw": "Standard lunch is now 1200 per head", "date": "5 Nov", "order": 6}]
    update_item = [{"k": "food_price", "n": "standard", "p": 1200, "q": "Standard lunch is now 1200 per head", "msg_id": "M6"}]
    ledger.add_items(update_item, update_msg)
    res = plan(ledger)

    assert res["food"]["price_per_head"] == 1200
    assert len(res["food"]["history"]) == 1
    assert res["food"]["history"][0]["price"] == 1000


def test_order_below_headcount_fails():
    # Synthetic test data: order 100 boxes when headcount is 127
    ledger, msgs = _create_base_synthetic_ledger()
    order_msg = [{"id": "M6", "raw": "Caterer: order rounded down to 100 boxes", "date": "5 Nov", "order": 6}]
    order_item = [{"k": "food_order", "v": 100, "q": "order rounded down to 100 boxes", "msg_id": "M6"}]
    ledger.add_items(order_item, order_msg)
    res = plan(ledger)

    assert res["valid"] is False
    chk = next(c for c in res["checks"] if c["name"] == "food covers headcount")
    assert chk["status"] == "fail"
    assert "short by 27" in chk["detail"]


def test_judge_withdrawal_with_and_without_spares():
    # Synthetic test data: 20 confirmed, 17 needed.
    ledger, msgs = _create_base_synthetic_ledger()
    # Withdrawal of 2 (20 - 2 = 18 >= 17 -> still valid)
    w1_msg = [{"id": "M6", "raw": "Two judges withdrew", "date": "2 Nov", "order": 6}]
    w1_item = [{"k": "judge_change", "v": -2, "q": "Two judges withdrew", "msg_id": "M6"}]
    ledger.add_items(w1_item, w1_msg)
    res1 = plan(ledger)
    assert res1["judging"]["confirmed"] == 18
    assert next(c for c in res1["checks"] if c["name"] == "enough judges")["status"] == "pass"

    # Withdrawal of 3 more (18 - 3 = 15 < 17 -> fails)
    w2_msg = [{"id": "M7", "raw": "Three more judges withdrew", "date": "3 Nov", "order": 7}]
    w2_item = [{"k": "judge_change", "v": -3, "q": "Three more judges withdrew", "msg_id": "M7"}]
    ledger.add_items(w2_item, w2_msg)
    res2 = plan(ledger)
    assert res2["judging"]["confirmed"] == 15
    assert next(c for c in res2["checks"] if c["name"] == "enough judges")["status"] == "fail"


def test_late_judge_is_not_cancellation():
    # Synthetic test data: judge delay adds buffer, does not decrement confirmed count
    ledger, msgs = _create_base_synthetic_ledger()
    delay_msg = [{"id": "M6", "raw": "Judge running 10 minutes late due to traffic", "date": "2 Nov", "order": 6}]
    delay_item = [{"k": "judge_delay", "v": 10, "q": "10 minutes late", "msg_id": "M6"}]
    ledger.add_items(delay_item, delay_msg)
    res = plan(ledger)

    assert res["judging"]["confirmed"] == 20
    assert res["judging"]["max_delay"] == 10
    # Judging window should be 3 * 15 + 10 = 55 min
    assert res["schedule"]["judging_window"] == 55


def test_proposal_and_approve_lifecycle():
    # Synthetic test data: unapproved proposal stays outside, approval moves inside
    ledger, msgs = _create_base_synthetic_ledger()
    p_msg = [{"id": "M6", "raw": "Quote for DJ Rs 30000", "date": "2 Nov", "order": 6}]
    p_item = [{"k": "proposal", "n": "dj", "p": 30000, "q": "DJ Rs 30000", "msg_id": "M6"}]
    ledger.add_items(p_item, p_msg)
    res = plan(ledger)

    assert len(res["budget"]["unapproved_proposals"]) == 1
    assert len(res["budget"]["approved_proposals"]) == 0
    old_proj = res["budget"]["projected_total"]

    # Now approve proposal
    app_msg = [{"id": "M7", "raw": "Dean approved the DJ", "date": "3 Nov", "order": 7}]
    app_item = [{"k": "approve", "n": "dj", "q": "approved the DJ", "msg_id": "M7"}]
    ledger.add_items(app_item, app_msg)
    res2 = plan(ledger)

    assert len(res2["budget"]["unapproved_proposals"]) == 0
    assert len(res2["budget"]["approved_proposals"]) == 1
    assert res2["budget"]["projected_total"] == old_proj + 30000


def test_cap_violation_and_over_budget():
    # Synthetic test data: budget overrun and area cap breach
    ledger, msgs = _create_base_synthetic_ledger()
    over_msg = [{"id": "M6", "raw": "Cap on food Rs 50000. Big order Rs 400000.", "date": "2 Nov", "order": 6}]
    over_items = [
        {"k": "cap", "n": "food", "p": 50000, "q": "Cap on food Rs 50000", "msg_id": "M6"},
        {"k": "committed", "n": "extra", "p": 400000, "q": "Big order Rs 400000", "msg_id": "M6"},
    ]
    ledger.add_items(over_items, over_msg)
    res = plan(ledger)

    assert res["valid"] is False
    chk = next(c for c in res["checks"] if c["name"] == "within budget")
    assert chk["status"] == "fail"


def test_try_update_accepts_valid_and_rejects_invalid():
    # Synthetic test data: verify try_update behavior
    ledger, msgs = _create_base_synthetic_ledger()
    plan_orig = plan(ledger)
    assert plan_orig["valid"] is True

    # 1. Valid price change update
    cand_valid = [{"k": "committed", "n": "printing", "p": 15000, "q": "Printing is 15000", "msg_id": "M6"}]
    res_valid = try_update(ledger, cand_valid, [{"id": "M6", "raw": "Printing is 15000", "date": "2 Nov", "order": 6}])
    assert res_valid["accepted"] is True
    assert res_valid["plan_after"]["valid"] is True

    # 2. Invalid update: food order below headcount
    cand_invalid = [{"k": "food_order", "v": 50, "q": "50 boxes ordered", "msg_id": "M7"}]
    res_invalid = try_update(ledger, cand_invalid, [{"id": "M7", "raw": "50 boxes ordered", "date": "3 Nov", "order": 7}])
    assert res_invalid["accepted"] is False
    assert res_invalid["violated"] == "food covers headcount"
    assert "short by" in res_invalid["reason"]


def test_unverified_rule_produces_warning():
    # Synthetic test data: generic rule yields warn-level check
    ledger, msgs = _create_base_synthetic_ledger()
    rule_msg = [{"id": "M6", "raw": "Participants must wear ID badges at all times", "date": "2 Nov", "order": 6}]
    rule_item = [{"k": "rule", "n": "Wear ID badges", "a": "venue", "q": "wear ID badges", "msg_id": "M6"}]
    ledger.add_items(rule_item, rule_msg)
    res = plan(ledger)

    warn_chks = [c for c in res["checks"] if c["name"] == "unverified constraint"]
    assert any("Wear ID badges" in c["detail"] for c in warn_chks)


def test_render_markdown():
    # Synthetic test data: check markdown rendering includes sections
    ledger, msgs = _create_base_synthetic_ledger()
    res = plan(ledger)
    md = render_markdown(res)
    assert "## 1. Venue" in md
    assert "## 2. Schedule" in md
    assert "## 3. Food & Catering" in md
    assert "## 4. Judging" in md
    assert "## 5. Budget Summary" in md
    assert "## 6. Validation Checklist" in md
