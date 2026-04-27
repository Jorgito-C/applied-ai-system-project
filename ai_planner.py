import json
import logging
import os
from typing import Callable, Dict, List, Optional, Tuple

from pawpal_system import Owner, Scheduler, Task

LOGGER = logging.getLogger("pawpal.ai")
if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    file_handler = logging.FileHandler("pawpal_ai.log")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    LOGGER.addHandler(file_handler)

ModelCallable = Callable[[str], str]


def verify_plan_result(owner: Owner, tasks: List[Task], result: Dict) -> List[str]:
    """
    Return human-readable violations; empty list means the plan is safe to show.
    Used by tests and evaluate_ai_planner.py to measure reliability under bad model output.
    """
    violations: List[str] = []
    if not isinstance(result, dict):
        return ["result is not a dict"]

    plan = result.get("plan")
    if plan is None:
        return ["missing plan key"]
    if not isinstance(plan, list):
        return ["plan is not a list"]

    task_by_id = {t.task_id: t for t in tasks}
    total_minutes = 0
    seen_ids: set = set()

    for item in plan:
        if not isinstance(item, Task):
            violations.append(f"plan entry is not a Task: {type(item).__name__}")
            continue
        if item.task_id in seen_ids:
            violations.append(f"duplicate task_id in plan: {item.task_id}")
        seen_ids.add(item.task_id)

        original = task_by_id.get(item.task_id)
        if original is None:
            violations.append(f"unknown task_id in plan: {item.task_id}")
        elif original.completed:
            violations.append(f"completed task_id in plan: {item.task_id}")

        total_minutes += item.duration

    if total_minutes > owner.time_available:
        violations.append(
            f"plan total {total_minutes} min exceeds owner budget {owner.time_available} min"
        )

    return violations


class AgenticPlanner:
    """Plan pet-care tasks with an AI-first, guardrailed workflow."""

    def __init__(self, model_call: Optional[ModelCallable] = None):
        self.model_call = model_call or self._build_gemini_model_call()

    def plan_day(self, owner: Owner, tasks: List[Task]) -> Dict:
        """
        Agentic workflow:
        1) Plan candidate task IDs with AI.
        2) Validate and repair unsafe/incomplete output.
        3) Fall back to deterministic planner when needed.
        """
        if not tasks:
            return {
                "source": "none",
                "plan": [],
                "skipped": [],
                "notes": ["No tasks available to schedule."],
            }

        task_map = {task.task_id: task for task in tasks}
        fallback_plan = Scheduler(tasks).generate_daily_plan(owner.time_available)
        fallback_ids = [task.task_id for task in fallback_plan]

        ai_result = self._attempt_ai_plan(owner, tasks)
        if ai_result is None:
            LOGGER.info("AI unavailable. Using deterministic fallback.")
            return self._build_response(
                source="fallback",
                selected_ids=fallback_ids,
                tasks=tasks,
                notes=["Gemini unavailable or API key missing. Used rule-based planner."],
            )

        selected_ids, ai_notes = ai_result
        validated_ids, guardrail_notes = self._validate_selected_ids(
            selected_ids=selected_ids,
            task_map=task_map,
            time_budget=owner.time_available,
        )

        if not validated_ids:
            LOGGER.warning("AI output did not pass guardrails. Falling back.")
            return self._build_response(
                source="fallback",
                selected_ids=fallback_ids,
                tasks=tasks,
                notes=ai_notes + guardrail_notes + ["Guardrails rejected AI plan."],
            )

        return self._build_response(
            source="gemini",
            selected_ids=validated_ids,
            tasks=tasks,
            notes=ai_notes + guardrail_notes,
        )

    def _attempt_ai_plan(
        self, owner: Owner, tasks: List[Task]
    ) -> Optional[Tuple[List[int], List[str]]]:
        if self.model_call is None:
            return None

        prompt = self._build_prompt(owner, tasks)
        LOGGER.info("Calling model for planning. task_count=%s", len(tasks))
        try:
            response_text = self.model_call(prompt)
            parsed = json.loads(response_text)
        except Exception as exc:  # guardrail: never crash scheduler from model failure
            LOGGER.exception("Model planning failed: %s", exc)
            return None

        selected_ids = parsed.get("selected_task_ids", [])
        rationale = parsed.get("rationale", "")
        checks = parsed.get("checks", [])
        notes = []
        if rationale:
            notes.append(f"AI rationale: {rationale}")
        if checks:
            notes.append(f"AI checks: {', '.join(str(item) for item in checks)}")
        return selected_ids, notes

    def _build_prompt(self, owner: Owner, tasks: List[Task]) -> str:
        serialized_tasks = [
            {
                "task_id": task.task_id,
                "pet": task.pet.name,
                "task_type": task.task_type,
                "duration": task.duration,
                "priority": task.priority,
                "due_date": task.due_date.isoformat(),
                "due_time": task.due_time,
                "frequency": task.frequency,
                "completed": task.completed,
            }
            for task in tasks
            if not task.completed
        ]
        return (
            "You are scheduling pet care tasks.\n"
            f"Time budget (minutes): {owner.time_available}\n"
            "Return strict JSON only with keys:\n"
            "- selected_task_ids: array of integers\n"
            "- rationale: short string\n"
            "- checks: array of strings\n"
            "Rules:\n"
            "1) Pick only IDs from provided tasks.\n"
            "2) Do not exceed total duration budget.\n"
            "3) Prefer higher priority and earlier due time.\n"
            "4) Exclude completed tasks.\n"
            f"Tasks JSON: {json.dumps(serialized_tasks)}"
        )

    def _validate_selected_ids(
        self, selected_ids: List[int], task_map: Dict[int, Task], time_budget: int
    ) -> Tuple[List[int], List[str]]:
        notes: List[str] = []
        if not isinstance(selected_ids, list):
            return [], ["Guardrail: selected_task_ids was not a list."]

        cleaned_ids: List[int] = []
        seen = set()
        for item in selected_ids:
            if not isinstance(item, int):
                continue
            if item in seen:
                continue
            task = task_map.get(item)
            if task is None:
                continue
            if task.completed:
                continue
            cleaned_ids.append(item)
            seen.add(item)

        minutes = 0
        budgeted_ids: List[int] = []
        for task_id in cleaned_ids:
            task = task_map[task_id]
            if minutes + task.duration <= time_budget:
                budgeted_ids.append(task_id)
                minutes += task.duration
            else:
                notes.append(
                    f"Guardrail: dropped task {task_id} to fit {time_budget}-minute budget."
                )

        if not budgeted_ids:
            notes.append("Guardrail: no valid tasks remained after validation.")
        return budgeted_ids, notes

    def _build_response(
        self, source: str, selected_ids: List[int], tasks: List[Task], notes: List[str]
    ) -> Dict:
        selected_set = set(selected_ids)
        selected = [task for task in tasks if task.task_id in selected_set]
        skipped = [task for task in tasks if not task.completed and task.task_id not in selected_set]
        selected_sorted = sorted(
            selected, key=lambda task: (-task.priority, task.due_date, task.due_time or "99:99")
        )
        return {
            "source": source,
            "plan": selected_sorted,
            "skipped": skipped,
            "notes": notes,
        }

    def _build_gemini_model_call(self) -> Optional[ModelCallable]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None

        try:
            import google.generativeai as genai
        except Exception as exc:  # pragma: no cover - import depends on environment
            LOGGER.warning("google.generativeai unavailable: %s", exc)
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        def _call(prompt: str) -> str:
            response = model.generate_content(prompt)
            return (response.text or "").strip()

        return _call
