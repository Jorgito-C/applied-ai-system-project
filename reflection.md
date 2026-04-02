# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

The three core actions I wanted a user to be able to do in PawPal+:

1. **Enter owner and pet information** — I needed a way to capture who the owner is and basic pet details before anything else. Without that context, the scheduler has nothing to work with. The owner's available time per day is especially important because it drives every scheduling decision.

2. **Add and manage care tasks** — I wanted the user to be able to create tasks like walks, feedings, medication, and grooming, each with a duration and a priority. That's the minimum data the scheduler needs to reason about the day.

3. **Generate and view a daily schedule** — The whole point of the app is to produce a concrete plan. I wanted the output to not just list tasks but also explain what got included and what got left out, so the owner understands the tradeoffs.

For my initial UML I designed four classes:

- **`Owner`** — the top-level container. I gave it the owner's id, name, and available time per day in minutes. It owns the list of pets and handles all persistence (saving and loading to JSON).

- **`Pet`** — represents a single animal. I kept it simple: id, name, species, age, and a list of tasks. I gave it `add_task` and `get_tasks` so other parts of the system don't have to reach into its internals directly.

- **`Task`** — the atomic unit of care. I put everything the scheduler needs here: `task_type`, `duration`, `priority`, `due_date`, `due_time`, `frequency`, and a `completed` flag. I also added a back-reference to the owning `Pet` so the scheduler can label tasks without a separate lookup.

- **`Scheduler`** — I kept this as a separate service class that just takes a flat list of tasks. I didn't want scheduling logic mixed into `Owner` or `Pet` because I knew I'd want to test it independently.

**b. Design changes**

When I ran an AI review on the skeleton, three gaps came up that I agreed with and fixed:

1. **Added `time_available` to `Owner`** — My original `Owner` had no time field at all, which meant the scheduler had no budget to enforce. I added `time_available: int` (defaulting to 120 minutes) to `__init__`, `to_dict`, and `load_from_json`.

2. **Fixed `generate_daily_plan()` to actually respect the time budget** — My original version just called `sort_tasks_by_priority()` and returned everything. That's a sorted list, not a plan. I rewrote it to greedily add tasks in priority order until the budget runs out.

3. **Guarded `mark_task_complete()` against an empty task list** — The `max()` call would crash with a `ValueError` if `self.tasks` was ever empty. I added an `if self.tasks else 1` fallback to prevent that.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

My scheduler considers two constraints: **priority** (1–5, where 5 is most critical) and the **owner's daily time budget** in minutes. `generate_daily_plan()` picks tasks in descending priority order until the budget is exhausted. I decided to weight priority over time because skipping a medication is a much bigger deal than skipping an enrichment activity, even if both would fit in the schedule.

**b. Tradeoffs**

My conflict detector only flags tasks that share an exact `(due_date, due_time)` match — it doesn't check for overlapping durations. So if I schedule a 30-minute walk at 08:00 and a feeding at 08:20, the system won't warn me even though they physically overlap.

I think this is acceptable for now. The app is meant for a single owner with a small number of pets, and the most common mistake I'm guarding against is accidentally putting two things at exactly the same time. Full overlap detection would mean sorting tasks and comparing intervals, which adds a lot of complexity for an edge case most users won't hit often. I'd rather ship something simple and correct than something complete and brittle.

---

## 3. AI Collaboration

**a. How you used AI**

I used AI mostly for design brainstorming and catching gaps I missed. The most useful prompts were ones where I shared the actual file and asked specific questions, like "does this class have everything it needs to support time-based scheduling?" That kind of targeted review surfaced the missing `time_available` field and the broken `generate_daily_plan()` much faster than re-reading my own code would have.

**b. Judgment and verification**

When AI suggested adding full interval-overlap detection to the conflict checker, I didn't take it. The suggestion was technically correct, but it added a lot of code for a scenario that's unlikely in a single-owner app. I kept my simpler exact-match approach and documented the tradeoff instead. I verified my version was sufficient by writing a test that confirmed two tasks at the same exact time trigger a warning, which covers the realistic case I actually care about.

---

## 4. Testing and Verification

**a. What you tested**

I wrote five tests:
- `test_mark_complete_changes_task_status` — confirms that calling `mark_complete()` flips the flag
- `test_add_task_increases_pet_task_count` — confirms that `pet.add_task()` actually appends to the list
- `test_sort_tasks_by_time_returns_chronological_order` — confirms tasks come back in time order regardless of insertion order
- `test_daily_task_completion_creates_next_day_task` — confirms that completing a daily task auto-generates tomorrow's copy with the correct date
- `test_conflict_detection_flags_same_date_and_time` — confirms a warning is raised when two tasks share the same slot

These felt like the most important behaviors to lock down because they're the ones where a silent bug would give the owner wrong information without any error.

**b. Confidence**

I'm fairly confident the core scheduling behavior is correct for the happy path. The main edge cases I'd want to test next are: what happens if the owner's time budget is 0, what happens when all tasks have the same priority, and whether `load_from_json` fully round-trips a schedule without data loss.

---

## 5. Reflection

**a. What went well**

I'm most satisfied with how clean the separation between `Scheduler` and the data classes ended up. Because `Scheduler` just takes a list of tasks, I can test it in complete isolation without setting up a full owner and pet hierarchy every time.

**b. What you would improve**

If I had another pass, I'd replace the exact-time conflict detection with proper interval overlap checking. I'd also add a way to remove or edit tasks from the UI — right now you can only add them.

**c. Key takeaway**

The biggest thing I learned is that AI is most useful when you give it something concrete to react to. Vague prompts got me generic answers. Sharing the actual file and asking "what's missing for this specific requirement?" got me actionable feedback I could act on immediately.
