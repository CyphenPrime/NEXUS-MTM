# OpsWeave — Project Context and Engineering Rules (for the Antigravity Agent) — FINAL

**Read this file AND README.md completely before every substantial change.**
Authority order: (1) official brief `Hackathon_Students_Brief_Final.pdf` → (2) this file → (3) README.md → (4) existing code (never assumed correct).
If instructions conflict, protect the official requirement and say so. Do not invent requirements. Do not edit README.md or CONTEXT.md unless the human asks.

## 1. What we are building
OpsWeave: a message-driven planner for a **4-hour physical hackathon in Islamabad, 150 students, 50 teams**. It reads a text file of messages (English / Roman Urdu), plans **venue, schedule, food, judging, budget**, validates with Python rules, and prints a truthful model-call trace. Later messages update the plan.
Promises: every decision has evidence · every rejected message has a reason · every hard rule is checked by code · every real model call is traced · missing information stays *unknown*.

## 2. Two timelines — never mix them
* **Planned event** (what the software plans): 4 hours, 15-minute prayer break (from the sample pack), judges evaluate teams.
* **Team build day** (NOT part of the plan): 10:00 build starts · 1:25 code freeze · 1:30 test run · 2:30–4:30 judges visit tables. These must never appear as event-schedule constraints.

## 3. Mandatory behaviours
1. Read every message from a text file exactly as given; no facts or messages typed in code.
2. Same single command for every message: `python main.py` — **no arguments, no flags, no hints, no manual edits**.
3. Print the trace: each model call numbered, with model name, exactly one area tag from {reading, venue, schedule, food, judging, budget}, input, output, provider-reported tokens. End with total tokens.
4. Accept new messages after the first run and update the existing plan.
5. On conflict, keep the plan valid and print the reason in the trace.
Limits: full run ≤ 2 minutes (hard cut-off); update ≤ 5 model calls and ≤ 1 minute. UI scored: plan, trace, rejected messages. Six plan checks: correct figures, within budget, venue fits, schedule valid, enough judges, all areas covered.
Disqualification: misreported tokens/models/areas · facts or messages typed in code · code changed after the 1:25 freeze.

## 4. Architecture decisions (do not change casually)
* **One `reading` model call per full run and one per update.** Python does arithmetic, planning, validation, conflict handling. No per-area model planners.
* Model code only in `core/llm.py` (providers: `gemini`, and `openai` = any OpenAI-compatible server incl. Ollama via `LLM_BASE_URL`). Secrets only in `.env` (gitignored).
* One shared flow in `core/pipeline.py` used by `main.py`. The Streamlit UI never has its own pipeline: it edits `data/messages.txt` and runs `python main.py` as a subprocess.
* Fact = structured item: id, kind, name, value/price, unit, facilities, source message id, verbatim evidence, status (`active | superseded | rejected | informational | unverified`). Kinds are the closed list in README §4.
* Supersede: same kind+name (normalised lowercase), later message date wins; file order if no dates. History is kept, never deleted.
* Rejection: apply candidate to a **copy** → re-plan → validate. Previously valid plan becoming invalid, or a hard rule broken → reject, keep the old plan, record reason.
* `main.py` decides update vs reset by comparing saved message hashes with the file: saved list is a prefix and there are new messages → update with only the new ones; identical → no model call; otherwise → reset and full run.
* Anything not stated stays unknown. Planning defaults (opening/lunch/closing minutes) live only in `config.py`, labelled "planning default".

## 5. Domain rules (Python)
Exactly as README §5: `teams`, `judges_needed = ceil(teams/judge_max_teams)`, `headcount = students + staff + judges_needed` (sample: 150+10+17 = **177**; shown as an assumption); venue = cheapest eligible (capacity, availability, mandatory facilities; never assume facilities); food = newest valid price × headcount + fees, order below headcount invalid; judging = confirmed ≥ needed, caps respected, late judge is a risk not a cancellation, honorarium for judges needed (warn about all-confirmed cost); budget = committed + selected, proposals outside the total until `approve`, each cost once, caps enforced, integer PKR; schedule = fixed order of blocks, required breaks included and never moved, no overlaps, total = duration. A plan with a failed or unresolved hard check is never marked valid.

## 6. Trace rules
* Record only real calls with real provider usage. Missing usage → `unavailable` (never estimated). Retries are separate numbered calls. System events (rejections, supersedes, routing, validation) are labelled `SYSTEM EVENT`, not numbered as calls.
* The printed trace ENDS with `TOTAL TOKENS` (summed from recorded calls only; if usage is missing show the known subtotal and the count unavailable). Include provider-reported thinking tokens.

## 7. Token discipline
Batch all messages in one call · short JSON keys · JSON-only · temperature 0 · thinking off/minimal · output cap 1500 · update call gets only new messages + active-keys line · no model call for maths or layout · measure with `measure.py` (120 s kill).

## 8. Files and Git
Commit: source, README, CONTEXT, tests, `.env.example`, `requirements.txt`, `data/messages.txt`, `.streamlit/config.toml`. Gitignore: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `outputs/`, `data/state.json`, `.pytest_cache/`. Before the 1:30 test: `git status` clean, `git log -1` equals the submitted hash. **No code change after 1:25.**

## 9. Prohibited shortcuts
Hardcoding pack facts/prices/capacities/names/expected answers (also in prompts as pre-filled answers) · matching exact sample phrases · trusting the latest message blindly · model-made arithmetic · counting a cost twice · counting a proposal as committed · assuming a facility · treating a late judge as cancelled · moving fixed times · extra model calls without reason · hiding retries · fabricating model names/outputs/tokens/test results · presenting a mock as a real model result · marking an invalid plan valid · committing keys · claiming tests passed without running them · changing code after the freeze · adding command-line flags.

## 10. Testing honesty
Label tests: unit · offline (saved model-style JSON fixtures) · live model · timed end-to-end. Offline tests are not proof of model performance. Synthetic test data must be labelled. Cover unseen cases: Roman Urdu, venue unavailable, new mandatory facility, delivery fee, judge withdrawal, budget change, second break, proposal approval, irrelevant message, plausible-but-wrong message.

## 11. Definition of done
- [ ] Pack read from `data/messages.txt`; nothing hardcoded
- [ ] `python main.py` handles first run, appended messages, and a different pack (reset)
- [ ] Five areas present; six checks pass on the sample pack (README §11)
- [ ] Wrong message rejected with reason, plan kept; valid change accepted
- [ ] Update = 1 `reading` call; full run < 2 min; update < 1 min
- [ ] Trace truthful, ends with token totals; `outputs/trace.json` and `outputs/final_submission.txt` saved
- [ ] UI shows plan, trace, rejected messages; upload / run / send-message / download work
- [ ] Tests run and honestly reported; `measure.py` numbers recorded
- [ ] Clean `git status`, pushed, hash recorded before 1:25

## 12. Priorities
1) Official requirements 2) No hardcoded facts 3) Evidence + safe conflict handling 4) Correct five-area plan 5) Python for maths/rules 6) 1-call updates 7) Truthful trace 8) Time limits 9) Clear UI 10) Small code all three teammates can explain.
