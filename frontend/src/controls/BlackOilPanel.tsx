/**
 * Three-phase fluid inputs and fluid-model selection. Values are sent to the
 * backend black-oil model; nothing is calculated here.
 */
import { useEffect, useState } from "react";

import { Button, Input, Segmented } from "@/components/ui/primitives";
import { fmt, paToBara } from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

interface Props {
  state: SimulationState;
  onBlackOil: (body: Record<string, number | string>) => Promise<boolean>;
  onFluidModel: (m: "single_phase" | "black_oil") => Promise<boolean>;
}

type Key = "producing_gor_sm3_sm3" | "water_cut_pct" | "oil_api" | "gas_specific_gravity" | "water_salinity_wt_pct";

const FIELDS: { key: Key; label: string; unit: string; min: number; max: number; hint: string }[] = [
  { key: "producing_gor_sm3_sm3", label: "Producing GOR", unit: "Sm³/Sm³", min: 0, max: 2000, hint: "gas-oil ratio at standard conditions" },
  { key: "water_cut_pct", label: "Water cut", unit: "%", min: 0, max: 98, hint: "water / (oil + water) at standard conditions" },
  { key: "oil_api", label: "Oil gravity", unit: "°API", min: 10, max: 70, hint: "stock-tank oil" },
  { key: "gas_specific_gravity", label: "Gas specific gravity", unit: "air = 1", min: 0.55, max: 1.5, hint: "separator gas" },
  { key: "water_salinity_wt_pct", label: "Water salinity", unit: "wt% NaCl", min: 0, max: 26, hint: "formation water" },
];

export function BlackOilPanel({ state, onBlackOil, onFluidModel }: Props) {
  const mp = state.multiphase;
  const available = state.fluid_models ?? ["single_phase"];
  const current = state.fluid_model ?? "single_phase";
  const init = (): Record<Key, string> => ({
    producing_gor_sm3_sm3: mp ? String(+mp.params.producing_gor_sm3_sm3.toFixed(2)) : "",
    water_cut_pct: mp ? String(+(mp.params.water_cut * 100).toFixed(2)) : "",
    oil_api: mp ? String(mp.params.oil_api) : "",
    gas_specific_gravity: mp ? String(mp.params.gas_specific_gravity) : "",
    water_salinity_wt_pct: mp ? String(mp.params.water_salinity_wt_pct) : "",
  });
  const [v, setV] = useState<Record<Key, string>>(init);
  const sig = mp ? `${mp.params.producing_gor_sm3_sm3}|${mp.params.water_cut}|${mp.params.oil_api}|${mp.params.gas_specific_gravity}|${mp.params.water_salinity_wt_pct}` : "";
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setV(init()), [sig]);
  const num = (k: Key) => (v[k].trim() === "" ? NaN : Number(v[k]));
  const bad = (k: Key) => {
    const f = FIELDS.find((x) => x.key === k)!;
    const x = num(k);
    return !Number.isFinite(x) || x < f.min || x > f.max;
  };
  const apply = () =>
    onBlackOil({
      producing_gor_sm3_sm3: num("producing_gor_sm3_sm3"),
      water_cut: num("water_cut_pct") / 100,
      oil_api: num("oil_api"),
      gas_specific_gravity: num("gas_specific_gravity"),
      water_salinity_wt_pct: num("water_salinity_wt_pct"),
    });

  return (
    <div data-testid="black-oil-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="t-eyebrow">Fluid model</h3>
        <Segmented
          label="Fluid model"
          size="sm"
          value={current}
          testIdPrefix="fluid-model"
          options={[
            { value: "single_phase", label: "Single-phase (simplified)" },
            { value: "black_oil", label: "Three-phase black oil", title: available.includes("black_oil") ? undefined : "not configured for this scenario" },
          ]}
          disabled={!available.includes("black_oil")}
          onChange={(m) => m !== current && onFluidModel(m)}
        />
      </div>
      <p className="mt-1 text-[12.5px] text-dim">Switching the fluid model restarts the scenario from its initial conditions.</p>
      {mp ? (
        <>
          <p className="mt-3 text-[12.5px] text-warn">{mp.params.name} — generic correlations, illustrative unless taken from a PVT report</p>
          {FIELDS.map((f) => (
            <label key={f.key} className="grid grid-cols-[1fr_96px_74px] items-center gap-2 py-0.5" title={f.hint}>
              <span className="text-muted">{f.label}</span>
              <Input aria-label={f.label} inputMode="decimal" value={v[f.key]} aria-invalid={bad(f.key)} onChange={(e) => setV((s) => ({ ...s, [f.key]: e.target.value }))} />
              <span className="text-[12.5px] text-dim">{f.unit}</span>
            </label>
          ))}
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-dim">
              Bubble point at reservoir temperature: <span className="num text-fg">{fmt(paToBara(mp.params.bubble_point_reservoir_pa), 1)} bara</span>
            </span>
            <Button variant="primary" size="sm" disabled={FIELDS.some((f) => bad(f.key))} onClick={apply}>
              Apply fluid
            </Button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-muted">Multiphase correlation</span>
            <Segmented
              label="Multiphase correlation"
              size="sm"
              value={mp.correlation}
              testIdPrefix="correlation"
              options={[
                { value: "beggs_brill", label: "Beggs & Brill" },
                { value: "no_slip", label: "No-slip (homogeneous)" },
              ]}
              onChange={(c) => onBlackOil({ correlation: c })}
            />
          </div>
          <p className="mt-2 text-[12.5px] text-dim">
            GOR and water cut change the fluid <em>entering</em> the well — it travels up the tubing and along the flowline with the flow. Oil gravity, gas
            gravity and salinity re-characterise the fluid everywhere at once.
          </p>
        </>
      ) : (
        <p className="mt-3 text-[12.5px] text-dim">
          The single-phase model treats the produced fluid as a constant-property liquid and flags results invalid below the bubble point.
          {available.includes("black_oil") ? " Select the three-phase model to simulate oil, gas and water." : " This scenario has no three-phase fluid configured."}
        </p>
      )}
    </div>
  );
}
