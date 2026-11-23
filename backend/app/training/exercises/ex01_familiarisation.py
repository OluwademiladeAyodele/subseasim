"""Exercise 1 - Workstation familiarisation.

A guided tour of the Christmas tree workstation: the arrangement of the
production bore, wing, choke, annulus, chemical lines and hydraulics; tags
and transmitters; reading live values; the speed control; and a first valve
operation (the swab valve) with its pressure response.
"""

from __future__ import annotations

from app.training.exercises.common import Held, bins, capture, fmt, is_closed, is_open, running, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step

_sv = Held(lambda e: is_open(e, "SV-101"), 120)
_sv0 = Held(lambda e: is_closed(e, "SV-101"), 120)


def _q_read(obs: Obs) -> str | None:
    return bins((obs.get("base") or {}).get("PT-104"), [100, 150, 200], ["a", "b", "c", "d"])


def _q_read_explain(obs: Obs) -> str:
    return (f"PT-104 read {fmt(obs['base']['PT-104'])} bara when you started. Values on the panels are live: they are the "
            "simulated transmitter readings, with their own response time and resolution.")


def _p_sv(obs: Obs) -> str | None:
    if "sv" not in obs:
        return None
    s = obs["sv"]
    return "a" if abs(s["PT-105"] - s["PT-104"]) <= 2.0 else "b"


def _p_sv_explain(obs: Obs) -> str:
    b, s = obs["base"], obs["sv"]
    return (f"PT-105 (tree cap, above the swab valve) went from {fmt(b['PT-105'])} to {fmt(s['PT-105'])} bara and now matches the "
            f"cavity PT-104 ({fmt(s['PT-104'])} bara): the open swab valve joined the two volumes.")


def _q_trap_explain(obs: Obs) -> str:
    c = obs.get("sv0") or {}
    return (f"After SV-101 closed, PT-105 stayed at {fmt(c.get('PT-105'))} bara: the fluid above the closed valve is trapped and keeps "
            "its pressure until it is bled off.")


EXERCISE = ExerciseDefinition(
    id="ex01_familiarisation",
    number=1,
    title="Exercise 1 - Workstation familiarisation",
    scenario_id="xt_230xp22b",
    objectives=[
        "Find your way around the Christmas tree workstation: production bore, wing and choke, annulus, chemical lines, hydraulics.",
        "Identify valves and transmitters by their tags and read live values.",
        "Use the simulation speed control.",
        "Operate a first valve and read the pressure response.",
    ],
    initial_configuration=["Tree workstation, single-phase producer flowing at CHK-101 30 %."],
    instructions=["Keep the Christmas tree page open beside this panel.", "Click any valve or transmitter to inspect it."],
    expected_observations=["Open valves are teal, closed valves red.", "Opening the swab valve equalises the tree cap with the cavity."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - The workstation",
             "The Christmas tree page is your main screen. In the middle is the vertical production bore: SCSSV-101 (deep in the well), "
             "PMV-101 (production master valve), the tree cavity, SV-101 (swab valve) and the tree cap at the top. The production wing "
             "goes right through PWV-101 (production wing valve) to the choke CHK-101 and down to the flowline and manifold. On the left "
             "is the A-annulus with AMV-101, AWV-101, the crossover XOV-101 and the service line (SLV-101). Chemical injection lines "
             "enter from the right of the bore; the hydraulic selector valves are at the bottom right."),
        Step("t_start", "task", "Start the simulation",
             "Press START in the top bar. The clock T+ shows simulated time.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="base"),
        Step("q_pmv", "question", "Valves on the bore",
             "Going up the production bore from the well, which valve do you meet first ON THE TREE?",
             options=[Option("a", "PMV-101 (production master valve)"), Option("b", "PWV-101 (production wing valve)"),
                      Option("c", "CHK-101 (production choke)"), Option("d", "SV-101 (swab valve)")],
             correct="a", explanation="SCSSV-101 is below the tree, in the tubing. On the tree the master valve comes first; the wing "
                                      "valve is on the side outlet, the swab valve above."),
        Step("q_tag", "question", "Transmitter panels",
             "Which panel shows pressure and temperature in the tree cavity between PMV-101 and PWV-101?",
             options=[Option("a", "PTT-104 (PT-104 and TT-104)"), Option("b", "PTT-001"), Option("c", "PT-404"), Option("d", "PDT-101")],
             correct="a", explanation="PTT panels show a pressure (PT) and temperature (TT) transmitter at the same point. 0xx tags are "
                                      "downhole, 1xx the production bore and wing, 2xx the flowline, 3xx chemicals, 4xx the annulus."),
        Step("q_read", "question", "Read a live value",
             "Look at PTT-104 on the tree. In which range was PT-104 when you started?",
             options=[Option("a", "Below 100 bara"), Option("b", "100 - 150 bara"), Option("c", "150 - 200 bara"), Option("d", "Above 200 bara")],
             correct=_q_read, explanation=_q_read_explain),
        Step("q_colour", "question", "Colours",
             "What does a RED valve symbol mean on the tree?",
             options=[Option("a", "Closed"), Option("b", "Open"), Option("c", "Alarm")],
             correct="a", explanation="Teal = open, red = closed (see the legend). A faded line carries no flow; a chemical line takes its "
                                      "chemical's colour while injecting."),
        Step("q_pdt", "question", "Differential pressure",
             "PDT-101 shows the pressure differential across which component?",
             options=[Option("a", "The production choke CHK-101"), Option("b", "The SCSSV"), Option("c", "The annulus master valve")],
             correct="a", explanation="PDT-101 = pressure upstream minus downstream of the choke (PT-102 - PT-103)."),
        Step("t_speed", "task", "2 - The speed control",
             "Set the simulation speed to 60x in the top bar. Valves still travel at their real speed in SIMULATED time - you just "
             "wait less.",
             condition=lambda e: running(e) and e.time_scale == 60.0,
             condition_hint=lambda e: "Click 60x in the top bar.", record_as="speed"),
        Step("p_sv", "prediction", "Predict: open the swab valve",
             "The tree cap above SV-101 (PT-105) is at a lower pressure than the cavity (PT-104). When you open SV-101, PT-105 will:",
             options=[Option("a", "Equalise with PT-104"), Option("b", "Stay as it is")],
             correct=_p_sv, explanation=_p_sv_explain),
        Step("t_sv", "task", "3 - Open the swab valve",
             "Click SV-101 on the tree, press Open, and watch PT-105.",
             condition=_sv, condition_hint=lambda e: travel_hint(e, "SV-101", 100, "open it") if not is_open(e, "SV-101")
             else f"Hold ({_sv.remaining(e):.0f} s).", record_as="sv"),
        Step("t_sv0", "task", "4 - Close it again",
             "Close SV-101.",
             condition=_sv0, condition_hint=lambda e: travel_hint(e, "SV-101", 0, "close it") if not is_closed(e, "SV-101")
             else f"Hold ({_sv0.remaining(e):.0f} s).", record_as="sv0"),
        Step("q_trap", "question", "Trapped pressure",
             "After SV-101 closed, what did PT-105 do?",
             options=[Option("a", "Kept the pressure it had (trapped)"), Option("b", "Dropped back at once")],
             correct=lambda obs: None if "sv0" not in obs else ("a" if abs(obs["sv0"]["PT-105"] - obs["sv"]["PT-105"]) <= 2.0 else "b"),
             explanation=_q_trap_explain),
        Step("summary", "summary", "Performance summary"),
    ],
)
