from datetime import date, timedelta
from pawpal_system import Owner, Pet, Task, Scheduler
from ai_planner import AgenticPlanner, verify_plan_result


def test_mark_complete_changes_task_status():
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    task = Task(
        task_id=1,
        pet=pet,
        task_type="Walk",
        duration=30,
        priority=3,
        due_date=date.today(),
        due_time="08:00",
        frequency="daily",
    )

    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_add_task_increases_pet_task_count():
    pet = Pet(pet_id=1, name="Eevie", species="Cat", age=5)
    task = Task(
        task_id=2,
        pet=pet,
        task_type="Feed",
        duration=10,
        priority=5,
        due_date=date.today(),
        due_time="07:30",
        frequency="once",
    )

    assert len(pet.tasks) == 0
    pet.add_task(task)
    assert len(pet.tasks) == 1


def test_sort_tasks_by_time_returns_chronological_order():
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)

    task1 = Task(
        task_id=1,
        pet=pet,
        task_type="Medication",
        duration=5,
        priority=4,
        due_date=date.today(),
        due_time="09:00",
        frequency="once",
    )

    task2 = Task(
        task_id=2,
        pet=pet,
        task_type="Morning Walk",
        duration=30,
        priority=3,
        due_date=date.today(),
        due_time="08:00",
        frequency="daily",
    )

    task3 = Task(
        task_id=3,
        pet=pet,
        task_type="Feed Breakfast",
        duration=10,
        priority=5,
        due_date=date.today(),
        due_time="07:30",
        frequency="once",
    )

    scheduler = Scheduler([task1, task2, task3])
    sorted_tasks = scheduler.sort_tasks_by_time()

    assert [task.due_time for task in sorted_tasks] == ["07:30", "08:00", "09:00"]


def test_daily_task_completion_creates_next_day_task():
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    today = date.today()

    task = Task(
        task_id=1,
        pet=pet,
        task_type="Morning Walk",
        duration=30,
        priority=3,
        due_date=today,
        due_time="08:00",
        frequency="daily",
    )

    scheduler = Scheduler([task])
    new_task = scheduler.mark_task_complete(1)

    assert task.completed is True
    assert new_task is not None
    assert new_task.task_type == "Morning Walk"
    assert new_task.due_date == today + timedelta(days=1)
    assert new_task.due_time == "08:00"
    assert new_task.completed is False


def test_conflict_detection_flags_same_date_and_time():
    pet1 = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    pet2 = Pet(pet_id=2, name="Eevie", species="Cat", age=5)
    today = date.today()

    task1 = Task(
        task_id=1,
        pet=pet1,
        task_type="Morning Walk",
        duration=30,
        priority=3,
        due_date=today,
        due_time="08:00",
        frequency="daily",
    )

    task2 = Task(
        task_id=2,
        pet=pet2,
        task_type="Feed Breakfast",
        duration=10,
        priority=5,
        due_date=today,
        due_time="08:00",
        frequency="once",
    )

    scheduler = Scheduler([task1, task2])
    warnings = scheduler.get_conflict_warnings()

    assert len(warnings) == 1
    assert "Conflict detected" in warnings[0]
    assert "08:00" in warnings[0]


def test_agentic_planner_falls_back_without_model():
    owner = Owner(owner_id=1, name="Minh", time_available=45)
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    owner.add_pet(pet)

    task1 = Task(
        task_id=1,
        pet=pet,
        task_type="Walk",
        duration=30,
        priority=5,
        due_date=date.today(),
        due_time="08:00",
        frequency="daily",
    )
    task2 = Task(
        task_id=2,
        pet=pet,
        task_type="Feed",
        duration=20,
        priority=4,
        due_date=date.today(),
        due_time="09:00",
        frequency="once",
    )
    owner.add_task(task1)
    owner.add_task(task2)

    planner = AgenticPlanner(model_call=None)
    result = planner.plan_day(owner, owner.get_all_tasks())

    assert result["source"] == "fallback"
    assert [task.task_id for task in result["plan"]] == [1]
    assert "steps" in result and len(result["steps"]) >= 4


def test_agentic_planner_guardrails_drop_invalid_ids():
    owner = Owner(owner_id=1, name="Minh", time_available=60)
    pet = Pet(pet_id=1, name="Eevie", species="Cat", age=5)
    owner.add_pet(pet)

    task1 = Task(
        task_id=10,
        pet=pet,
        task_type="Medication",
        duration=20,
        priority=5,
        due_date=date.today(),
        due_time="07:00",
        frequency="daily",
    )
    task2 = Task(
        task_id=11,
        pet=pet,
        task_type="Grooming",
        duration=30,
        priority=3,
        due_date=date.today(),
        due_time="08:00",
        frequency="once",
    )
    owner.add_task(task1)
    owner.add_task(task2)

    def fake_model_call(_: str) -> str:
        return (
            '{"selected_task_ids":[999,10,10,11],"rationale":"test","checks":["budget"]}'
        )

    planner = AgenticPlanner(model_call=fake_model_call)
    result = planner.plan_day(owner, owner.get_all_tasks())

    assert result["source"] == "gemini"
    assert [task.task_id for task in result["plan"]] == [10, 11]


def test_planner_invariants_hold_under_flaky_model():
    owner = Owner(owner_id=1, name="Eval", time_available=60)
    pet = Pet(pet_id=1, name="Sofi", species="Dog", age=3)
    owner.add_pet(pet)
    owner.add_task(
        Task(
            task_id=1,
            pet=pet,
            task_type="Walk",
            duration=25,
            priority=5,
            due_date=date.today(),
            due_time="08:00",
            frequency="daily",
        )
    )
    owner.add_task(
        Task(
            task_id=2,
            pet=pet,
            task_type="Feed",
            duration=20,
            priority=4,
            due_date=date.today(),
            due_time="09:00",
            frequency="once",
        )
    )
    owner.add_task(
        Task(
            task_id=3,
            pet=pet,
            task_type="Meds",
            duration=30,
            priority=3,
            due_date=date.today(),
            due_time="10:00",
            frequency="once",
        )
    )
    tasks = owner.get_all_tasks()

    responses = [
        "not valid json",
        '{"selected_task_ids": "oops"}',
        '{"selected_task_ids":[999,1]}',
        '{"selected_task_ids":[1,2,3]}',
        '{"selected_task_ids":[2,1]}',
    ]
    idx = 0

    def flaky_model(_prompt: str) -> str:
        nonlocal idx
        text = responses[idx % len(responses)]
        idx += 1
        return text

    planner = AgenticPlanner(model_call=flaky_model)
    for _ in range(30):
        result = planner.plan_day(owner, tasks)
        assert verify_plan_result(owner, tasks, result) == []