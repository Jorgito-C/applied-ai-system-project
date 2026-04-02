# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

The three core actions a user should be able to perform in PawPal+:

1. **Enter owner and pet information** — The user provides basic details about themselves (name, available time per day) and their pet (name, species, age). This context anchors every scheduling decision; without it, the system has no way to apply constraints or personalize the plan.

2. **Add and manage care tasks** — The user creates, edits, and removes pet care tasks such as walks, feedings, medication, grooming, and enrichment activities. Each task carries at minimum a duration (how long it takes) and a priority level (how critical it is), so the scheduler has the data it needs to reason about the day.

3. **Generate and view a daily schedule** — The user triggers the scheduler, which fits tasks into the available time window in priority order and returns a concrete daily plan. The plan should also include a brief explanation of why tasks were included or excluded, so the owner understands the tradeoffs at a glance.

The initial UML design uses four classes:

- **`Owner`** — the top-level entity. Holds the owner's id, name, and (after revision) available time per day in minutes. Owns a list of `Pet` objects and is responsible for persistence: saving and loading the entire object graph to/from JSON.

- **`Pet`** — represents a single animal. Stores id, name, species, and age. Owns a list of `Task` objects and exposes `add_task` / `get_tasks` so that the owner and scheduler can interact with a pet's workload without reaching into its internals directly.

- **`Task`** — the atomic unit of pet care. Carries everything the scheduler needs to reason about one care item: `task_type` (walk, feeding, meds, etc.), `duration` in minutes, `priority` (higher = more important), `due_date`, `due_time`, `frequency` (daily/weekly), and a `completed` flag. It holds a back-reference to its `Pet` so the scheduler can label tasks by pet without a separate lookup.

- **`Scheduler`** — stateless service class that operates on a flat list of `Task` objects. Responsible for sorting, filtering, conflict detection, recurring-task generation, and producing the daily plan. Intentionally separated from `Owner` and `Pet` so scheduling logic can be tested independently of data ownership.

**b. Design changes**

After an AI review of the skeleton (`#file:pawpal_system.py`), three issues were identified and addressed:

1. **Added `time_available` to `Owner`** — The README lists "time available" as a first-class constraint, but the original `Owner` had no such field. Without it the scheduler had no time budget to enforce. Added `time_available: int` (minutes per day, default 120) to `Owner.__init__`, `to_dict`, and `load_from_json`.

2. **Made `generate_daily_plan()` actually respect a time budget** — The original implementation just called `sort_tasks_by_priority()` and returned every task. That is a sorted list, not a plan. Updated it to accept an optional `time_available` parameter and use a greedy loop: add tasks in priority order until the budget is exhausted. This aligns with the stated requirement to "consider constraints."

3. **Guarded `max()` against an empty task list in `mark_task_complete()`** — `max(existing_task.task_id ...)` raises `ValueError` on an empty sequence. Added an `if self.tasks else 1` fallback so the method cannot crash when the list is unexpectedly empty.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

- What constraints does your scheduler consider (for example: time, priority, preferences)?
- How did you decide which constraints mattered most?

**b. Tradeoffs**

- Describe one tradeoff your scheduler makes.
- Why is that tradeoff reasonable for this scenario?

---

## 3. AI Collaboration

**a. How you used AI**

- How did you use AI tools during this project (for example: design brainstorming, debugging, refactoring)?
- What kinds of prompts or questions were most helpful?

**b. Judgment and verification**

- Describe one moment where you did not accept an AI suggestion as-is.
- How did you evaluate or verify what the AI suggested?

---

## 4. Testing and Verification

**a. What you tested**

- What behaviors did you test?
- Why were these tests important?

**b. Confidence**

- How confident are you that your scheduler works correctly?
- What edge cases would you test next if you had more time?

---

## 5. Reflection

**a. What went well**

- What part of this project are you most satisfied with?

**b. What you would improve**

- If you had another iteration, what would you improve or redesign?

**c. Key takeaway**

- What is one important thing you learned about designing systems or working with AI on this project?
