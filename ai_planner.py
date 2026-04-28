import json
import logging
import os
from pathlib import Path
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
_AUTO_MODEL = object()


def _append_trace(steps: List[Dict], label: str, detail: str = "") -> None:
    """Record one observable step in the agent decision chain (stretch: multi-step trace)."""
    steps.append({"step": len(steps) + 1, "label": label, "detail": detail})


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

    def __init__(self, model_call: Optional[ModelCallable] = _AUTO_MODEL):
        self.last_error: Optional[str] = None
        if model_call is _AUTO_MODEL:
            self.model_call = self._build_gemini_model_call()
        else:
            # Explicit None means force deterministic mode (no model).
            self.model_call = model_call

    def plan_day(self, owner: Owner, tasks: List[Task]) -> Dict:
        """
        Agentic workflow:
        1) Plan candidate task IDs with AI.
        2) Validate and repair unsafe/incomplete output.
        3) Fall back to deterministic planner when needed.

        Each run appends an observable ``steps`` trace (tool-style phases) for UI/CLI.
        """
        steps: List[Dict] = []
        self.last_error = None

        if not tasks:
            _append_trace(steps, "Observe", "No tasks attached — nothing to schedule.")
            return {
                "source": "none",
                "plan": [],
                "skipped": [],
                "notes": ["No tasks available to schedule."],
                "steps": steps,
            }

        task_map = {task.task_id: task for task in tasks}
        incomplete = [t for t in tasks if not t.completed]
        _append_trace(
            steps,
            "Tool: list_tasks",
            f"{len(tasks)} total tasks, {len(incomplete)} incomplete (by completed flag).",
        )
        _append_trace(
            steps,
            "Tool: read_owner_budget",
            f"time_available={owner.time_available} minutes for {owner.name!r}.",
        )

        fallback_plan = Scheduler(tasks).generate_daily_plan(owner.time_available)
        fallback_ids = [task.task_id for task in fallback_plan]
        fb_minutes = sum(t.duration for t in fallback_plan)
        _append_trace(
            steps,
            "Tool: baseline_plan (Scheduler)",
            f"Greedy fallback IDs {fallback_ids} (~{fb_minutes} min) if AI path fails.",
        )

        ai_result = self._attempt_ai_plan(owner, tasks, steps)
        if ai_result is None:
            LOGGER.info("AI unavailable. Using deterministic fallback.")
            _append_trace(
                steps,
                "Decide",
                "Use deterministic Scheduler output (model unavailable or parse error).",
            )
            reason = self.last_error or self._diagnose_unavailable_reason()
            return self._build_response(
                source="fallback",
                selected_ids=fallback_ids,
                tasks=tasks,
                notes=[f"{reason} Used rule-based planner."],
                steps=steps,
            )

        selected_ids, ai_notes = ai_result
        validated_ids, guardrail_notes = self._validate_selected_ids(
            selected_ids=selected_ids,
            task_map=task_map,
            time_budget=owner.time_available,
            steps=steps,
        )

        if not validated_ids:
            LOGGER.warning("AI output did not pass guardrails. Falling back.")
            _append_trace(
                steps,
                "Decide",
                "Guardrails emptied the plan — use Scheduler fallback IDs.",
            )
            return self._build_response(
                source="fallback",
                selected_ids=fallback_ids,
                tasks=tasks,
                notes=ai_notes + guardrail_notes + ["Guardrails rejected AI plan."],
                steps=steps,
            )

        _append_trace(
            steps,
            "Decide",
            f"Accept Gemini plan: task_ids={validated_ids}.",
        )
        return self._build_response(
            source="gemini",
            selected_ids=validated_ids,
            tasks=tasks,
            notes=ai_notes + guardrail_notes,
            steps=steps,
        )

    def _attempt_ai_plan(
        self, owner: Owner, tasks: List[Task], steps: List[Dict]
    ) -> Optional[Tuple[List[int], List[str]]]:
        if self.model_call is None:
            _append_trace(steps, "Model: skip", "No model_call configured (no API key / client).")
            return None

        prompt = self._build_prompt(owner, tasks)
        _append_trace(
            steps,
            "Tool: build_prompt",
            f"Prompt length {len(prompt)} chars; includes {len([t for t in tasks if not t.completed])} open tasks.",
        )
        LOGGER.info("Calling model for planning. task_count=%s", len(tasks))
        _append_trace(steps, "Model: generate", "Requesting strict JSON: selected_task_ids, rationale, checks.")
        try:
            response_text = self.model_call(prompt)
            preview = (response_text[:400] + "…") if len(response_text) > 400 else response_text
            _append_trace(steps, "Model: raw_text (truncated)", preview)
            parsed = json.loads(self._extract_json_candidate(response_text))
        except Exception as exc:  # guardrail: never crash scheduler from model failure
            LOGGER.exception("Model planning failed: %s", exc)
            self.last_error = f"Gemini error: {str(exc)}"
            _append_trace(steps, "Parse: json_error", str(exc)[:300])
            return None

        _append_trace(steps, "Parse: json_ok", f"Top-level keys: {list(parsed.keys())}")
        selected_ids = parsed.get("selected_task_ids", [])
        rationale = parsed.get("rationale", "")
        checks = parsed.get("checks", [])
        _append_trace(
            steps,
            "Tool: extract_ids",
            f"selected_task_ids type={type(selected_ids).__name__}; preview={str(selected_ids)[:200]}",
        )
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
        self,
        selected_ids: List[int],
        task_map: Dict[int, Task],
        time_budget: int,
        steps: List[Dict],
    ) -> Tuple[List[int], List[str]]:
        notes: List[str] = []
        if not isinstance(selected_ids, list):
            _append_trace(steps, "Validate: reject", "selected_task_ids is not a list.")
            return [], ["Guardrail: selected_task_ids was not a list."]

        cleaned_ids: List[int] = []
        seen = set()
        dropped_unknown = 0
        dropped_completed = 0
        dropped_dup = 0
        dropped_type = 0
        for item in selected_ids:
            if not isinstance(item, int):
                dropped_type += 1
                continue
            if item in seen:
                dropped_dup += 1
                continue
            task = task_map.get(item)
            if task is None:
                dropped_unknown += 1
                continue
            if task.completed:
                dropped_completed += 1
                continue
            cleaned_ids.append(item)
            seen.add(item)

        _append_trace(
            steps,
            "Validate: filter_ids",
            f"Kept {len(cleaned_ids)} id(s); dropped non-int={dropped_type}, dup={dropped_dup}, "
            f"unknown_id={dropped_unknown}, completed={dropped_completed}.",
        )

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
        _append_trace(
            steps,
            "Validate: enforce_budget",
            f"After budget walk: ids={budgeted_ids}, planned_minutes={minutes} (cap {time_budget}).",
        )
        return budgeted_ids, notes

    def _build_response(
        self,
        source: str,
        selected_ids: List[int],
        tasks: List[Task],
        notes: List[str],
        steps: List[Dict],
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
            "steps": steps,
        }

    def _build_gemini_model_call(self) -> Optional[ModelCallable]:
        api_key = self._resolve_api_key()
        if not api_key:
            return None

        # Try modern + legacy names to avoid 404 model mismatches.
        candidate_models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
        ]

        # SDK path 1: deprecated but still common package.
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)

            def _call(prompt: str) -> str:
                last_error: Optional[Exception] = None
                for model_name in candidate_models:
                    try:
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(
                            prompt,
                            generation_config={"response_mime_type": "application/json"},
                        )
                        text = (response.text or "").strip()
                        if text:
                            return text
                    except Exception as exc:
                        last_error = exc
                        LOGGER.warning("Model %s failed: %s", model_name, exc)
                if last_error is not None:
                    raise last_error
                return ""

            return _call
        except Exception as exc:
            LOGGER.warning("google.generativeai unavailable: %s", exc)

        # SDK path 2: new official package.
        try:
            from google import genai as genai_v2

            client = genai_v2.Client(api_key=api_key)

            def _call(prompt: str) -> str:
                last_error: Optional[Exception] = None
                for model_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                        )
                        text = (getattr(response, "text", None) or "").strip()
                        if text:
                            return text
                    except Exception as exc:
                        last_error = exc
                        LOGGER.warning("Model %s failed: %s", model_name, exc)
                if last_error is not None:
                    raise last_error
                return ""

            return _call
        except Exception as exc:
            LOGGER.warning("google.genai unavailable: %s", exc)
            return None

    def _resolve_api_key(self) -> Optional[str]:
        """Read API key from env first, then local env files."""
        env_key = os.getenv("GEMINI_API_KEY")
        if env_key:
            return env_key.strip()

        for filename in (".env.local", ".env"):
            path = Path(filename)
            if not path.exists():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    raw = line.strip()
                    if not raw or raw.startswith("#") or "=" not in raw:
                        continue
                    key, value = raw.split("=", 1)
                    if key.strip() == "GEMINI_API_KEY":
                        return value.strip().strip('"').strip("'")
            except Exception as exc:
                LOGGER.warning("Failed reading %s: %s", filename, exc)

        return None

    def _extract_json_candidate(self, text: str) -> str:
        """
        Accept plain JSON or markdown-fenced JSON and return the best JSON substring.
        """
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 3:
                cleaned = "\n".join(lines[1:-1]).strip()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            return cleaned
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    def _diagnose_unavailable_reason(self) -> str:
        """Best-effort human-readable reason when model path is unavailable."""
        if not self._resolve_api_key():
            return "Gemini API key not found."

        try:
            import google.generativeai  # noqa: F401
            return "Gemini client unavailable for this request."
        except Exception:
            pass

        try:
            from google import genai  # noqa: F401
            return "Gemini client unavailable for this request."
        except Exception:
            return "Gemini SDK not installed in this Python environment."
