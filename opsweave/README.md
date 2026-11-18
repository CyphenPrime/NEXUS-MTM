# OpsWeave — Lean, Evidence-Backed Event Planner (FINAL)

**Mind to Machine Hackathon · Student Brief of 18 November 2026**
Stack: Python 3.10+ · one small language model (configurable) · Streamlit UI · built in Google Antigravity.

OpsWeave reads a pack of messages (English / Roman Urdu), extracts facts with **one cheap model call**, and does **everything else in plain Python**: conflict checks, arithmetic, the five-area plan, validation. Every fact keeps its source message. Every rejected message keeps a reason. Every model call is traced with real, provider-reported token counts.

> **The model reads language. Python does maths and rules.** Fewer tokens = more points.

---

## 0. Decisions made after comparing three drafts (ChatGPT, Gemini, and the review)

| # | Issue | Final decision |
|---|---|---|
| 1 | ChatGPT drafts said the schedule is "ambiguous" (10:00 start vs 2:30–4:30 judge visits). | **Wrong.** `10:00 build / 1:25 freeze / 1:30 test / 2:30–4:30 judges` is the **team's own build day**, not a constraint of the planned event. The planned event = **4 hours + a 15-minute prayer break**. Never put build-day times in the event schedule. |
| 2 | Gemini said food headcount is "177 or 180". | **177** (the brief states it): 150 students + 10 staff + **17 judges needed** (= ceil(50 ÷ 3)), *not* the 20 confirmed. Rule: `students + staff + judges needed`, unless the pack says otherwise. |
| 3 | ChatGPT: a model call per area. | Wasteful. **One `reading` call per run/update**; all five areas are computed by Python. |
| 4 | Gemini: `python main.py sample_messages.txt` (argument). | The brief says no flags. The command is exactly `python main.py`, which reads `data/messages.txt`. |
| 5 | Gemini: UI with upload, "Run", "Send new message", "Save" buttons. | **Adopted** (good for the UI score), but the buttons only write `data/messages.txt` and run the *same* `python main.py` as a subprocess — one code path, never a second pipeline. |
| 6 | Gemini: `gemini-2.5-flash` / `gpt-4o-mini` / Ollama. | Provider adapter supports **Gemini** and any **OpenAI-compatible** endpoint (OpenAI, or local **Ollama** via base URL) as a rate-limit fallback. Default `gemini-2.5-flash-lite`. The organizers' small-model list decides the bonus — ask the help desk. |
| 7 | Nobody handled: the unseen pack replacing the sample pack. | `main.py` compares saved message hashes with the file: saved list is a **prefix** → *update*; otherwise → **reset + full run**. |
| 8 | Nobody handled: dirty `git status`. | `data/state.json`, `outputs/`, `.env`, `.venv/` are gitignored. The volunteer checks `git status` **before** the run. |
| 9 | Honorarium: 20 confirmed judges or 17 needed? | Genuine ambiguity. Default: pay **17 needed** (consistent with 177). Show the all-20 cost as a warning. Ask the help desk. |
| 10 | Unseen constraint kinds were vague. | Closed list of fact kinds (§4) incl. venue unavailable, judge withdrawal, spending caps, approvals of proposals, food needs, generic `rule` (shown as "unverified" warning, never ignored). |
| 11 | Token / 2-minute measurement. | `measure.py` runs the full pipeline under a hard 120-second kill and reports seconds + tokens. |
| 12 | Submission upload. | `main.py` also writes `outputs/final_submission.txt` (plan + rejected + full trace) ready to upload. |
| 13 | ChatGPT's what-if simulator, change radar, 7 UI sections. | Dropped. UI scoring = plan, trace, rejected messages, clear and easy. |

---

## 1. The task (from the brief)

Build an agent system that reads a message pack and plans a **4-hour physical hackathon in Islamabad for 150 students in 50 teams**: **venue, schedule, food, judging, budget**. Respect every constraint in the messages, including kinds not in the sample pack.

The system must:
1. Read every message from a text file exactly as given (no facts typed in code).
2. Process every message the same way through the same command (no flags/hints/edits).
3. Print a trace: each model call numbered, model name, **one** area tag (`reading`, `venue`, `schedule`, `food`, `judging`, `budget`), input, output, provider-reported token counts; end with total tokens.
4. Accept new messages after the first run and update the existing plan.
5. On a conflict with a rule/fact, keep the plan valid and print the reason in the trace.

Limits: full run cut off at **2 min**; update **≤ 5 model calls**, cut off at **1 min**. Plan checks: **correct figures, within budget, venue fits, schedule valid, enough judges, all areas covered.**
Scoring (100 + 10 bonus): Output 30 · Catching the wrong message 20 · Understanding 20 · Handling change 10 · UI 10 · Predicting a change 5 · Token use 5 · Bonus 10 (every call on the organizers' small-model list). Tie-breaks: wrong-message catch, handling change, token use.
Disqualification: misreported trace, facts typed in code, code changed after the 1:25 freeze.

Test day: unseen pack → 3 more messages one by one (two change the task, one is plausible but wrong) → write a prediction slip of which areas make model calls → upload final plan + trace.

---

## 2. Architecture

```
data/messages.txt ─► core/reader.py   (split, IDs, dates, hashes)                [Python]
                         │
                         ▼
                    core/llm.py  ── ONE "reading" call ──► compact JSON items    [model]
                         │
                         ▼
                    core/ledger.py (verify quotes, supersede by kind+name+date)  [Python]
                         │
                         ▼
                    core/engine.py (venue · schedule · food · judging · budget · validate · try_update)  [Python]
                         │
                         ▼
   core/pipeline.py (full run / update / reset / reject) ─► core/store.py ─► outputs/*, data/state.json
         ▲                                                         │
   main.py (watchdog + prints trace)                       app.py (Streamlit; runs `python main.py` via subprocess)
```

| Part | Purpose | What breaks without it |
|---|---|---|
| `reader.py` | splits file, keeps raw text, IDs, dates, hashes | facts altered/typed in; no update-vs-reset detection |
| `llm.py` | only code that talks to a model; returns real usage | untruthful trace → disqualification |
| `ledger.py` | facts + evidence + supersede history | stale price used; no evidence trail |
| `engine.py` | deterministic planning, validation, conflict check | wrong maths; wrong message accepted |
| `pipeline.py` | one flow for run/update/reset/reject | different paths for different messages |
| `trace.py` | numbers calls, sums tokens, logs events | invalid trace |
| `store.py` | persistence + outputs | no incremental update; nothing to upload |
| `main.py` | the one judged command + time limit | breaks "same command" and the time limit |
| `app.py` | shows plan, trace, rejections | lose UI points |

### Module contracts (names are fixed; prompts rely on them)
* `reader.read_messages(path="data/messages.txt") -> list[dict]` with keys `id, raw, sender, channel, date, order, hash`.
* `llm.call_model(area, system, user) -> dict` with keys `model, area, input, output, input_tokens, output_tokens, thinking_tokens, total_tokens, status, error, seconds`.
* `trace.Trace`: `add_call`, `add_event`, `totals`, `render_text`, `to_dict`.
* `ledger.build_prompt_for_reading(messages, active_keys=None) -> (system, user)`, `ledger.parse_reading_output(text) -> list`, `ledger.Ledger` (`add_items, supersede, get, active, to_dict, from_dict, copy`).
* `engine.plan(ledger) -> dict`, `engine.affected_areas(items) -> list`, `engine.try_update(ledger, items, messages) -> dict`, `engine.render_markdown(plan) -> str`.
* `pipeline.run(path="data/messages.txt", llm_fn=llm.call_model) -> dict` (returns plan, trace, rejected, mode).
* `store.load_state / save_state / save_outputs`.

### Folder structure
```
opsweave/
├── main.py  measure.py  app.py  config.py
├── core/  __init__.py reader.py llm.py ledger.py engine.py trace.py store.py pipeline.py
├── data/  messages.txt   practice_change.txt   practice_wrong.txt
├── tests/ (+ tests/fixtures/)
├── outputs/  (generated, gitignored)
├── .streamlit/config.toml
├── .env.example  .gitignore  requirements.txt  README.md  CONTEXT.md
```

---

## 3. Message handling

* The splitter inspects the real `data/messages.txt` and accepts: blank-line blocks, one message per non-empty line, numbered lines (`1.`, `#1`, `[1]`, `1 |`), `|`-separated rows. Raw text is kept unchanged. Sender/channel/date only if clearly present, else `null`.
* Dates ("9 Nov", "2026-11-09") parsed by Python. If both facts have dates, the **later date wins**; otherwise file order wins.
* IDs `M1, M2, …` in file order. SHA-256 per message decides *old vs new*.
* Roman Urdu is sent to the model untouched.

---

## 4. The single reading call (token-lean)

One call per full run (all messages) and one per update (new messages + a short active-keys line). Settings: temperature 0, JSON-only, `max_output_tokens` 1500, thinking off/minimal, compact JSON, system prompt ≲ 350 tokens, no echo of message text.

Output format (short keys):
```json
{"m":[{"id":"M1","r":1,"i":[{"k":"attendance","n":"students","v":150,"q":"150 students"}]}]}
```
`r`=1 relevant, 0 irrelevant. `n`=short stable lowercase name (**reuse the exact same name for the same item**, e.g. `printing`, `standard`, `hall a`). `q`=verbatim quote ≤ 12 words; Python checks it is a substring of the message, else the fact is `unverified`.

| k | fields | meaning |
|---|---|---|
| `attendance` | n=students/staff/judges/other, v | people counts |
| `team_size` | v | students per team |
| `budget_total` | p | all-in budget (PKR) |
| `event_minutes` | v | event duration |
| `break` | n, v=minutes | required break (e.g. prayer) |
| `fixed_time` | n=block label, t="HH:MM" | block at a fixed clock time |
| `venue` | n, v=capacity, p=price, f=[facilities] | venue option |
| `venue_need` | n=facility | mandatory facility |
| `venue_unavailable` | n=venue name | venue cannot be used |
| `food_price` | n=option, p=price per head | menu option |
| `food_fee` | n, p | delivery/service fee (0 if free) |
| `food_order` | v=quantity | quantity someone states/orders |
| `food_need` | n=text, v=count | dietary/other need (shown, flagged unverified) |
| `judges_confirmed` | v | confirmed judges |
| `judge_change` | v=signed number | judges added (+) / withdrawn (−) |
| `judge_fee` | p | honorarium per judge |
| `judge_minutes` | v | minutes per team |
| `judge_max_teams` | v | max teams per judge |
| `judge_delay` | v=minutes | a judge may be late |
| `committed` | n, p | already ordered/spent |
| `proposal` | n, p | optional, **unapproved** |
| `approve` | n=proposal label | an authority approves a proposal |
| `cap` | n=area, p | maximum spend for an area |
| `rule` | n=text, a=area | any other constraint → "unverified constraint" warning |

---

## 5. Deterministic engine (Python only; integer PKR)

```
teams         = stated teams, else ceil(students / team_size)
judges_needed = ceil(teams / judge_max_teams)
headcount     = students + staff + judges_needed        (unless the pack says otherwise; shown as an assumption)
```
* **Venue**: eligible = capacity ≥ headcount, not `venue_unavailable`, has every `venue_need`. Cheapest eligible wins. None → fail with reasons. Never assume an unlisted facility.
* **Food**: newest valid price (later date supersedes). Prefer option named *standard*; if budget would break, switch to cheapest option and log it. `cost = headcount × price + fees`. A stated `food_order` < headcount → **invalid** (show shortfall). Never change headcount to fit an order.
* **Judging**: `confirmed = judges_confirmed + Σ judge_change`. Need `confirmed ≥ judges_needed`. Each judge ≤ `judge_max_teams`; per-judge minutes = teams × `judge_minutes`. Honorarium = `judges_needed × judge_fee` (warning shows the cost if all confirmed were paid). `judge_delay` = risk, **not** cancellation; adds buffer to the judging window.
* **Schedule** (offsets from start, or clock time if given). Order: Opening (15) → Build A → each required break → Lunch (30) → Build B → Judging window (= `judge_max_teams × judge_minutes + max delay`) → Closing (15). Opening/Lunch/Closing minutes are **planning defaults** in `config.py` (labelled, not facts). Build = duration − all other blocks, split: A = floor(half), B = rest. A `fixed_time` block is placed at its time (shift build blocks); impossible → fail with shortfall. Valid when total = duration, no overlap, every break present, judging window fits, build ≥ 0 (warn if < 60 min).
* **Budget**: `committed_total + venue + food + honoraria + approved proposals`; `remaining = budget − projected`. Each cost once. Unapproved `proposal` stays outside the total (shown with remaining-after). `cap` per area enforced. Over budget → fail with exact overrun.
* **Checks** (exact names): `correct figures` (totals recomputed a second way), `within budget`, `venue fits`, `schedule valid`, `enough judges`, `all areas covered`, plus `food covers headcount`, `evidence present`. `valid` = no fail and no unknowns. Missing inputs → `unknowns`, never invented.
* **Catching the wrong message**: apply the candidate items to a **copy** of the ledger → re-plan → validate. If the plan was valid and becomes invalid (or a hard rule breaks: food order < headcount, over budget/cap, judge cap, no venue) → **reject**, keep the previous plan, log reason with numbers. A valid change (price change, withdrawn judge with spares, new facility rule that another venue meets) is **accepted**. Newer ≠ correct.
* **Router** (affected areas, for the trace): attendance/team_size → all; venue*/venue_need → venue, budget; event_minutes/break/fixed_time → schedule; food* → food, budget; judge* → judging, schedule, budget; committed/budget_total/proposal/approve/cap → budget; rule → its `a`. Recalculation is Python, so **model calls per update = 1 (`reading`)**.

---

## 6. Trace

```
CALL #1 | model: <actual id> | area: reading | seconds: 2.1
INPUT : <exact text sent>
OUTPUT: <exact response>
TOKENS: input=<n> output=<n> thinking=<n|none> total=<n>     ("unavailable" if the provider did not report)
SYSTEM EVENT: M9 rejected — food order 100 < headcount 177 (short by 77). Previous valid plan retained.
TOTAL TOKENS: input=… output=… total=…
```
Retries are real, numbered calls. System events are not numbered. Totals sum recorded calls only; if some usage is missing print the known subtotal and the number unavailable.

---

## 7. UI (Streamlit, `streamlit run app.py`)

Dark, clean, teal accent. KPI strip: status (VALID/INVALID), budget, projected, remaining, venue, headcount, judges, calls, total tokens.
* **Sidebar**: upload a `.txt` pack (replaces `data/messages.txt`) · **Run / Reprocess** (runs `python main.py` as a subprocess) · **Send new message** text box (appends a new numbered block to `data/messages.txt`, then runs `python main.py`) · download `outputs/final_submission.txt`.
* **Plan** tab: Venue (all venues + eligible/ineligible reason) · Schedule table/timeline · Food · Judging (judge→teams table, risk notes) · Budget (committed / selected / optional proposals) · checklist ✅/⚠️/❌ · assumptions · unknowns · "Evidence" expanders.
* **Trace** tab: numbered calls (expanders with full input/output), system events, bold TOTAL TOKENS.
* **Rejected & changes** tab: red cards for rejected messages (exact text, reason, rule, area, "previous plan retained"); superseded facts; update history (new messages, accepted/rejected, affected areas, model calls, areas not recomputed).

---

## 8. Token efficiency and the 2-minute measurement

Single batched call · compact keys · no reasoning text · thinking off · capped output · update sends only new messages + active-key line · never use a model for sums/ceilings/layout.
`measure.py` (not judged): deletes `data/state.json`, runs `python main.py` with a hard **120-second** kill, prints seconds, calls, input/output/thinking/total tokens. Run 3×, note the numbers. Targets: full run 1 call (≈ ≤ 3,000 tokens), update 1 call (≈ ≤ 1,500 tokens).

---

## 9. Help-desk questions (judges do not answer during the build)

1. Which models are on the **small-model list**?
2. Honorarium for **all confirmed judges** or only **judges needed**? Do judges/staff get food? (We assume needed judges, and yes.)
3. How is the unseen pack / each new message delivered (append to the same text file)? Format?
4. Is an event start clock time ever given? (We use relative times if not.)

---

## 10. Setup and commands

```bash
python --version && git --version
python -m venv .venv
.venv\Scripts\activate           # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # then put your real key inside .env
python check_model.py            # one-time model access check
python main.py                   # THE judged command (full run and updates)
streamlit run app.py             # UI
python measure.py                # time + token measurement
pytest -q                        # tests
```
`.env.example`:
```
LLM_PROVIDER=gemini            # gemini | openai   (openai also covers Ollama/other OpenAI-compatible servers)
LLM_API_KEY=your_key_here
LLM_MODEL=gemini-2.5-flash-lite
LLM_BASE_URL=                  # only for openai-compatible, e.g. http://localhost:11434/v1 for Ollama
```
Note: thinking controls differ between Gemini 2.5 (thinking budget) and 3.x (thinking level); the adapter must minimise thinking for the model actually used and include any reported thinking tokens in the totals.

---

## 11. Expected results for the sample pack (TEST FIXTURE ONLY — never in source code)

| Item | Expected |
|---|---|
| Teams / headcount | 50 / **177** |
| Venue | Hall A, cap 200, Rs 120,000 (Room D too small; generator not required) |
| Food | 177 × Rs 1,200 = **Rs 212,400** (Rs 1,000 superseded; delivery free) |
| Judging | need 17 (confirmed 20); 3 teams max, 45 min per judge; honorarium **Rs 85,000** (Rs 100,000 if all 20 paid → warning) |
| Committed | 100,000 + 20,000 + 10,000 = **Rs 130,000** |
| **Projected total** | **Rs 547,400** · remaining **Rs 102,600** |
| Schedule | 240 min: Opening 15, Build 55, Prayer break 15, Lunch 30, Build 55, Judging 55 (45 + 10 late buffer), Closing 15 |
| DJ Rs 50,000 | optional, **not** in total |
| Update: printing → 15,000 | total **Rs 552,400** · remaining **Rs 97,600** · 1 `reading` call · only budget changes |
| Wrong message: 100 boxes | **Rejected** (100 < 177, short by 77); previous plan kept |

---

## 12. Definition of done
Pack read from file · one command for run and update · all five areas · six checks pass · wrong message rejected with reason · update = 1 call · full run < 2 min · trace truthful, ends with totals · UI shows plan/trace/rejections · outputs saved incl. `final_submission.txt` · tests run honestly · `git status` clean and pushed **before 1:25**.
