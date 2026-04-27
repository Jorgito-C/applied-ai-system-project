# Model card — PawPal+ (Applied AI final)

This document is my **model / system card**: what the AI piece is, how I use it, what can go wrong, how I tested it, and how I collaborated with AI tools while staying responsible for the design.

---

## 1. Base project (what existed before the AI layer)

**Name:** **PawPal+** — my CodePath **Applied AI (AI 110)** project from **Modules 1–3**, carried forward in this repo.

**What it was for:** I modeled a pet owner’s day as code: an **`Owner`** (with a daily minute budget), **`Pet`** objects, and **`Task`** rows (type, duration, priority, due date/time, recurrence). A stateless **`Scheduler`** sorted and filtered tasks, detected **same-slot** time conflicts, advanced **recurring** tasks when marked complete, and built a **greedy daily plan** that respects priority until the time budget runs out. Streamlit (`app.py`) and a CLI demo (`main.py`) sit on top of that core (`pawpal_system.py`).

The base goal was **trustworthy scheduling logic**, not “AI for AI’s sake.”

---

## 2. AI component (what actually runs)

**Provider / model:** **Google Gemini** (`gemini-1.5-flash`) via `google-generativeai`, configured with **`GEMINI_API_KEY`** from the environment.

**Role in the product:** The model does **not** mutate my objects directly. It returns **strict JSON** with `selected_task_ids`, `rationale`, and `checks`. My **`AgenticPlanner`** (`ai_planner.py`) then:

1. Builds a **baseline** plan with the deterministic `Scheduler` (always available as fallback).
2. Calls Gemini with a prompt that lists **only open tasks** and the owner’s **minute budget**.
3. **Parses** JSON; on failure, logs and falls back.
4. **Validates** IDs (exist, not completed, fit budget in order).
5. **Decides:** accept Gemini’s cleaned list, or use the baseline.

**Stretch — observable multi-step reasoning:** Every run records a **`steps`** trace (numbered phases: list tasks, read budget, baseline plan, build prompt, model call, truncated raw text, parse, validate, final **Decide**). You can see it in the Streamlit expander **“Agent trace (multi-step reasoning)”** and in `main.py` console output.

---

## 3. Intended use

**In scope:** Helping a single owner **prioritize** same-day pet care when time is limited, and surfacing **obvious scheduling mistakes** (e.g. two tasks at the same clock time).

**Out of scope / not claims:** This is **not** veterinary or behavioral advice. Priority numbers are **human judgments**, not medical triage.

---

## 4. Data sent to the model

The prompt includes: owner **time budget**, and for each **incomplete** task: `task_id`, pet name, task type, duration, priority, due date/time, frequency, completion flag.

**Privacy note:** Pet names and task labels go to the vendor API when Gemini is enabled. For a production app I would minimize fields, avoid free-text health notes in prompts, and keep keys **server-side** (not in client bundles).

---

## 5. Limitations and biases

- **Priority bias:** Both the greedy scheduler and the model are steered by my numeric **priority** field. That encodes my assumptions (e.g. medication often high), not objective medical truth.
- **Conflict detection is narrow:** I only flag tasks sharing the **exact** `(date, due_time)`. **Overlapping durations** (walk 08:00–08:30 vs feed 08:15) are not detected by design—documented as a trade-off.
- **Model variability:** Even with guardrails, Gemini can propose different **valid** subsets on different days; the UI shows **source** (`gemini` vs `fallback`) and the **trace** so I’m not hiding which path ran.
- **Single-owner assumption:** No multi-household permissions or shared calendars.

---

## 6. Misuse and mitigations

**Misuse:** Treating output as a substitute for a vet; ignoring conflict banners; leaking an API key in a public repo or client.

**Mitigations I applied:** Guardrails + deterministic fallback so a bad model response doesn’t corrupt state; **`pawpal_ai.log`** for failures; invariant checks in **`verify_plan_result()`** and stress runs in **`evaluate_ai_planner.py`**; README + this card stating limitations; local-only key via environment variable.

---

## 7. Testing results (what I measured)

**Automated:** `python -m pytest` — **8** tests including scheduler behavior, planner **fallback** when no model is configured, **guardrails** on bogus IDs, a **flaky-model loop** (30 iterations) proving invariants never break, and a minimum **agent trace** length on fallback.

**Stress script:** `python evaluate_ai_planner.py` — mock model cycles through invalid JSON and bad IDs; last run reported **0 invariant failures** over **36** trials, with a plain-English summary line suitable for writeups.

**Human:** I still read conflict warnings, **planner source**, and the **agent trace** before I treat a schedule as “final.”

**Plain summary:** Automated tests pass consistently; the model’s most common failure modes are **boring** (bad JSON / bad IDs) and are caught. The scarier case—**plausible** but wrong plans—is why I rely on explicit validation and traceability, not vibes.

---

## 8. AI collaboration (helpful vs flawed)

**Helpful suggestion:** Early on, Copilot-style review noticed my **`Owner`** had **no time budget** and that **`generate_daily_plan()`** returned a sorted list instead of actually **stopping** when minutes ran out. Those were real bugs in naming vs behavior.

**Flawed suggestion:** The same tools pushed **full interval-overlap** conflict detection. Technically attractive, but it would have pulled in midnight and “no time set” edge cases I wasn’t ready to own. I kept **exact-slot** warnings, added a test, and documented the gap.

**Cursor Agent mode:** I used it to implement the **multi-step trace** across `ai_planner.py`, `app.py`, and `main.py` without breaking guardrails—I still reviewed every step list and test outcome myself.

---

## 9. Reproducibility

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GEMINI_API_KEY="..."   # optional; omit to exercise fallback
streamlit run app.py
python -m pytest
python evaluate_ai_planner.py
```

---

## 10. Related docs

- **`README.md`** — setup, architecture (diagram + Mermaid), features, sample interactions, reliability section.
- **`reflection.md`** — longer narrative on design, trade-offs, and ethics (**section 6** expands misuse and bias).
- **`assets/system-architecture.png`** — system diagram required for submission.
