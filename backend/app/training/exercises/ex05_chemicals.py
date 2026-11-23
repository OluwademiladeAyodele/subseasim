"""Exercise 5 - Chemical injection.

The trainee injects methanol into the tree, adjusts the metering valve,
follows the chemical down the flowline to the analysers (transport delay)
and sees that the injection rate depends on the pressure at the injection
point. All judged from the simulation; reviews from this run's readings.
"""

from __future__ import annotations

from app.training.exercises.common import Held, at, capture, fmt, is_closed, is_open, running, table, travel_hint
from app.training.framework import ExerciseDefinition, Obs, Option, Step


def _ft301(e) -> float:
    r = e.readings.get("FT-301")
    return 0.0 if r is None or r.value is None else r.value * 86400


def _at(e, tag) -> float:
    r = e.readings.get(tag)
    return 0.0 if r is None or r.value is None else float(r.value)


_inj = Held(lambda e: is_open(e, "CIV-301") and _ft301(e) > 0.5, 60)
_meter = Held(lambda e: is_open(e, "CIV-301") and at(e, "CIMV-301", 100.0), 300)
_ch50 = Held(lambda e: is_open(e, "CIV-301") and at(e, "CHK-101", 50.0), 600)


def _arrived(e) -> bool:
    return running(e) and is_open(e, "CIV-301") and _at(e, "AT-510") > 0 and _at(e, "AT-511") > 0.5 * _at(e, "AT-510")


def _hint(h: Held, tag: str, target: float, what: str):
    def hint(e):
        if running(e) and at(e, tag, target):
            return f"Hold: recorded after {h.seconds / 60:.0f} min of simulation time ({h.remaining(e):.0f} s left)."
        return travel_hint(e, tag, target, what)
    return hint


def _p_delay(obs: Obs) -> str | None:
    if "inj" not in obs or "arr" not in obs:
        return None
    d = obs["arr"]["sim_time_s"] - obs["inj"]["sim_time_s"]
    return "b" if d > 300 else "a"


def _p_delay_explain(obs: Obs) -> str:
    d = (obs["arr"]["sim_time_s"] - obs["inj"]["sim_time_s"]) / 60
    return (f"AT-510, 30 m from the tree, saw methanol almost at once ({fmt(obs['inj']['AT-510'] * 100, 2)} vol%); AT-511, 2.5 km down "
            f"the flowline, only after {d:.0f} minutes. A chemical travels WITH the production fluid: the delay is the volume of "
            "pipe between the two points divided by the flow rate.")


def _p_meter(obs: Obs) -> str | None:
    try:
        d = obs["meter"]["FT-301"] - obs["arr"]["FT-301"]
    except (KeyError, TypeError):
        return None
    return "a" if d > 0.2 else "b" if d < -0.2 else "c"


def _p_meter_explain(obs: Obs) -> str:
    return (f"FT-301 went from {fmt(obs['arr']['FT-301'], 1)} to {fmt(obs['meter']['FT-301'], 1)} m3/d: opening the metering valve "
            "removes resistance from the injection line, so more of the available pressure drives flow.")


def _p_ch(obs: Obs) -> str | None:
    try:
        d = obs["ch50"]["FT-301"] - obs["meter"]["FT-301"]
    except (KeyError, TypeError):
        return None
    return "a" if d > 0.2 else "b" if d < -0.2 else "c"


def _p_ch_explain(obs: Obs) -> str:
    m, c = obs["meter"], obs["ch50"]
    return (f"Opening the production choke lowered the pressure at the injection point (tree cavity PT-104 {fmt(m['PT-104'])} -> "
            f"{fmt(c['PT-104'])} bara), so the pump's supply pressure had more differential to push against: FT-301 went from "
            f"{fmt(m['FT-301'], 1)} to {fmt(c['FT-301'], 1)} m3/d. Injection rate = f(supply pressure - line losses - metering-valve "
            "dP - production pressure at the injection point).")


def _review_transport(obs: Obs, preds: dict) -> dict:
    v = preds.get("p_delay")
    lead = f"Your prediction: '{v['choice_text']}'. Result: '{v['correct_text']}'. " if v and v["correct"] is not None else ""
    a = obs["arr"]
    text = (lead + _p_delay_explain(obs) + f" The concentration also tells you the dose: {fmt(a['AT-511'] * 100, 2)} vol% methanol at "
            f"AT-511 with {fmt(a['FT-301'], 1)} m3/d injected into {fmt(a['FT-101'], 0)} m3/d of production. Operators use the analyser "
            "readings - not the pump setting - to confirm the chemical reached the place it protects.")
    return {"text": text}


def _review_rate(obs: Obs, preds: dict) -> dict:
    text = _p_meter_explain(obs) + " " + _p_ch_explain(obs)
    t = table(obs, [("inj", "CIV-301 opened"), ("arr", "Front at AT-511"), ("meter", "CIMV-301 100 %"), ("ch50", "Choke 50 %")],
              [("FT-301", "FT-301 m3/d", 2), ("PT-104", "PT-104 bara", 1), ("FT-101", "FT-101 m3/d", 0), ("valves.CHK-101", "Choke %", 0)])
    return {"text": text, "table": t}


EXERCISE = ExerciseDefinition(
    id="ex05_chemicals",
    number=5,
    title="Exercise 5 - Chemical injection",
    scenario_id="xt_230xp22b",
    objectives=[
        "Start methanol injection into the tree and confirm it on the flow meter (FT-301).",
        "Follow the chemical down the flowline to the analysers and explain the transport delay.",
        "Explain what sets the injection rate: supply pressure, metering valve and the production pressure at the injection point.",
    ],
    initial_configuration=["Tree workstation, single-phase producer flowing at CHK-101 30 %.",
                           "All chemical pumps running; injection valves (CIV) closed; metering valves CIMV at 50 %."],
    instructions=["Use the Chemicals page (or click a chemical line on the tree).",
                  "Use 60x - 300x while waiting for the chemical front to travel down the flowline."],
    expected_observations=["FT-301 shows injection as soon as CIV-301 opens.", "AT-511 (2.5 km) responds only after the transit time.",
                           "More metering-valve opening or lower production pressure gives more injection."],
    capture=capture,
    steps=[
        Step("intro", "info", "1 - Chemicals on a subsea tree",
             "Chemicals are pumped from the host through the umbilical and injected at the tree: methanol (hydrates), corrosion "
             "inhibitor, biocide and wax inhibitor. Each line has an injection valve (CIV) and a metering valve (CIMV). Analysers "
             "AT-510 (30 m), AT-511 (2.5 km) and AT-512 (5 km) measure methanol in the flowline."),
        Step("t_start", "task", "Start the simulation", "Press START.",
             condition=running, condition_hint=lambda e: "Press START in the top bar.", record_as="base"),
        Step("t_inj", "task", "2 - Inject methanol",
             "Open CIV-301 (methanol into the tree cavity) and watch FT-301.",
             condition=_inj, condition_hint=lambda e: travel_hint(e, "CIV-301", 100, "open it") if not is_open(e, "CIV-301")
             else "Check the methanol pump is running (Chemicals page).", record_as="inj"),
        Step("p_delay", "prediction", "Predict: the analyser 2.5 km away",
             "When will AT-511, 2.5 km down the flowline, show methanol?",
             options=[Option("a", "Immediately"), Option("b", "After a delay - the time the fluid takes to get there"), Option("c", "Never")],
             correct=_p_delay, explanation=_p_delay_explain),
        Step("t_arr", "task", "3 - Follow the chemical front",
             "Wait until the methanol reaches AT-511 (use 300x). The task completes when AT-511 reads at least half of AT-510.",
             condition=_arrived, condition_hint=lambda e: f"Methanol travelling: AT-510 {_at(e, 'AT-510') * 100:.2f} vol%, AT-511 "
             f"{_at(e, 'AT-511') * 100:.2f} vol%." if running(e) else "Press RESUME.", record_as="arr"),
        Step("r_transport", "review", "Review: chemical transport", review=_review_transport),
        Step("p_meter", "prediction", "Predict: open the metering valve",
             "You will open CIMV-301 from 50 % to 100 %. The injection rate FT-301 will:",
             options=[Option("a", "Increase"), Option("b", "Decrease"), Option("c", "Stay the same")],
             correct=_p_meter, explanation=_p_meter_explain),
        Step("t_meter", "task", "4 - Open the metering valve",
             "Set CIMV-301 to 100 % (Chemicals page) and hold.",
             condition=_meter, condition_hint=_hint(_meter, "CIMV-301", 100, "set it to 100 %"), record_as="meter"),
        Step("p_ch", "prediction", "Predict: open the production choke",
             "Opening the production choke to 50 % lowers the pressure in the tree. The methanol injection rate will:",
             options=[Option("a", "Increase"), Option("b", "Decrease"), Option("c", "Stay the same")],
             correct=_p_ch, explanation=_p_ch_explain),
        Step("t_ch50", "task", "5 - Open the choke to 50 %",
             "Set CHK-101 to 50 % and hold.",
             condition=_ch50, condition_hint=_hint(_ch50, "CHK-101", 50, "set it to 50 %"), record_as="ch50"),
        Step("r_rate", "review", "Review: what sets the injection rate", review=_review_rate),
        Step("t_stop", "task", "6 - Stop the injection",
             "Close CIV-301 and return the choke to 30 %.",
             condition=lambda e: running(e) and is_closed(e, "CIV-301") and at(e, "CHK-101", 30.0),
             condition_hint=lambda e: travel_hint(e, "CIV-301", 0, "close it") if not is_closed(e, "CIV-301")
             else travel_hint(e, "CHK-101", 30, "set it to 30 %"), record_as="stop"),
        Step("q_ci", "question", "Continuous or batch?",
             "Corrosion inhibitor is usually injected continuously; methanol mainly during start-up, shut-in and cold periods. Why?",
             options=[Option("a", "Corrosion acts all the time; hydrates form only when the fluid is cold and at high pressure"),
                      Option("b", "Methanol is too expensive to buy"), Option("c", "Corrosion inhibitor cannot be stopped")],
             correct="a", explanation="Inject each chemical when and where its risk exists: hydrate risk is highest in cold, "
                                      "high-pressure, low-flow conditions such as start-up and shut-in."),
        Step("q_limit", "question", "Injection limit",
             "The methanol pump discharge is 250 bara and the tree pressure 245 bara. What will the injection rate be?",
             options=[Option("a", "Very small: almost no differential is left to drive the chemical"),
                      Option("b", "The same as at a tree pressure of 100 bara"), Option("c", "Higher, because the pressures are high")],
             correct="a", explanation="Injection needs a differential; a chemical cannot be injected into a point at higher pressure "
                                      "than the pump can deliver there."),
        Step("summary", "summary", "Performance summary"),
    ],
)
