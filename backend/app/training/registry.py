"""Registry of the guided training exercises (the intern curriculum)."""

from __future__ import annotations

from app.training.exercises.ex01_familiarisation import EXERCISE as EX01
from app.training.exercises.ex02_startup import EXERCISE as EX02
from app.training.exercises.ex03_choke import EXERCISE as EX03
from app.training.exercises.ex04_shutin import EXERCISE as EX04
from app.training.exercises.ex05_chemicals import EXERCISE as EX05
from app.training.exercises.ex06_annulus import EXERCISE as EX06
from app.training.exercises.ex07_integrated import EXERCISE as EX07
from app.training.exercises.ex08_leaktest import EXERCISE as EX08
from app.training.exercises.ex09_hydraulics import EXERCISE as EX09
from app.training.framework import ExerciseDefinition

EXERCISES: dict[str, ExerciseDefinition] = {e.id: e for e in (EX01, EX02, EX03, EX04, EX05, EX06, EX07, EX08, EX09)}


def get_exercise(exercise_id: str) -> ExerciseDefinition:
    if exercise_id not in EXERCISES:
        raise KeyError(exercise_id)
    return EXERCISES[exercise_id]
