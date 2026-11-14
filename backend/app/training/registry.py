"""Registry of available training exercises."""

from __future__ import annotations

from app.training.exercises.ex03_choke import EXERCISE as EX03
from app.training.framework import ExerciseDefinition

EXERCISES: dict[str, ExerciseDefinition] = {e.id: e for e in (EX03,)}


def get_exercise(exercise_id: str) -> ExerciseDefinition:
    if exercise_id not in EXERCISES:
        raise KeyError(exercise_id)
    return EXERCISES[exercise_id]
