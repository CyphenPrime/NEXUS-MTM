class Trace:
    """
    Truthful execution trace recording model calls and system events in chronological order.
    Calculates token statistics based strictly on provider-reported numbers.
    """

    def __init__(self):
        self.entries = []  # Chronological list of calls and system events
        self.calls = []    # List of all call dicts with assigned call_number

    def add_call(self, call_dict: dict) -> dict:
        """Assigns sequential call_number 1, 2, ... and records the call."""
        call_copy = dict(call_dict)
        call_number = len(self.calls) + 1
        call_copy["call_number"] = call_number
        self.calls.append(call_copy)
        self.entries.append({"type": "call", "data": call_copy})
        return call_copy

    def add_event(self, text: str):
        """Records an unnumbered system event in chronological order."""
        self.entries.append({"type": "event", "text": text})

    def totals(self) -> dict:
        """
        Sums input/output/thinking/total tokens over all recorded calls.
        Tracks how many calls were missing provider usage data.
        """
        input_sum = 0
        output_sum = 0
        thinking_sum = 0
        total_sum = 0
        missing_count = 0

        for c in self.calls:
            in_tok = c.get("input_tokens")
            out_tok = c.get("output_tokens")
            th_tok = c.get("thinking_tokens")
            tot_tok = c.get("total_tokens")

            if in_tok is None or out_tok is None or tot_tok is None:
                missing_count += 1

            if in_tok is not None:
                input_sum += in_tok
            if out_tok is not None:
                output_sum += out_tok
            if th_tok is not None:
                thinking_sum += th_tok
            if tot_tok is not None:
                total_sum += tot_tok

        return {
            "calls_count": len(self.calls),
            "missing_usage_count": missing_count,
            "input_tokens": input_sum,
            "output_tokens": output_sum,
            "thinking_tokens": thinking_sum,
            "total_tokens": total_sum,
        }

    def totals_line(self) -> str:
        """Returns the single formatted TOTAL TOKENS line."""
        tot = self.totals()
        if tot["missing_usage_count"] > 0:
            return (
                f"TOTAL TOKENS: input={tot['input_tokens']} output={tot['output_tokens']} "
                f"total={tot['total_tokens']} (known subtotal; {tot['missing_usage_count']} call(s) unavailable)"
            )
        return f"TOTAL TOKENS: input={tot['input_tokens']} output={tot['output_tokens']} total={tot['total_tokens']}"

    def render_calls_text(self) -> str:
        """Renders only the CALL #n blocks from the trace."""
        lines = []
        for entry in self.entries:
            if entry["type"] == "call":
                c = entry["data"]
                lines.append(
                    f"CALL #{c['call_number']} | model: {c['model']} | area: {c['area']} | "
                    f"seconds: {c.get('seconds', 0.0)} | status: {c.get('status', 'success')}"
                )
                lines.append(f"INPUT : {c.get('input', '')}")
                lines.append(f"OUTPUT: {c.get('output', '')}")
                in_str = str(c["input_tokens"]) if c.get("input_tokens") is not None else "unavailable"
                out_str = str(c["output_tokens"]) if c.get("output_tokens") is not None else "unavailable"
                th_str = str(c["thinking_tokens"]) if c.get("thinking_tokens") is not None else "none"
                tot_str = str(c["total_tokens"]) if c.get("total_tokens") is not None else "unavailable"
                lines.append(f"TOKENS: input={in_str} output={out_str} thinking={th_str} total={tot_str}")
        return "\n".join(lines)

    def render_events_text(self) -> str:
        """Renders only the SYSTEM EVENT lines from the trace."""
        lines = []
        for entry in self.entries:
            if entry["type"] == "event":
                lines.append(f"SYSTEM EVENT: {entry['text']}")
        return "\n".join(lines)

    def render_text(self) -> str:
        """
        Renders trace text format adhering strictly to specification.
        Ends with the required TOTAL TOKENS line.
        """
        lines = []
        for entry in self.entries:
            if entry["type"] == "call":
                c = entry["data"]
                lines.append(
                    f"CALL #{c['call_number']} | model: {c['model']} | area: {c['area']} | "
                    f"seconds: {c.get('seconds', 0.0)} | status: {c.get('status', 'success')}"
                )
                lines.append(f"INPUT : {c.get('input', '')}")
                lines.append(f"OUTPUT: {c.get('output', '')}")

                in_str = str(c["input_tokens"]) if c.get("input_tokens") is not None else "unavailable"
                out_str = str(c["output_tokens"]) if c.get("output_tokens") is not None else "unavailable"
                th_str = str(c["thinking_tokens"]) if c.get("thinking_tokens") is not None else "none"
                tot_str = str(c["total_tokens"]) if c.get("total_tokens") is not None else "unavailable"

                lines.append(f"TOKENS: input={in_str} output={out_str} thinking={th_str} total={tot_str}")
            elif entry["type"] == "event":
                lines.append(f"SYSTEM EVENT: {entry['text']}")

        lines.append(self.totals_line())
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serializes trace data to a dictionary."""
        return {
            "entries": self.entries,
            "calls": self.calls,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        """Reconstructs a Trace instance from a dictionary."""
        trace = cls()
        trace.entries = data.get("entries", [])
        trace.calls = data.get("calls", [])
        return trace
