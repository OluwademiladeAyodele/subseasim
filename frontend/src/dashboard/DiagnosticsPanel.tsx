import { Badge } from "@/components/ui/primitives";
import { fmt, paToBarDelta } from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

export function DiagnosticsPanel({ state }: { state: SimulationState }) {
  const h = state.hydraulics;
  return (
    <div className="grid gap-3 p-3 lg:grid-cols-2" data-testid="diagnostics">
      <div>
        <h3 className="mb-1 t-eyebrow">Solver</h3>
        <dl className="grid grid-cols-[160px_1fr] gap-y-0.5">
          <dt className="text-muted">Hydraulic status</dt>
          <dd>
            <Badge tone={h.status === "failed" ? "bad" : h.status === "closed_in" ? "warn" : "ok"}>{h.status.replace("_", "-")}</Badge>
          </dd>
          <dt className="text-muted">Brent iterations</dt>
          <dd className="num">{h.iterations}</dd>
          <dt className="text-muted">Pressure residual</dt>
          <dd className="num">{h.residual_pa.toExponential(2)} Pa</dd>
          <dt className="text-muted">Net static drive F(0)</dt>
          <dd className="num">{fmt(h.driving_pressure_pa === null ? null : paToBarDelta(h.driving_pressure_pa), 2)} bar</dd>
          {h.message && (
            <>
              <dt className="text-muted">Message</dt>
              <dd className="text-bad">{h.message}</dd>
            </>
          )}
        </dl>
        <h3 className="mb-1 mt-3 t-eyebrow">Model validity checks</h3>
        {state.diagnostics.length === 0 ? (
          <p className="text-ok">All Release 1 model assumptions satisfied at the current operating point.</p>
        ) : (
          <ul className="space-y-1">
            {state.diagnostics.map((d, i) => (
              <li key={i} className="flex gap-2">
                <Badge tone={d.severity === "error" ? "bad" : d.severity === "warning" ? "warn" : "info"}>{d.severity}</Badge>
                <span>
                  <span className="num mr-1 text-dim">{d.code}</span>
                  {d.message}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="mb-1 t-eyebrow">Active models (Release 1)</h3>
        <dl className="space-y-1.5">
          {Object.entries(state.model).map(([k, v]) => (
            <div key={k}>
              <dt className="text-[12.5px] font-bold uppercase text-muted">{k}</dt>
              <dd className="text-fg">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-[12.5px] text-dim">
          Not modelled: multiphase flow, gas, hydrates, wax, slugging, pressure transients / water hammer, reservoir depletion. See docs/ENGINEERING_ASSUMPTIONS.md.
          Scenario data: {state.scenario.data_classification}.
        </p>
      </div>
    </div>
  );
}
