"""Guided-exercise framework.

An exercise is a sequence of steps:

    info        read-only content
    task        an operation the trainee performs; completion is judged by the
                backend from the SIMULATION STATE (not by button clicks) and a
                set of observations is recorded from the instruments
    prediction  the trainee predicts an outcome BEFORE acting; the correct
                answer is resolved afterwards from the recorded observations,
                so it reflects what this simulation actually did
    question    assessment question (fixed answer, or resolved from data)
    review      explanation generated from the recorded observations
    summary     final performance summary

Scoring: questions and predictions are scored separately so that the
summary distinguishes "understood the concept" from "anticipated the result".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.simulation.engine import SimulationEngine

StepKind = Literal["info", "task", "prediction", "question", "review", "summary"]
Obs = dict[str, dict[str, Any]]


@dataclass
class Option:
    id: str
    text: str


@dataclass
class Step:
    id: str
    kind: StepKind
    title: str
    body: str = ""
    # task
    condition: Callable[[SimulationEngine], bool] | None = None
    condition_hint: Callable[[SimulationEngine], str] | None = None
    record_as: str | None = None
    # prediction / question
    options: list[Option] = field(default_factory=list)
    correct: str | Callable[[Obs], str | None] | None = None
    explanation: str | Callable[[Obs], str] = ""
    # review
    review: Callable[[Obs, dict], dict] | None = None


@dataclass
class ExerciseDefinition:
    id: str
    number: int
    title: str
    scenario_id: str
    objectives: list[str]
    initial_configuration: list[str]
    instructions: list[str]
    expected_observations: list[str]
    steps: list[Step]
    capture: Callable[[SimulationEngine], dict[str, Any]]

    def summary(self) -> dict:
        return {
            "id": self.id, "number": self.number, "title": self.title, "scenario_id": self.scenario_id,
            "objectives": self.objectives, "initial_configuration": self.initial_configuration,
            "instructions": self.instructions, "expected_observations": self.expected_observations,
            "step_count": len(self.steps),
        }


class TrainingError(ValueError):
    pass


class TrainingSession:
    def __init__(self, definition: ExerciseDefinition):
        self.d = definition
        self.index = 0
        self.observations: Obs = {}
        self.responses: dict[str, dict[str, Any]] = {}
        self.completed: set[str] = set()
        self.started_wall = time.time()
        self.finished_wall: float | None = None

    @property
    def current(self) -> Step:
        return self.d.steps[self.index]

    # ------------------------------------------------------------- progress
    def update(self, engine: SimulationEngine) -> bool:
        """Evaluate the current task against the simulation. Returns True on completion."""
        s = self.current
        if s.kind != "task" or s.id in self.completed:
            return False
        if s.condition is not None and s.condition(engine):
            if s.record_as:
                self.observations[s.record_as] = self.d.capture(engine)
            self.completed.add(s.id)
            return True
        return False

    def _resolve_correct(self, s: Step) -> str | None:
        if callable(s.correct):
            return s.correct(self.observations)
        return s.correct

    def answer(self, step_id: str, choice: str) -> dict:
        s = self.current
        if s.id != step_id:
            raise TrainingError("answers are accepted for the current step only")
        if s.kind not in ("prediction", "question"):
            raise TrainingError("this step does not take an answer")
        if choice not in {o.id for o in s.options}:
            raise TrainingError(f"unknown option {choice!r}")
        if s.id in self.responses:
            raise TrainingError("this step has already been answered")
        resp: dict[str, Any] = {"choice": choice, "answered_wall": time.time()}
        if s.kind == "question":
            correct = self._resolve_correct(s)
            resp["correct_option"] = correct
            resp["correct"] = correct == choice
            resp["explanation"] = s.explanation(self.observations) if callable(s.explanation) else s.explanation
        self.responses[s.id] = resp
        self.completed.add(s.id)
        return resp

    def advance(self) -> None:
        s = self.current
        if s.kind in ("info", "review"):
            self.completed.add(s.id)
        if s.id not in self.completed:
            raise TrainingError("complete the current step before continuing")
        if self.index < len(self.d.steps) - 1:
            self.index += 1
            if self.current.kind == "summary":
                self.completed.add(self.current.id)
                self.finished_wall = time.time()

    # ----------------------------------------------------------- reporting
    def _prediction_results(self) -> list[dict]:
        out = []
        for s in self.d.steps:
            if s.kind != "prediction" or s.id not in self.responses:
                continue
            correct = self._resolve_correct(s)
            choice = self.responses[s.id]["choice"]
            out.append({
                "step_id": s.id, "title": s.title, "choice": choice,
                "choice_text": next(o.text for o in s.options if o.id == choice),
                "correct_option": correct,
                "correct_text": next((o.text for o in s.options if o.id == correct), None),
                "correct": None if correct is None else correct == choice,
                "explanation": (s.explanation(self.observations) if callable(s.explanation) else s.explanation) if correct else None,
            })
        return out

    def score(self) -> dict:
        qs = [s for s in self.d.steps if s.kind == "question"]
        q_correct = sum(1 for s in qs if self.responses.get(s.id, {}).get("correct"))
        preds = self._prediction_results()
        p_resolved = [p for p in preds if p["correct"] is not None]
        p_correct = sum(1 for p in p_resolved if p["correct"])
        return {
            "questions_correct": q_correct, "questions_total": len(qs),
            "predictions_correct": p_correct,
            "predictions_total": len([s for s in self.d.steps if s.kind == "prediction"]),
            "predictions_resolved": len(p_resolved),
        }

    def state(self, engine: SimulationEngine | None = None) -> dict:
        s = self.current
        steps = [
            {"id": st.id, "kind": st.kind, "title": st.title,
             "status": "complete" if st.id in self.completed else ("current" if i == self.index else "pending")}
            for i, st in enumerate(self.d.steps)
        ]
        cur: dict[str, Any] = {"id": s.id, "kind": s.kind, "title": s.title, "body": s.body,
                               "complete": s.id in self.completed or s.kind in ("info", "review")}
        if s.kind in ("prediction", "question"):
            cur["options"] = [{"id": o.id, "text": o.text} for o in s.options]
            cur["response"] = self.responses.get(s.id)
        if s.kind == "task" and engine is not None:
            cur["hint"] = self.task_hint(engine)
        if s.kind == "review" and s.review is not None:
            cur["review"] = s.review(self.observations, {p["step_id"]: p for p in self._prediction_results()})
        result = {
            "exercise": self.d.summary(),
            "index": self.index,
            "steps": steps,
            "current": cur,
            "observations": self.observations,
            "score": self.score(),
            "finished": self.finished_wall is not None,
        }
        if s.kind == "summary":
            result["summary"] = {
                "predictions": self._prediction_results(),
                "questions": [
                    {"step_id": st.id, "title": st.title, **{k: v for k, v in self.responses.get(st.id, {}).items() if k != "answered_wall"}}
                    for st in self.d.steps if st.kind == "question"
                ],
                "duration_s": (self.finished_wall or time.time()) - self.started_wall,
            }
        return result

    def task_hint(self, engine: SimulationEngine) -> str | None:
        s = self.current
        if s.kind == "task" and s.condition_hint is not None and s.id not in self.completed:
            return s.condition_hint(engine)
        return None
