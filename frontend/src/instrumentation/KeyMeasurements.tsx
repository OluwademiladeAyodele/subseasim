import { Stat } from "@/components/ui/primitives";
import { displayTag } from "@/lib/tags";
import { type DisplayPrefs, FLOW_LABEL, flowFromM3s, fmt, instrumentDisplay, paToBarDelta } from "@/lib/units";
import type { InstrumentSnapshot, SimulationState } from "@/types/simulation";

/**
 * Hero metrics: the handful of numbers an operator reads first, large and
 * tabular. Driven by the scenario's instruments; never synthesised.
 */
export function KeyMeasurements({ state, prefs, onSelect }: { state: SimulationState; prefs: DisplayPrefs; onSelect?: (tag: string) => void }) {
  const h = state.hydraulics;
  const failed = h.status === "failed" || state.diagnostics.some((d) => d.severity === "error");
  const q = h.q_m3s;
  const dynamic = state.mode === "dynamic";
  const prodNodes = new Set(state.elements.filter((e) => !e.branch).flatMap((e) => [e.from, e.to]));
  const isProd = (i: InstrumentSnapshot) => !i.element && !!i.node && prodNodes.has(i.node);
  const prod = state.instruments.filter((i) => (i.type === "differential_pressure" ? true : isProd(i)));
  const pressures = prod.filter((i) => i.type === "pressure");
  const temps = prod.filter((i) => i.type === "temperature");
  const dp = prod.find((i) => i.type === "differential_pressure");
  const mp = state.multiphase;
  const pick = [pressures[1] ?? pressures[0], pressures[0], mp ? undefined : dp, temps[temps.length - 1]].filter(
    (x, i, a): x is InstrumentSnapshot => !!x && a.indexOf(x) === i,
  );
  const nodeRate = (i: InstrumentSnapshot) => (i.node ? state.nodes.find((n) => n.id === i.node)?.rate_pa_s ?? 0 : 0);
  const rate = h.max_pressure_rate_pa_s ?? 0;
  const rateBarMin = (rate * 60) / 1e5;
  const ss = state.steady_reference?.q_m3s;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Stat
        testId="kpi-flow"
        label={mp ? "Production (reservoir volume)" : dynamic ? "Flowline flow" : "Production flow"}
        value={failed ? "INVALID" : fmt(q === null ? null : flowFromM3s(q, prefs.flowUnit), 0)}
        unit={failed ? undefined : FLOW_LABEL[prefs.flowUnit]}
        tone={failed ? "fault" : "accent"}
        sub={
          failed
            ? h.message || "see diagnostics"
            : dynamic && ss != null
              ? `heading to ${fmt(flowFromM3s(ss, prefs.flowUnit), 0)} ${FLOW_LABEL[prefs.flowUnit]} (steady state)`
              : `${fmt(h.mass_flow_kg_s, 2)} kg/s · ${h.status.replace("_", "-")}`
        }
      />
      {mp && (
        <Stat
          testId="kpi-phases"
          label="Oil · gas · water (std)"
          value={fmt(mp.rates_arrival.oil_sm3_d, 0)}
          unit="Sm³/d oil"
          tone="accent"
          sub={`gas ${fmt(mp.rates_arrival.gas_sm3_d / 1000, 1)} kSm³/d · water ${fmt(mp.rates_arrival.water_sm3_d, 0)} Sm³/d at the manifold`}
        />
      )}
      {dynamic ? (
        <Stat
          testId="kpi-process"
          label="Process response"
          value={rateBarMin < 0.003 ? "Steady" : rateBarMin > 1 ? "Fast" : "Evolving"}
          tone={rateBarMin < 0.003 ? "ok" : rateBarMin > 1 ? "warn" : "info"}
          sub={`max |dP/dt| ${fmt(rateBarMin, rateBarMin < 0.1 ? 3 : 1)} bar/min${h.process_settling ? ` · after ${h.process_settling}` : ""}`}
        />
      ) : (
        <Stat
          label="Net static drive"
          value={fmt(h.driving_pressure_pa === null ? null : paToBarDelta(h.driving_pressure_pa), 1)}
          unit="bar"
          sub="P_res − P_down − ρgΔz"
        />
      )}
      {pick.map((i) => {
        const d = instrumentDisplay(i.type, i.value_si, prefs, i.display_unit);
        const r = dynamic && i.type === "pressure" ? nodeRate(i) : 0;
        return (
          <Stat
            key={i.tag}
            label={
              <span>
                <span className="num font-semibold text-fg">{displayTag(state, i.tag)}</span> · {i.description}
              </span>
            }
            value={i.value_si === null ? i.status.replace(/_/g, " ").toLowerCase() : fmt(d.value, d.digits)}
            unit={i.value_si === null ? undefined : d.unit}
            tone={i.status === "GOOD" ? "fg" : "warn"}
            trend={Math.abs(r) > 2 ? (r > 0 ? "up" : "down") : null}
            onClick={onSelect ? () => onSelect(i.tag) : undefined}
          />
        );
      })}
    </div>
  );
}
