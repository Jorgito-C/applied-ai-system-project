#!/usr/bin/env python3
"""
Stress-check the agentic planner and print a short reliability summary.

Run (no API key required; uses a flaky mock model):

    python evaluate_ai_planner.py

Exit code 0 only if every trial passes invariant checks.
"""

from __future__ import annotations

from datetime import date

from ai_planner import AgenticPlanner, verify_plan_result
from pawpal_system import Owner, Pet, Task


def _fixture() -> tuple[Owner, list[Task]]:
    owner = Owner(owner_id=1, name="Eval", time_available=60)
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    owner.add_pet(pet)
    t1 = Task(
        task_id=1,
        pet=pet,
        task_type="Walk",
        duration=25,
        priority=5,
        due_date=date.today(),
        due_time="08:00",
        frequency="daily",
    )
    t2 = Task(
        task_id=2,
        pet=pet,
        task_type="Feed",
        duration=20,
        priority=4,
        due_date=date.today(),
        due_time="09:00",
        frequency="once",
    )
    t3 = Task(
        task_id=3,
        pet=pet,
        task_type="Meds",
        duration=30,
        priority=3,
        due_date=date.today(),
        due_time="10:00",
        frequency="once",
    )
    owner.add_task(t1)
    owner.add_task(t2)
    owner.add_task(t3)
    tasks = owner.get_all_tasks()
    return owner, tasks


def main() -> None:
    owner, tasks = _fixture()

    responses = [
        "not valid json {{{",
        '{"selected_task_ids": "oops"}',
        '{"selected_task_ids":[999,1]}',
        '{"selected_task_ids":[1,2,3]}',
        '{"selected_task_ids":[3,2,1]}',
        '{"selected_task_ids":[2,1],"rationale":"ok","checks":["budget"]}',
    ]
    idx = 0

    def flaky_model(_prompt: str) -> str:
        nonlocal idx
        text = responses[idx % len(responses)]
        idx += 1
        return text

    trials = 36
    failures = 0
    by_source: dict[str, int] = {}

    planner = AgenticPlanner(model_call=flaky_model)

    for _ in range(trials):
        result = planner.plan_day(owner, tasks)
        source = str(result.get("source", "unknown"))
        by_source[source] = by_source.get(source, 0) + 1
        bad = verify_plan_result(owner, tasks, result)
        if bad:
            failures += 1
            print("FAIL:", bad)
            print("  source:", source)
            print("  plan ids:", [t.task_id for t in result.get("plan", [])])

    print()
    print("--- Reliability summary (mock stress) ---")
    print(f"Trials: {trials}")
    print(f"Invariant failures: {failures}")
    print(f"By source: {by_source}")
    print()
    print(
        "Plain-English line for writeups: "
        f"{trials - failures} of {trials} mock runs stayed within budget and only "
        "referenced real tasks; flaky JSON and hallucinated IDs were absorbed by "
        "guardrails or fallback scheduling."
    )

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
