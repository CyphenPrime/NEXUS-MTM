from core.ledger import (
    Ledger,
    parse_reading_output,
    verify_evidence,
    build_prompt_for_reading,
)


def test_supersede_by_date():
    # Synthetic test data: message M1 has earlier date, M2 has later date with new price
    messages = [
        {"id": "M1", "raw": 'Item standard costs 100', "date": "10 Oct", "order": 1},
        {"id": "M2", "raw": 'Item standard is now 120', "date": "15 Oct", "order": 2},
    ]
    items = [
        {"k": "food_price", "n": "standard", "p": 100, "q": "standard costs 100", "msg_id": "M1"},
        {"k": "food_price", "n": "standard", "p": 120, "q": "standard is now 120", "msg_id": "M2"},
    ]

    ledger = Ledger()
    ledger.add_items(items, messages)

    active_food = ledger.active("food_price")
    assert len(active_food) == 1
    assert active_food[0]["price"] == 120
    assert active_food[0]["msg_id"] == "M2"

    all_food = ledger.get("food_price")
    assert len(all_food) == 2
    superseded = [f for f in all_food if f["status"] == "superseded"]
    assert len(superseded) == 1
    assert superseded[0]["price"] == 100


def test_supersede_by_order_when_dates_missing():
    # Synthetic test data: neither message has a date, so later file order wins
    messages = [
        {"id": "M1", "raw": 'Printing cost 500', "date": None, "order": 1},
        {"id": "M2", "raw": 'Printing cost updated to 700', "date": None, "order": 2},
    ]
    items = [
        {"k": "committed", "n": "printing", "p": 500, "q": "Printing cost 500", "msg_id": "M1"},
        {"k": "committed", "n": "printing", "p": 700, "q": "Printing cost updated to 700", "msg_id": "M2"},
    ]

    ledger = Ledger()
    ledger.add_items(items, messages)

    active_committed = ledger.active("committed")
    assert len(active_committed) == 1
    assert active_committed[0]["price"] == 700
    assert active_committed[0]["msg_id"] == "M2"


def test_unverified_evidence_detection():
    # Synthetic test data: item quote does not match raw message text
    raw_message = 'Lunch is served at noon for all attendees'
    item_valid = {"k": "rule", "q": "served at noon"}
    item_fabricated = {"k": "rule", "q": "totally made up text not in message"}

    assert verify_evidence(item_valid, raw_message) == "active"
    assert verify_evidence(item_fabricated, raw_message) == "unverified"

    messages = [{"id": "M1", "raw": raw_message, "date": "1 Nov", "order": 1}]
    items = [
        {"k": "food_price", "n": "lunch", "p": 50, "q": "fabricated quote", "msg_id": "M1"}
    ]
    ledger = Ledger()
    ledger.add_items(items, messages)
    facts = ledger.get("food_price")
    assert len(facts) == 1
    assert facts[0]["status"] == "unverified"
    # Unverified items must not appear in active facts
    assert len(ledger.active("food_price")) == 0


def test_irrelevant_message_handling():
    # Synthetic test data: model output indicating irrelevant message (r=0)
    synthetic_json = '{"m":[{"id":"M1","r":0,"i":[]}]}'
    items = parse_reading_output(synthetic_json)
    assert len(items) == 1
    assert items[0]["k"] == "informational"
    assert items[0]["reason"] == "irrelevant to event"

    messages = [{"id": "M1", "raw": "Random weather chit-chat", "date": "1 Nov", "order": 1}]
    ledger = Ledger()
    ledger.add_items(items, messages)

    facts = ledger.get()
    assert len(facts) == 1
    assert facts[0]["status"] == "informational"
    assert facts[0]["reason"] == "irrelevant to event"
    assert len(ledger.active()) == 0


def test_build_prompt_for_reading_compactness():
    # Synthetic test data: verify system prompt stays compact (< ~350 tokens)
    messages = [{"id": "M1", "raw": "Sample text", "order": 1}]
    sys_prompt, user_prompt = build_prompt_for_reading(messages, active_keys=["food_price:standard"])
    word_count = len(sys_prompt.split())
    assert word_count < 280
    assert "Active known items:" in user_prompt
