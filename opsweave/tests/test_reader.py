import tempfile
from pathlib import Path
from core.reader import read_messages, parse_date


def test_parse_date():
    # Synthetic test data for date parsing
    assert parse_date("9 Nov") == (0, 11, 9)
    assert parse_date("12 November 2026") == (2026, 11, 12)
    assert parse_date("2026-11-03") == (2026, 11, 3)
    assert parse_date("Oct 20") == (0, 10, 20)
    assert parse_date("invalid date") is None
    assert parse_date(None) is None


def test_reader_blank_line_separated():
    # Synthetic test data: blank-line separated blocks
    content = """1 | Alice, email | 10 Nov | "First test message."

2 | Bob, WhatsApp | 11 Nov | "Second test message."
"""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    try:
        msgs = read_messages(temp_path)
        assert len(msgs) == 2
        assert msgs[0]["id"] == "M1"
        assert msgs[0]["sender"] == "Alice"
        assert msgs[0]["channel"] == "email"
        assert msgs[0]["date"] == "10 Nov"
        assert msgs[0]["raw"] == '1 | Alice, email | 10 Nov | "First test message."'
        assert msgs[1]["id"] == "M2"
        assert msgs[1]["sender"] == "Bob"
        assert msgs[1]["channel"] == "WhatsApp"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_reader_single_line_and_numbered_formats():
    # Synthetic test data: numbered lines without blank lines
    content = """[1] Plain text message with no header
[2] Another plain line
"""
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    try:
        msgs = read_messages(temp_path)
        assert len(msgs) == 2
        assert msgs[0]["id"] == "M1"
        assert msgs[0]["raw"] == "[1] Plain text message with no header"
        assert msgs[0]["sender"] is None
        assert msgs[0]["channel"] is None
        assert msgs[0]["date"] is None
        assert msgs[1]["id"] == "M2"
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_reader_exact_raw_preservation_and_hashes():
    # Synthetic test data: verify raw preservation including spaces/quotes
    content = '1 | Team, email | 1 Jan | "Exact verbatim string with \'quotes\' & spaces."\n'
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    try:
        msgs = read_messages(temp_path)
        assert len(msgs) == 1
        assert msgs[0]["raw"] == '1 | Team, email | 1 Jan | "Exact verbatim string with \'quotes\' & spaces."'
        assert len(msgs[0]["hash"]) == 64  # valid SHA-256 hex string
    finally:
        Path(temp_path).unlink(missing_ok=True)
