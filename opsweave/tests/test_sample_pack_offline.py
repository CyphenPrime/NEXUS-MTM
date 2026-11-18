import json
from pathlib import Path
from core.reader import read_messages
from core.ledger import parse_reading_output, Ledger
from core.engine import plan, try_update


def test_sample_pack_offline_matches_expected():
    """
    Offline test: uses saved real model output (tests/fixtures/sample_reading_output.json)
    and verifies full compliance with README §11 expected fixture values.
    """
    base_dir = Path(__file__).resolve().parent.parent
    messages_path = base_dir / "data" / "messages.txt"
    fixture_path = base_dir / "tests" / "fixtures" / "sample_reading_output.json"
    expected_path = base_dir / "tests" / "fixtures" / "sample_expected.json"

    messages = read_messages(str(messages_path))
    raw_fixture = fixture_path.read_text(encoding="utf-8")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    items = parse_reading_output(raw_fixture)
    ledger = Ledger()
    ledger.add_items(items, messages)

    plan_result = plan(ledger)

    # 1. Validation status
    assert plan_result["valid"] is True

    # 2. Counts & Headcount
    # 150 students + 10 staff + 17 judges needed = 177
    assert plan_result["food"]["headcount"] == expected["headcount"]
    assert plan_result["judging"]["judges_needed"] == expected["judging"]["judges_needed"]
    assert plan_result["judging"]["confirmed"] == expected["judging"]["confirmed"]

    # 3. Venue
    chosen_venue = plan_result["venue"]["chosen"]
    assert chosen_venue["name"].lower() == expected["venue"]["name"]
    assert chosen_venue["capacity"] == expected["venue"]["capacity"]
    assert chosen_venue["price"] == expected["venue"]["price"]

    # 4. Food
    assert plan_result["food"]["price_per_head"] == expected["food"]["price_per_head"]
    assert plan_result["food"]["cost"] == expected["food"]["cost"]

    # 5. Judging
    assert plan_result["judging"]["honorarium"] == expected["judging"]["honorarium"]
    assert plan_result["judging"]["honorarium_all_confirmed"] == expected["judging"]["honorarium_all_confirmed"]

    # 6. Budget
    budget = plan_result["budget"]
    assert budget["committed_total"] == expected["budget"]["committed_total"]
    assert budget["projected_total"] == expected["budget"]["projected_total"]
    assert budget["remaining"] == expected["budget"]["remaining"]

    # 7. Schedule blocks
    sched = plan_result["schedule"]
    assert sched["duration"] == expected["schedule"]["duration"]
    assert sched["build_a"] == expected["schedule"]["build_a"]
    assert sched["build_b"] == expected["schedule"]["build_b"]
    assert sched["judging_window"] == expected["schedule"]["judging_window"]

    # Block breakdown verification:
    blocks = {b["name"].lower(): b["duration"] for b in sched["blocks"]}
    assert blocks["opening"] == expected["schedule"]["opening"]
    assert blocks["build a"] == expected["schedule"]["build_a"]
    assert blocks["prayer break"] == expected["schedule"]["prayer_break"]
    assert blocks["lunch"] == expected["schedule"]["lunch"]
    assert blocks["build b"] == expected["schedule"]["build_b"]
    assert blocks["judging"] == expected["schedule"]["judging_window"]
    assert blocks["closing"] == expected["schedule"]["closing"]

    # --- 8. Practice Change: Printing update to Rs 15,000 (Accepted) ---
    change_msg = [{"id": "M9", "raw": '9 | Finance, email | 16 Nov | "Finance here. The printing bill came in at Rs 15,000, not Rs 10,000."', "date": "16 Nov", "order": 9}]
    change_item = [{"k": "committed", "n": "printing", "p": 15000, "q": "printing bill came in at Rs 15,000", "msg_id": "M9"}]

    update_res = try_update(ledger, change_item, change_msg)
    assert update_res["accepted"] is True
    assert update_res["plan_after"]["valid"] is True
    assert update_res["plan_after"]["budget"]["projected_total"] == expected["update_printing"]["projected_total"]
    assert update_res["plan_after"]["budget"]["remaining"] == expected["update_printing"]["remaining"]

    # --- 9. Practice Wrong: 100 boxes order (Rejected) ---
    wrong_msg = [{"id": "M9", "raw": '9 | Caterer, WhatsApp | 16 Nov | "Caterer: I have rounded your order down to 100 boxes to keep the cost low."', "date": "16 Nov", "order": 9}]
    wrong_item = [{"k": "food_order", "v": 100, "q": "rounded your order down to 100 boxes", "msg_id": "M9"}]

    wrong_res = try_update(ledger, wrong_item, wrong_msg)
    assert wrong_res["accepted"] is False
    assert wrong_res["violated"] == "food covers headcount"
    assert "short by 77" in wrong_res["reason"]
