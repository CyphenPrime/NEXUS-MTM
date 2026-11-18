import hashlib
import re
from pathlib import Path


MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

KNOWN_CHANNELS = {"email", "whatsapp", "slack", "sms", "memo", "phone", "call", "in-person"}


def parse_date(date_str: str | None) -> tuple[int, int, int] | None:
    """
    Parses date string into a comparable tuple: (year, month, day).
    If year is not present, year is 0.
    Returns None if date cannot be parsed. Never guesses.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = date_str.strip().strip('"\'')
    if not cleaned:
        return None

    # Format: YYYY-MM-DD
    m_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", cleaned)
    if m_iso:
        return int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))

    # Format: DD/MM/YYYY or MM/DD/YYYY (if year is 4 digits)
    m_slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", cleaned)
    if m_slash:
        return int(m_slash.group(3)), int(m_slash.group(2)), int(m_slash.group(1))

    # Format: "9 Nov", "9 Nov 2026", "09 November 2026", "Nov 9, 2026"
    m_named = re.search(r"(\d{1,2})\s+([A-Za-z]+)(?:\s+(\d{4}))?", cleaned)
    if m_named:
        day = int(m_named.group(1))
        month_name = m_named.group(2).lower()
        year = int(m_named.group(3)) if m_named.group(3) else 0
        if month_name in MONTH_MAP:
            return year, MONTH_MAP[month_name], day

    m_named_rev = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:,?\s+(\d{4}))?", cleaned)
    if m_named_rev:
        month_name = m_named_rev.group(1).lower()
        day = int(m_named_rev.group(2))
        year = int(m_named_rev.group(3)) if m_named_rev.group(3) else 0
        if month_name in MONTH_MAP:
            return year, MONTH_MAP[month_name], day

    return None


def _split_into_raw_blocks(text: str) -> list[str]:
    """
    Splits text into message chunks tolerating:
    - Blank-line separated blocks
    - Numbered blocks ('1.', '#1', '[1]', '1 |')
    - Single line messages
    """
    text = text.strip()
    if not text:
        return []

    # If double-newline blank line blocks exist, prefer blank line separation
    if re.search(r"\n\s*\n", text):
        blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
        return blocks

    # Otherwise check for line prefixes like "1 |", "1.", "#1", "[1]"
    lines = text.splitlines()
    has_prefixed_lines = any(re.match(r"^(?:\[\d+\]|\#\d+|\d+[\.\)]|\d+\s*\|)", l.strip()) for l in lines)
    if has_prefixed_lines:
        blocks = []
        current_block = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if re.match(r"^(?:\[\d+\]|\#\d+|\d+[\.\)]|\d+\s*\|)", line_str) and current_block:
                blocks.append("\n".join(current_block))
                current_block = [line]
            else:
                current_block.append(line)
        if current_block:
            blocks.append("\n".join(current_block))
        return blocks

    # Fallback: one non-empty line per message
    return [l.strip() for l in lines if l.strip()]


def _extract_metadata_from_block(raw: str) -> tuple[str | None, str | None, str | None]:
    """
    Extracts (sender, channel, date) if clearly present in the format:
    e.g. '1 | Dean\'s office, email | 9 Nov | "..."'
    Never guesses; returns None when absent.
    """
    first_line = raw.splitlines()[0].strip()

    # Look for pipe-separated headers: [Prefix |] Header | Date | Content
    if "|" in first_line:
        parts = [p.strip() for p in first_line.split("|")]
        sender = None
        channel = None
        date_str = None

        # Discard leading numeric prefix if present (e.g. '1', '#1')
        if re.match(r"^(?:\[\d+\]|\#\d+|\d+[\.\)]?)$", parts[0]):
            parts = parts[1:]

        for part in parts[:-1]:  # exclude final content part
            # Check for date in part
            parsed_d = parse_date(part)
            if parsed_d is not None and date_str is None:
                date_str = part
                continue

            # Check for sender / channel in part (e.g. "Dean's office, email")
            if "," in part:
                subparts = [sp.strip() for sp in part.split(",")]
                for sp in subparts:
                    if sp.lower() in KNOWN_CHANNELS and channel is None:
                        channel = sp
                    elif sender is None:
                        sender = sp
            else:
                if part.lower() in KNOWN_CHANNELS and channel is None:
                    channel = part
                elif sender is None and not parse_date(part):
                    sender = part

        return sender, channel, date_str

    return None, None, None


def read_messages(path: str = "data/messages.txt") -> list[dict]:
    """
    Reads messages from text file, assigns M1, M2, ... in file order,
    preserves exact raw text, computes SHA256 hashes, and extracts metadata.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Messages file not found: {path}")

    content = file_path.read_text(encoding="utf-8")
    blocks = _split_into_raw_blocks(content)

    results = []
    for idx, block in enumerate(blocks, start=1):
        msg_id = f"M{idx}"
        raw_text = block
        sender, channel, date_str = _extract_metadata_from_block(raw_text)
        sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        results.append({
            "id": msg_id,
            "raw": raw_text,
            "sender": sender,
            "channel": channel,
            "date": date_str,
            "order": idx,
            "hash": sha,
        })

    return results
