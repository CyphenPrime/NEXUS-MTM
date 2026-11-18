import json
import re
import copy
from typing import Any
from core.reader import parse_date

ALLOWED_KINDS = {
    "attendance",
    "team_size",
    "budget_total",
    "event_minutes",
    "break",
    "fixed_time",
    "venue",
    "venue_need",
    "venue_unavailable",
    "food_price",
    "food_fee",
    "food_order",
    "food_need",
    "judges_confirmed",
    "judge_change",
    "judge_fee",
    "judge_minutes",
    "judge_max_teams",
    "judge_delay",
    "committed",
    "proposal",
    "approve",
    "cap",
    "rule",
}

# Singletons where only one active value exists at a time (independent of name)
SINGLETON_KINDS = {
    "team_size",
    "budget_total",
    "event_minutes",
    "food_order",
    "judges_confirmed",
    "judge_fee",
    "judge_minutes",
    "judge_max_teams",
}


class ParseError(Exception):
    """Raised when reading output fails schema or parsing validation."""
    pass


def build_prompt_for_reading(messages: list[dict], active_keys: list[str] | None = None) -> tuple[str, str]:
    """
    Builds token-lean (<= ~250 tokens) system prompt and compact user prompt.
    System prompt defines exact JSON schema, compact allowed kinds, and extraction rules.
    """
    system_prompt = (
        'Extract event planning facts into compact JSON:\n'
        '{"m":[{"id":"M1","r":1,"i":[{"k":"attendance","n":"students","v":150,"q":"150 students"}]}]}\n'
        'Kinds & fields:\n'
        '- attendance: n (students|staff|judges|other), v (count), q\n'
        '- team_size: v (students/team), q\n'
        '- budget_total: p (PKR), q\n'
        '- event_minutes: v (minutes), q\n'
        '- break: n (label), v (minutes), q\n'
        '- fixed_time: n (label), t (HH:MM), q\n'
        '- venue: n (name), v (capacity), p (PKR), f ([facilities]), q\n'
        '- venue_need: n (facility), q\n'
        '- venue_unavailable: n (venue name), q\n'
        '- food_price: n (option), p (PKR/head), q\n'
        '- food_fee: n (label), p (PKR), q\n'
        '- food_order: v (count), q\n'
        '- food_need: n (text), v (count), q\n'
        '- judges_confirmed: v (count), q\n'
        '- judge_change: v (+/- count), q\n'
        '- judge_fee: p (PKR/judge), q\n'
        '- judge_minutes: v (min/team), q\n'
        '- judge_max_teams: v (max teams/judge), q\n'
        '- judge_delay: v (minutes late), q\n'
        '- committed: n (item), p (PKR), q\n'
        '- proposal: n (label), p (PKR), q\n'
        '- approve: n (proposal label), q\n'
        '- cap: n (area), p (PKR), q\n'
        '- rule: n (text), a (venue|schedule|food|judging|budget), q\n\n'
        'Normalization Rules for Facilities & Needs:\n'
        'Normalize accessibility facilities/needs to standard tags: "step-free access", "ramp access", "wheelchair", "ground floor" -> all include "step-free access".\n'
        'Normalize AV/projector/screen to "projector" or "av".\n'
        'Rules: JSON only. No whitespace or line-breaks in JSON. Amounts: integer PKR (no commas). '
        'Short verbatim quote q (<=12 words). If irrelevant: r=0, i=[]. '
        'Short stable lowercase n, reuse identical names. English or Roman Urdu. Never invent values.'
    )

    user_lines = [f"{m['id']}: {m['raw']}" for m in messages]
    if active_keys:
        user_lines.append(f"Active known items: {', '.join(active_keys)}")

    user_prompt = "\n".join(user_lines)
    return system_prompt, user_prompt


def parse_reading_output(text: str) -> list[dict]:
    """
    Parses and strictly validates the model's reading output JSON.
    Strips markdown code fences if present. Attaches msg_id to each extracted item.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except Exception as e:
        raise ParseError(f"Failed to parse JSON response: {e}")

    if not isinstance(data, dict) or "m" not in data or not isinstance(data["m"], list):
        raise ParseError("Output must be a JSON object with a top-level 'm' list.")

    extracted_items = []

    for m_entry in data["m"]:
        if not isinstance(m_entry, dict) or "id" not in m_entry:
            raise ParseError("Each message entry in 'm' must have an 'id'.")

        msg_id = m_entry["id"]
        is_relevant = m_entry.get("r", 1)

        if is_relevant == 0:
            extracted_items.append({
                "k": "informational",
                "n": "irrelevant",
                "v": None,
                "p": None,
                "f": [],
                "t": None,
                "a": None,
                "q": "",
                "msg_id": msg_id,
                "reason": "irrelevant to event",
            })
            continue

        raw_items = m_entry.get("i", [])
        if not isinstance(raw_items, list):
            raise ParseError(f"Message {msg_id} 'i' field must be a list.")

        for item in raw_items:
            if not isinstance(item, dict):
                raise ParseError(f"Item in message {msg_id} must be a dict.")

            kind = item.get("k")
            if not kind or kind not in ALLOWED_KINDS:
                raise ParseError(f"Message {msg_id} contains invalid kind '{kind}'.")

            name = item.get("n")
            if name is not None:
                name = str(name).strip().lower()

            # Ensure numeric fields are integer PKR / counts
            val = item.get("v")
            if val is not None:
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    raise ParseError(f"Message {msg_id} item '{kind}' field 'v' must be an integer, got: {val}")

            price = item.get("p")
            if price is not None:
                try:
                    price = int(price)
                except (ValueError, TypeError):
                    raise ParseError(f"Message {msg_id} item '{kind}' field 'p' must be an integer, got: {price}")

            facilities = item.get("f") or []
            if not isinstance(facilities, list):
                facilities = [str(facilities)]
            facilities = [str(fac).strip().lower() for fac in facilities]

            time_val = item.get("t")
            if time_val is not None:
                time_val = str(time_val).strip()

            area_val = item.get("a")
            if area_val is not None:
                area_val = str(area_val).strip().lower()

            quote = str(item.get("q", "")).strip()

            extracted_items.append({
                "k": kind,
                "n": name,
                "v": val,
                "p": price,
                "f": facilities,
                "t": time_val,
                "a": area_val,
                "q": quote,
                "msg_id": msg_id,
            })

    return extracted_items


def verify_evidence(item: dict, raw_message: str) -> str:
    """
    Verifies that quote q (or key segments of it if multiple clauses were combined)
    matches the raw message. Returns 'active' if valid, 'unverified' if missing or mismatch.
    """
    quote = item.get("q", "").strip()
    if not quote:
        return "unverified"

    norm_quote = re.sub(r"\s+", " ", quote.lower())
    norm_raw = re.sub(r"\s+", " ", raw_message.lower())

    if norm_quote in norm_raw:
        return "active"

    # If the LLM spliced two clauses separated by a period or sentence (e.g. "Hall 2 seats 180... Only Halls 2 and 3...")
    # check if each sentence/clause individually appears in norm_raw
    clauses = [c.strip() for c in re.split(r"[.;\n]+", norm_quote) if c.strip()]
    if len(clauses) > 1 and all(clause in norm_raw for clause in clauses):
        return "active"

    return "unverified"


class Ledger:
    """
    Fact ledger maintaining structured evidence-backed facts.
    Implements date-aware and order-aware superseding, preservation of history,
    and structured querying.
    """

    def __init__(self):
        self.facts: list[dict] = []
        self._next_fid = 1

    def add_items(self, items: list[dict], messages: list[dict]):
        """
        Adds parsed items to ledger, verifies verbatim evidence,
        attaches message date/order metadata, and runs supersede rules.
        """
        msg_map = {m["id"]: m for m in messages}

        for item in items:
            msg_id = item["msg_id"]
            msg = msg_map.get(msg_id, {})
            raw_text = msg.get("raw", "")
            date_str = msg.get("date")
            order = msg.get("order", 0)

            if item.get("k") == "informational":
                status = "informational"
            else:
                status = verify_evidence(item, raw_text)

            fid = f"F{self._next_fid}"
            self._next_fid += 1

            fact_record = {
                "fid": fid,
                "kind": item["k"],
                "name": item.get("n"),
                "value": item.get("v"),
                "price": item.get("p"),
                "facilities": item.get("f", []),
                "time": item.get("t"),
                "area": item.get("a"),
                "msg_id": msg_id,
                "evidence": item.get("q", ""),
                "status": status,
                "order": order,
                "date": date_str,
            }
            if "reason" in item:
                fact_record["reason"] = item["reason"]

            self.facts.append(fact_record)

        self.supersede()

    def supersede(self):
        """
        Supersedes older facts of the same kind and normalised name.
        Comparison:
        - Later message date wins (parsed with parse_date)
        - If dates missing or equal, later file order wins
        - Older facts transition from 'active' to 'superseded' (history is never deleted)
        """
        # Group facts by group key
        groups: dict[tuple, list[dict]] = {}

        for f in self.facts:
            # Only consider active facts for superseding
            if f["status"] not in ("active", "superseded"):
                continue

            kind = f["kind"]
            name = f["name"] or ""

            # Singletons supersede any fact of the same kind
            if kind in SINGLETON_KINDS:
                group_key = (kind, "")
            elif kind in ("judge_change", "rule"):
                # judge_change and rules without specific names are additive, not superseded
                if not name:
                    continue
                group_key = (kind, name)
            else:
                group_key = (kind, name)

            groups.setdefault(group_key, []).append(f)

        for group_key, fact_list in groups.items():
            if len(fact_list) <= 1:
                continue

            def sort_key(fact):
                d_parsed = parse_date(fact["date"])
                # (has_date, (year, month, day), order)
                if d_parsed is not None:
                    return (1, d_parsed, fact["order"])
                return (0, (0, 0, 0), fact["order"])

            # Sort ascending so the winning fact is last
            sorted_facts = sorted(fact_list, key=sort_key)
            winner = sorted_facts[-1]

            for fact in sorted_facts[:-1]:
                if fact["status"] == "active":
                    fact["status"] = "superseded"

            # Ensure winner remains active (unless it was unverified/rejected)
            if winner["status"] == "superseded":
                winner["status"] = "active"

    def get(self, kind: str | None = None) -> list[dict]:
        """Returns all facts (any status), optionally filtered by kind."""
        if kind is None:
            return list(self.facts)
        return [f for f in self.facts if f["kind"] == kind]

    def active(self, kind: str | None = None) -> list[dict]:
        """Returns active facts, optionally filtered by kind."""
        if kind is None:
            return [f for f in self.facts if f["status"] == "active"]
        return [f for f in self.facts if f["kind"] == kind and f["status"] == "active"]

    def to_dict(self) -> dict:
        """Serializes ledger facts and counter."""
        return {
            "facts": copy.deepcopy(self.facts),
            "next_fid": self._next_fid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ledger":
        """Deserializes ledger from dictionary."""
        ledger = cls()
        ledger.facts = copy.deepcopy(data.get("facts", []))
        ledger._next_fid = data.get("next_fid", 1)
        return ledger

    def copy(self) -> "Ledger":
        """Creates a deep copy of the ledger."""
        return Ledger.from_dict(self.to_dict())
