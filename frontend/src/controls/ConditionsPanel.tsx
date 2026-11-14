import { useEffect, useState } from "react";

import { Button, Input } from "@/components/ui/primitives";
import {
  type DisplayPrefs,
  cpToPas,
  cToK,
  baraToPa,
  kToC,
  paToBara,
  pasToCp,
  piFieldToSi,
  piSiToField,
  pressureFromPa,
  pressureToPa,
} from "@/lib/units";
import type { SimulationState } from "@/types/simulation";

interface Props {
  state: SimulationState;
  prefs: DisplayPrefs;
  onBoundary: (body: Record<string, number>) => Promise<boolean>;
  onFluid: (body: Record<string, number>) => Promise<boolean>;
}

type Field = { key: string; label: string; unit: string; value: string };

function useForm(initial: Record<string, number>, deps: unknown[]) {
  const [values, setValues] = useState<Record<string, string>>({});
  useEffect(() => {
    setValues(Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, Number.isFinite(v) ? String(+v.toFixed(4)) : ""])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [values, (k: string, v: string) => setValues((s) => ({ ...s, [k]: v }))] as const;
}

function FieldRow({ f, onChange, invalid }: { f: Field; onChange: (v: string) => void; invalid: boolean }) {
  return (
    <label className="grid grid-cols-[1fr_96px_64px] items-center gap-2 py-0.5">
      <span className="text-muted">{f.label}</span>
      <Input aria-label={f.label} inputMode="decimal" value={f.value} aria-invalid={invalid} onChange={(e) => onChange(e.target.value)} />
      <span className="text-[11px] text-dim">{f.unit}</span>
    </label>
  );
}

const parse = (s: string) => (s.trim() === "" ? NaN : Number(s));

export function ConditionsPanel({ state, prefs, onBoundary, onFluid }: Props) {
  const b = state.boundary;
  const f = state.fluid;
  const ref = prefs.pressureRef;

  const [bv, setB] = useForm(
    {
      p_res: pressureFromPa(b.reservoir_pressure_pa, ref),
      j: piSiToField(b.productivity_index_si),
      t_res: kToC(b.reservoir_temperature_k),
      p_down: pressureFromPa(b.downstream_pressure_pa, ref),
    },
    [b.reservoir_pressure_pa, b.productivity_index_si, b.reservoir_temperature_k, b.downstream_pressure_pa, ref, state.scenario.id],
  );
  const [fv, setF] = useForm(
    { rho: f.density_kg_m3, mu: pasToCp(f.viscosity_pas), cp: f.specific_heat_j_kgk, pb: paToBara(f.bubble_point_pressure_pa) },
    [f.density_kg_m3, f.viscosity_pas, f.specific_heat_j_kgk, f.bubble_point_pressure_pa, state.scenario.id],
  );

  const bFields: Field[] = [
    { key: "p_res", label: "Reservoir pressure", unit: ref, value: bv.p_res ?? "" },
    { key: "j", label: "Productivity index", unit: "(m³/d)/bar", value: bv.j ?? "" },
    { key: "t_res", label: "Reservoir temperature", unit: "°C", value: bv.t_res ?? "" },
    { key: "p_down", label: "Downstream (arrival) pressure", unit: ref, value: bv.p_down ?? "" },
  ];
  const fFields: Field[] = [
    { key: "rho", label: "Density", unit: "kg/m³", value: fv.rho ?? "" },
    { key: "mu", label: "Dynamic viscosity", unit: "cP", value: fv.mu ?? "" },
    { key: "cp", label: "Specific heat", unit: "J/(kg·K)", value: fv.cp ?? "" },
    { key: "pb", label: "Bubble-point pressure", unit: "bara", value: fv.pb ?? "" },
  ];
  const bInvalid = (k: string) => !Number.isFinite(parse(bv[k] ?? ""));
  const fInvalid = (k: string) => !Number.isFinite(parse(fv[k] ?? ""));

  const applyBoundary = () =>
    onBoundary({
      reservoir_pressure_pa: pressureToPa(parse(bv.p_res), ref),
      productivity_index_si: piFieldToSi(parse(bv.j)),
      reservoir_temperature_k: cToK(parse(bv.t_res)),
      downstream_pressure_pa: pressureToPa(parse(bv.p_down), ref),
    });
  const applyFluid = () =>
    onFluid({
      density_kg_m3: parse(fv.rho),
      viscosity_pas: cpToPas(parse(fv.mu)),
      specific_heat_j_kgk: parse(fv.cp),
      bubble_point_pressure_pa: baraToPa(parse(fv.pb)),
    });

  return (
    <div className="space-y-4 p-3" data-testid="conditions-panel">
      <div>
        <h3 className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-dim">Reservoir &amp; boundary conditions</h3>
        {bFields.map((x) => (
          <FieldRow key={x.key} f={x} invalid={bInvalid(x.key)} onChange={(v) => setB(x.key, v)} />
        ))}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[11px] text-dim">Pressures in {ref === "bara" ? "bar absolute" : "bar gauge (ref. 1.01325 bar)"}</span>
          <Button variant="primary" size="sm" disabled={bFields.some((x) => bInvalid(x.key))} onClick={applyBoundary}>Apply conditions</Button>
        </div>
        <p className="mt-2 text-[11px] text-dim">
          Reservoir pressure drives inflow through the IPR; it is not the pressure in the tree. The solver finds the rate at which inflow balances the
          system resistance down to the downstream pressure.
        </p>
      </div>
      <div>
        <h3 className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-dim">Fluid (constant-property liquid)</h3>
        <p className="mb-1 text-[11px] text-warn">{f.name} — illustrative data</p>
        {fFields.map((x) => (
          <FieldRow key={x.key} f={x} invalid={fInvalid(x.key)} onChange={(v) => setF(x.key, v)} />
        ))}
        <div className="mt-2 flex justify-end">
          <Button variant="primary" size="sm" disabled={fFields.some((x) => fInvalid(x.key))} onClick={applyFluid}>Apply fluid</Button>
        </div>
        <p className="mt-2 text-[11px] text-dim">
          Below the bubble point gas would evolve; the single-phase model then flags its results as invalid rather than modelling two-phase flow.
        </p>
      </div>
    </div>
  );
}
