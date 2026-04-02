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

I used Copilot across all three phases of the project — design, implementation, and testing — but in different ways at each stage.

During design I used Copilot Chat with `#file:pawpal_system.py` to review my class skeleton and ask whether anything was missing for the scheduling requirements. That review found the missing `time_available` field on `Owner` and the fact that `generate_daily_plan()` wasn't actually enforcing a budget. Those were real gaps I had missed.

During implementation the most effective feature was **Inline Chat** directly on a method. Asking "how should this sort tasks by time as strings in HH:MM format?" right inside the editor gave me an answer I could immediately apply and tweak, without breaking my flow. It was much faster than switching to a browser.

During testing I used **Generate Tests** on the `Scheduler` class to get a starting draft, then edited each test to match my actual data model. The generated tests weren't always right out of the box — the AI didn't know my exact constructor signatures — but they gave me the right structure to work from.

The most useful prompt pattern overall was sharing a specific file and asking a targeted question about one requirement, rather than asking something open-ended like "what should I build next?" Focused input got focused output.

**b. Judgment and verification**

The clearest moment where I pushed back on an AI suggestion was around conflict detection. Copilot suggested implementing full interval overlap detection — sorting tasks by start time and checking if `start + duration` overlaps the next task's start. The logic was correct, but it was about 20 lines of additional code and introduced new edge cases (what if tasks span midnight? what about tasks with no time set?).

I decided the complexity wasn't justified for this app. The most realistic mistake a pet owner makes is scheduling two things at the exact same time, not accidentally overlapping a 30-minute walk with a feeding 20 minutes later. I kept my simpler exact-match dictionary approach, verified it with a test, and documented the tradeoff in section 2b so anyone reading the code understands the deliberate choice. That felt like the right call — not every technically correct suggestion is the right fit for the problem you're actually solving.

**c. Separate chat sessions**

Using separate chat sessions for design, implementation, and testing made a real difference. When I started a new session for testing, Copilot wasn't carrying context from the UML discussion or the earlier implementation decisions, which forced me to re-explain what I was building. That re-explanation was actually useful — it made me articulate my design choices clearly, and a couple of times I caught my own inconsistencies while typing the prompt.

If I had done everything in one long session, the context would have drifted and I think the suggestions would have been less precise. Keeping sessions focused kept the AI's suggestions relevant.

**d. Being the lead architect**

The biggest thing I learned is that AI is a fast, opinionated collaborator — not a decision-maker. It will suggest something plausible almost immediately, and if you're not careful you'll accept it just because it compiles and looks reasonable. The job of the lead architect is to evaluate every suggestion against the actual requirements, the actual users, and the actual tradeoffs — not just ask "does this work?" but "is this the right thing to build?"

In practice that meant: reading every AI-generated line before accepting it, asking why when something looked overly complex, and keeping the design goals visible so I had something to measure suggestions against. The `Scheduler` being a separate stateless class — not part of `Owner` — was my decision, not the AI's default. I pushed for it because I knew I wanted to test it independently. That kind of intentional architectural choice is exactly what the AI can't make for you.

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

I'm most satisfied with how clean the separation between `Scheduler` and the data classes ended up. Because `Scheduler` just takes a flat list of tasks and has no dependency on `Owner` or `Pet` beyond reading task attributes, I can test every scheduling behavior in complete isolation — no need to build a full owner-pet-task hierarchy for every test. That decision made the test suite much simpler to write and much easier to trust.

**b. What you would improve**

If I had another iteration, the first thing I'd add is the ability to remove or edit tasks from the UI — right now you can only add them, which gets awkward fast. I'd also replace the exact-time conflict detection with proper duration-overlap checking, now that I have a clearer sense of how complex it actually is. And I'd add a persistence button in the UI so the owner's data survives a full page refresh, not just in-session reruns.

**c. Key takeaway**

Working with AI on a real system taught me that the hardest part isn't generating code — it's knowing when to stop and think before accepting what was generated. AI is fast and confident, which makes it easy to keep moving. But moving fast in the wrong direction just means you have more to undo later. The most valuable skill I practiced in this project was slowing down at decision points — especially around architecture — and making sure I understood and agreed with every choice before it became load-bearing code.
