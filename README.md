# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Smarter Scheduling

The `Scheduler` class goes beyond a basic task list with four algorithmic features:

- **Sorting** — `sort_tasks_by_time()` orders tasks chronologically by due date and time using a `sorted()` lambda key. `sort_tasks_by_priority()` sorts by descending priority, then by date/time as a tiebreaker.
- **Filtering** — `filter_tasks_by_pet(pet_name)` returns only tasks belonging to a specific pet. `filter_tasks_by_status(completed)` returns pending or finished tasks so the owner can see exactly what's left in the day.
- **Recurring tasks** — `mark_task_complete(task_id)` automatically generates the next occurrence when a task is marked done. Daily tasks roll forward one day; weekly tasks roll forward seven days using Python's `timedelta`.
- **Conflict detection** — `get_conflict_warnings()` scans the task list for any two tasks that share the same date and time slot and returns human-readable warning messages instead of crashing.

## Testing PawPal+

Run the full test suite with:

```bash
python -m pytest
```

The suite lives in `test/test_pawpal.py` and covers five behaviors:

| Test | What it checks |
|---|---|
| `test_mark_complete_changes_task_status` | Calling `mark_complete()` flips the task's `completed` flag from `False` to `True` |
| `test_add_task_increases_pet_task_count` | `pet.add_task()` actually appends to the pet's task list |
| `test_sort_tasks_by_time_returns_chronological_order` | Tasks added out of order come back sorted earliest-first |
| `test_daily_task_completion_creates_next_day_task` | Completing a daily task auto-generates the next occurrence with `due_date + 1 day` |
| `test_conflict_detection_flags_same_date_and_time` | Two tasks at the same date/time slot produce a readable warning message |

**Confidence level: ★★★★☆**
The core scheduling behaviors are well covered and all 5 tests pass. I'm docking one star because the suite doesn't yet test edge cases like a pet with no tasks, a time budget of zero, or full round-trip persistence through JSON.

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.
