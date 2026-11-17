/**
 * Sand & choke inputs: every site-specific value used by the sand production,
 * detection and choke-erosion models. Empty = not available: the dependent
 * prediction reports "unavailable" instead of using a made-up value.
 */
import { CheckCircle2, CircleAlert, Download, FileUp, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useWorkstation } from "@/app/context";
import { PageBody } from "@/app/PageBody";
import { Badge, Button, Input, Panel, Select } from "@/components/ui/primitives";
import type { SandChokeInputs } from "@/types/sand";

type Draft = SandChokeInputs;

function NumField({ label, unit, value, onChange, hint, testId }: { label: string; unit?: string; value: number | null; onChange: (v: number | null) => void; hint?: string; testId?: string }) {
  const [text, setText] = useState(value == null ? "" : String(value));
  useEffect(() => setText(value == null ? "" : String(value)), [value]);
  const bad = text.trim() !== "" && !Number.isFinite(Number(text));
  return (
    <label className="grid grid-cols-[1fr_110px_70px] items-center gap-2 py-0.5" title={hint}>
      <span className="text-[13px] text-muted">{label}</span>
      <Input aria-label={label} data-testid={testId} inputMode="decimal" value={text} aria-invalid={bad} placeholder="—"
        onChange={(e) => {
          setText(e.target.value);
          const t = e.target.value.trim();
          if (t === "") onChange(null);
          else if (Number.isFinite(Number(t))) onChange(Number(t));
        }} />
      <span className="text-[12px] text-dim">{unit}</span>
    </label>
  );
}

function SelField<T extends string>({ label, value, options, onChange }: { label: string; value: T | null; options: [T, string][]; onChange: (v: T | null) => void }) {
  return (
    <label className="grid grid-cols-[1fr_180px] items-center gap-2 py-0.5">
      <span className="text-[13px] text-muted">{label}</span>
      <Select aria-label={label} value={value ?? ""} onChange={(e) => onChange((e.target.value || null) as T | null)}>
        <option value="">— not set —</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </Select>
    </label>
  );
}

function Status({ s }: { s?: { complete: boolean; missing: string[] } }) {
  if (!s) return null;
  return s.complete ? (
    <Badge tone="ok"><CheckCircle2 size={12} className="mr-1" />complete</Badge>
  ) : (
    <span title={`Missing: ${s.missing.join(", ")}`}><Badge tone="warn"><CircleAlert size={12} className="mr-1" />{s.missing.length} missing</Badge></span>
  );
}

function Missing({ s }: { s?: { complete: boolean; missing: string[] } }) {
  if (!s || s.complete) return null;
  return <p className="mb-2 text-[12px] text-warn">Needed for the prediction: {s.missing.join(" · ")}</p>;
}

export function SandInputsPage() {
  const { state, actions } = useWorkstation();
  const saved = state.sand_choke_inputs;
  const [d, setD] = useState<Draft | null>(saved ? structuredClone(saved) : null);
  const savedJson = useMemo(() => JSON.stringify(saved), [saved]);
  useEffect(() => setD(saved ? structuredClone(saved) : null), [savedJson]); // eslint-disable-line react-hooks/exhaustive-deps
  const fileRef = useRef<HTMLInputElement>(null);
  const [cvText, setCvText] = useState("");
  useEffect(() => setCvText((saved?.choke.cv_table ?? []).map(([s, c]) => `${s}, ${c}`).join("\n")), [savedJson]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <PageBody><p className="text-dim">This scenario has no sand / choke model.</p></PageBody>;
  const status = state.sand_choke?.inputs_status;
  const dirty = JSON.stringify(d) !== savedJson;
  const set = <K extends keyof Draft>(k: K, patch: Partial<Draft[K]>) => setD({ ...d, [k]: { ...(d[k] as object), ...patch } } as Draft);
  const mats = [...(state.erosion_materials ?? []).map((m) => [m.key, `${m.name} (K ${m.k.toExponential(2)}, n ${m.n})`] as [string, string]),
    ...d.custom_materials.map((m) => [m.name, `${m.name} (custom)`] as [string, string])];
  const g = d.geomechanics, c = d.completion, s = d.sand, ch = d.choke, a = d.acceptance;

  const save = () => {
    const rows = cvText.split(/\n/).map((l) => l.split(/[,;\t ]+/).filter(Boolean).map(Number)).filter((r) => r.length >= 2 && r.every(Number.isFinite));
    actions.sandInputs({ ...d, choke: { ...d.choke, cv_table: rows.map((r) => [r[0], r[1]] as [number, number]) } });
  };
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(d, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const el = document.createElement("a");
    el.href = url;
    el.download = "sand_choke_inputs.json";
    el.click();
    URL.revokeObjectURL(url);
  };
  const importJson = async (f: File) => {
    try {
      actions.sandInputs(JSON.parse(await f.text()) as Draft);
    } catch {
      /* invalid file: the backend validation message is shown on save */
    }
  };

  return (
    <PageBody intro="Enter your site data. Each prediction runs as soon as the inputs it needs are present; empty fields are never replaced by made-up values. Inputs stay with this session (also after Reset) and can be exported to a file.">
      <div className="sticky top-0 z-10 -mx-1 mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-panel/95 px-3 py-2 backdrop-blur" data-testid="sand-inputs-bar">
        <Button variant="primary" size="sm" disabled={!dirty} onClick={save} data-testid="sand-inputs-save"><Save size={14} className="mr-1" />Save &amp; recalculate</Button>
        {dirty && <span className="text-[12px] text-warn">unsaved changes</span>}
        <span className="flex-1" />
        {state.sand_choke_example_available && (
          <Button size="sm" onClick={() => actions.sandExample()} data-testid="sand-load-example" title="Replace all inputs with a complete ILLUSTRATIVE set (not field data)">
            Load illustrative example
          </Button>
        )}
        <Button size="sm" onClick={exportJson}><Download size={14} className="mr-1" />Export JSON</Button>
        <Button size="sm" onClick={() => fileRef.current?.click()}><FileUp size={14} className="mr-1" />Import JSON</Button>
        <input ref={fileRef} type="file" accept="application/json" className="hidden" onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])} />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-2" data-testid="sand-inputs">
        <Panel title="Reservoir rock & in-situ stresses" right={<Status s={status?.geomechanics} />}>
          <Missing s={status?.geomechanics} />
          <NumField label="Depth (TVD)" unit="m" value={g.depth_tvd_m} onChange={(v) => set("geomechanics", { depth_tvd_m: v })} testId="in-depth" />
          <NumField label="Overburden stress gradient" unit="bar/m" value={g.overburden_gradient_bar_m} onChange={(v) => set("geomechanics", { overburden_gradient_bar_m: v })} />
          <NumField label="Min horizontal stress gradient" unit="bar/m" value={g.min_horizontal_stress_gradient_bar_m} onChange={(v) => set("geomechanics", { min_horizontal_stress_gradient_bar_m: v })} />
          <NumField label="Max horizontal stress gradient" unit="bar/m" value={g.max_horizontal_stress_gradient_bar_m} onChange={(v) => set("geomechanics", { max_horizontal_stress_gradient_bar_m: v })} />
          <NumField label="Initial reservoir pressure" unit="bara" value={g.initial_reservoir_pressure_bara} onChange={(v) => set("geomechanics", { initial_reservoir_pressure_bara: v })} />
          <NumField label="Stress-path coefficient" unit="-" value={g.stress_path_coefficient} onChange={(v) => set("geomechanics", { stress_path_coefficient: v })} hint="d(sigma_h)/d(Pp) during depletion, 0.5-0.8 typical" />
          <NumField label="TWC strength (preferred)" unit="MPa" value={g.twc_strength_mpa} onChange={(v) => set("geomechanics", { twc_strength_mpa: v })} hint="Thick-walled-cylinder collapse strength, OD/ID = 3, from core tests" testId="in-twc" />
          <NumField label="UCS (if no TWC)" unit="MPa" value={g.ucs_mpa} onChange={(v) => set("geomechanics", { ucs_mpa: v })} />
          <NumField label="TWC / UCS ratio (site)" unit="-" value={g.twc_ucs_ratio} onChange={(v) => set("geomechanics", { twc_ucs_ratio: v })} />
          <NumField label="Biot coefficient" unit="-" value={g.biot_coefficient} onChange={(v) => set("geomechanics", { biot_coefficient: v })} />
          <NumField label="Poisson ratio" unit="-" value={g.poisson_ratio} onChange={(v) => set("geomechanics", { poisson_ratio: v })} />
          <NumField label="Water weakening (strength loss at 100 % water)" unit="fraction" value={g.water_weakening_fraction} onChange={(v) => set("geomechanics", { water_weakening_fraction: v })} />
          <NumField label="Porosity" unit="fraction" value={g.porosity} onChange={(v) => set("geomechanics", { porosity: v })} />
          <NumField label="Permeability" unit="mD" value={g.permeability_md} onChange={(v) => set("geomechanics", { permeability_md: v })} />
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title="Completion & sand control" right={<Status s={status?.completion} />}>
            <Missing s={status?.completion} />
            <SelField label="Completion type" value={c.completion_type} onChange={(v) => v && set("completion", { completion_type: v })}
              options={[["cased_perforated_standalone_screens", "Cased & perforated + standalone screens"], ["cased_perforated_no_screens", "Cased & perforated, no sand control"],
                ["openhole_standalone_screens", "Openhole + standalone screens"], ["gravel_pack", "Gravel pack (retention not modelled)"]]} />
            <SelField label="Screen type" value={c.screen_type} onChange={(v) => set("completion", { screen_type: v })} options={[["wire_wrapped", "Wire-wrapped"], ["premium_mesh", "Premium mesh"], ["other", "Other"]]} />
            <NumField label="Screen aperture / slot" unit="µm" value={c.screen_aperture_um} onChange={(v) => set("completion", { screen_aperture_um: v })} testId="in-aperture" />
            <NumField label="Bridging factor" unit="-" value={c.bridging_factor} onChange={(v) => v != null && set("completion", { bridging_factor: v })} hint="1 = geometric only; 2-3 = grains finer than aperture / factor pass once a bridge forms" />
            <NumField label="Damaged screen area" unit="fraction" value={c.screen_damage_fraction} onChange={(v) => set("completion", { screen_damage_fraction: v ?? 0 })} />
            <NumField label="Perforation diameter" unit="mm" value={c.perforation_diameter_mm} onChange={(v) => set("completion", { perforation_diameter_mm: v })} />
            <NumField label="Shot density" unit="spm" value={c.shot_density_spm} onChange={(v) => set("completion", { shot_density_spm: v })} />
            <NumField label="Perforated interval" unit="m" value={c.perforated_interval_m} onChange={(v) => set("completion", { perforated_interval_m: v })} />
          </Panel>

          <Panel title="Sand properties & production" right={<Status s={status?.sand} />}>
            <Missing s={status?.sand} />
            <NumField label="D10 (10 % finer)" unit="µm" value={s.d10_um} onChange={(v) => set("sand", { d10_um: v })} hint="Cumulative % FINER (passing) convention" />
            <NumField label="D50 (median)" unit="µm" value={s.d50_um} onChange={(v) => set("sand", { d50_um: v })} />
            <NumField label="D90 (90 % finer)" unit="µm" value={s.d90_um} onChange={(v) => set("sand", { d90_um: v })} />
            <NumField label="Grain density" unit="kg/m³" value={s.grain_density_kg_m3} onChange={(v) => v != null && set("sand", { grain_density_kg_m3: v })} />
            <SelField label="Sand rate source" value={s.mode} onChange={(v) => v && set("sand", { mode: v })} options={[["predictive", "Predictive (geomechanics + calibrated coefficient)"], ["measured", "Measured / configured"]]} />
            {s.mode === "measured" ? (
              <>
                <NumField label="Measured sand (at wellhead)" unit="" value={s.measured_value} onChange={(v) => set("sand", { measured_value: v })} />
                <SelField label="Unit / basis" value={s.measured_unit} onChange={(v) => v && set("sand", { measured_unit: v })}
                  options={[["kg_d", "kg/day"], ["kg_h", "kg/h"], ["g_s", "g/s"], ["pptb", "pptb (lb per 1000 bbl liquid, std)"], ["ppm_mass_liquid", "ppm by mass of liquid"],
                    ["ppm_mass_total", "ppm by mass of total stream"], ["ppm_vol_liquid", "ppm by volume of liquid (std)"]]} />
                <NumField label="Measurement uncertainty (1σ)" unit="%" value={s.measured_uncertainty_pct} onChange={(v) => v != null && set("sand", { measured_uncertainty_pct: v })} />
              </>
            ) : (
              <>
                <NumField label="Rate coefficient k (calibrated)" unit="kg/m³" value={s.rate_coefficient_kg_m3} onChange={(v) => set("sand", { rate_coefficient_kg_m3: v })}
                  hint="Formation sand per m³ of reservoir liquid at twice the critical drawdown - from sand-trap / detector history" />
                <NumField label="Rate exponent n" unit="-" value={s.rate_exponent} onChange={(v) => v != null && set("sand", { rate_exponent: v })} />
              </>
            )}
          </Panel>
        </div>

        <Panel title="Production choke trim" right={<Status s={status?.choke} />} className="xl:col-span-2">
          <Missing s={status?.choke} />
          <div className="grid gap-x-8 lg:grid-cols-2">
            <div>
              <label className="grid grid-cols-[1fr_180px] items-center gap-2 py-0.5">
                <span className="text-[13px] text-muted">Model / label</span>
                <Input aria-label="Choke model" value={ch.model_label ?? ""} onChange={(e) => set("choke", { model_label: e.target.value || null })} />
              </label>
              <SelField label="Trim design" value={ch.design} onChange={(v) => v && set("choke", { design: v })} options={[["plug_and_cage", "Plug & multi-hole cage"], ["external_sleeve", "External sleeve"], ["needle_and_seat", "Needle & seat"], ["other", "Other"]]} />
              <NumField label="Max Cv" unit="-" value={ch.max_cv} onChange={(v) => set("choke", { max_cv: v })} />
              <NumField label="Min controllable Cv" unit="-" value={ch.min_controllable_cv} onChange={(v) => set("choke", { min_controllable_cv: v })} />
              <NumField label="Actuator steps (full travel)" unit="steps" value={ch.actuator_steps} onChange={(v) => set("choke", { actuator_steps: v == null ? null : Math.round(v) })} />
              <NumField label="Plug stroke" unit="mm" value={ch.stroke_mm} onChange={(v) => set("choke", { stroke_mm: v })} />
              <NumField label="Cage inner diameter" unit="mm" value={ch.cage_inner_diameter_mm} onChange={(v) => set("choke", { cage_inner_diameter_mm: v })} />
              <NumField label="Cage wall thickness" unit="mm" value={ch.cage_wall_thickness_mm} onChange={(v) => set("choke", { cage_wall_thickness_mm: v })} />
              <NumField label="Plug diameter" unit="mm" value={ch.plug_diameter_mm} onChange={(v) => set("choke", { plug_diameter_mm: v })} />
              <NumField label="Choke outlet bore" unit="mm" value={ch.choke_outlet_bore_mm} onChange={(v) => set("choke", { choke_outlet_bore_mm: v })} />
              <NumField label="Gallery / inlet diameter" unit="mm" value={ch.gallery_diameter_mm} onChange={(v) => set("choke", { gallery_diameter_mm: v })} />
              <NumField label="Body wall thickness" unit="mm" value={ch.body_wall_thickness_mm} onChange={(v) => set("choke", { body_wall_thickness_mm: v })} />
              <SelField label="Trim material (cage & plug)" value={ch.trim_material} onChange={(v) => set("choke", { trim_material: v })} options={mats} />
              <SelField label="Body material" value={ch.body_material} onChange={(v) => set("choke", { body_material: v })} options={mats} />
              <NumField label="Mean impact angle at trim" unit="deg" value={ch.trim_impact_angle_deg} onChange={(v) => v != null && set("choke", { trim_impact_angle_deg: v })} />
              <NumField label="Share of trim wear at plug / seat" unit="fraction" value={ch.plug_share} onChange={(v) => v != null && set("choke", { plug_share: v })} />
              <label className="flex items-center justify-between gap-2 py-1 text-[13px] text-muted">
                Predicted hole growth changes the simulated Cv
                <input type="checkbox" checked={ch.erosion_feedback} onChange={(e) => set("choke", { erosion_feedback: e.target.checked })} />
              </label>
            </div>
            <div>
              <h3 className="mb-1 t-eyebrow">Cage hole rows (as new)</h3>
              <table className="w-full text-[12.5px]" data-testid="hole-rows">
                <thead className="text-left text-muted"><tr><th>Axial position mm</th><th>Diameter mm</th><th>Count</th><th></th></tr></thead>
                <tbody>
                  {ch.hole_rows.map((r, i) => (
                    <tr key={i}>
                      {(["axial_position_mm", "diameter_mm", "count"] as const).map((k) => (
                        <td key={k} className="py-0.5 pr-2">
                          <Input aria-label={`row ${i + 1} ${k}`} inputMode="decimal" value={String(r[k])}
                            onChange={(e) => {
                              const v = Number(e.target.value);
                              if (!Number.isFinite(v)) return;
                              const rows = ch.hole_rows.map((x, j) => (j === i ? { ...x, [k]: k === "count" ? Math.round(v) : v } : x));
                              set("choke", { hole_rows: rows });
                            }} />
                        </td>
                      ))}
                      <td><Button size="xs" variant="ghost" aria-label={`remove row ${i + 1}`} onClick={() => set("choke", { hole_rows: ch.hole_rows.filter((_, j) => j !== i) })}><Trash2 size={13} /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Button size="xs" className="mt-1" onClick={() => set("choke", { hole_rows: [...ch.hole_rows, { axial_position_mm: 0, diameter_mm: 5, count: 4 }] })}><Plus size={13} className="mr-1" />Add row</Button>
              <p className="mt-1 text-[12px] text-dim">Axial position: hole centre measured from the closed plug edge. Holes open as the plug lifts.</p>
              <h3 className="mb-1 mt-4 t-eyebrow">Vendor Cv vs step (new trim)</h3>
              <textarea aria-label="Cv table" className="h-32 w-full rounded-md border border-line bg-panel p-2 font-mono text-[12px]" placeholder={"step, Cv\n0, 0\n17, 1.61\n...\n165, 161"}
                value={cvText} onChange={(e) => setCvText(e.target.value)} />
              <p className="text-[12px] text-dim">One "step, Cv" pair per line (paste from the vendor data sheet). Empty: generic characteristic between min and max Cv.</p>
            </div>
          </div>
        </Panel>

        <Panel title="Acceptance criteria (site practice)" right={<Status s={status?.acceptance} />}>
          <Missing s={status?.acceptance} />
          <NumField label="Max cage-hole diameter increase" unit="mm" value={a.max_hole_diameter_increase_mm} onChange={(v) => set("acceptance", { max_hole_diameter_increase_mm: v })} testId="in-max-hole" />
          <NumField label="Max Cv increase at reference step" unit="%" value={a.max_cv_increase_pct} onChange={(v) => set("acceptance", { max_cv_increase_pct: v })} />
          <NumField label="Reference step (normal opening)" unit="step" value={a.reference_step} onChange={(v) => set("acceptance", { reference_step: v })} />
          <NumField label="Max plug / seat edge loss" unit="mm" value={a.max_plug_loss_mm} onChange={(v) => set("acceptance", { max_plug_loss_mm: v })} />
          <NumField label="Max body wall loss" unit="mm" value={a.max_body_wall_loss_mm} onChange={(v) => set("acceptance", { max_body_wall_loss_mm: v })} />
          <NumField label="Max outlet wall loss" unit="mm" value={a.max_outlet_wall_loss_mm} onChange={(v) => set("acceptance", { max_outlet_wall_loss_mm: v })} />
          <h3 className="mb-1 mt-3 t-eyebrow">Health categories (fraction of allowance consumed)</h3>
          <NumField label="Increased wear from" unit="fraction" value={d.thresholds.increased_wear} onChange={(v) => v != null && set("thresholds", { increased_wear: v })} />
          <NumField label="Inspection recommended from" unit="fraction" value={d.thresholds.inspection_recommended} onChange={(v) => v != null && set("thresholds", { inspection_recommended: v })} />
          <NumField label="Changeout assessment from" unit="fraction" value={d.thresholds.changeout_assessment} onChange={(v) => v != null && set("thresholds", { changeout_assessment: v })} />
          <NumField label="Critical from" unit="fraction" value={d.thresholds.critical} onChange={(v) => v != null && set("thresholds", { critical: v })} />
          <NumField label="Elevated erosion rate" unit="mm/yr" value={d.thresholds.elevated_rate_mm_y} onChange={(v) => v != null && set("thresholds", { elevated_rate_mm_y: v })} />
        </Panel>

        <Panel title="Sand detector">
          <label className="grid grid-cols-[1fr_180px] items-center gap-2 py-0.5">
            <span className="text-[13px] text-muted">Tag</span>
            <Input aria-label="Detector tag" value={d.detector.tag} onChange={(e) => set("detector", { tag: e.target.value })} />
          </label>
          <SelField label="Type" value={d.detector.detector_type} onChange={(v) => v && set("detector", { detector_type: v })} options={[["acoustic_non_intrusive", "Acoustic, non-intrusive"], ["intrusive_erosion_probe", "Intrusive erosion probe"]]} />
          <NumField label="Calibration uncertainty (1σ)" unit="%" value={d.detector.calibration_uncertainty_pct} onChange={(v) => v != null && set("detector", { calibration_uncertainty_pct: v })} />
          <NumField label="Minimum velocity for detection" unit="m/s" value={d.detector.min_velocity_m_s} onChange={(v) => v != null && set("detector", { min_velocity_m_s: v })} />
          <NumField label="Noise floor" unit="g/s" value={d.detector.noise_floor_g_s} onChange={(v) => v != null && set("detector", { noise_floor_g_s: v })} />
          <NumField label="Alarm threshold" unit="g/s" value={d.detector.alarm_threshold_g_s} onChange={(v) => v != null && set("detector", { alarm_threshold_g_s: v })} />
          <NumField label="Range" unit="g/s" value={d.detector.range_max_g_s} onChange={(v) => v != null && set("detector", { range_max_g_s: v })} />
        </Panel>

        <Panel title="Operating history (pre-loads wear)" className="xl:col-span-2" subtitle="Past periods since the trim was installed, e.g. monthly averages. Applied on save.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-[12.5px]" data-testid="history-table">
              <thead className="text-left text-muted">
                <tr>{["Label", "Days", "Choke step", "P up bara", "P down bara", "Oil Sm³/d", "Gas Sm³/d", "Water Sm³/d", "Sand kg/d", "T °C", ""].map((h) => <th key={h} className="pr-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {d.history.map((h, i) => (
                  <tr key={i}>
                    <td className="py-0.5 pr-2"><Input aria-label={`history ${i + 1} label`} value={h.label} onChange={(e) => setD({ ...d, history: d.history.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)) })} /></td>
                    {(["days", "choke_step", "upstream_pressure_bara", "downstream_pressure_bara", "oil_sm3_d", "gas_sm3_d", "water_sm3_d", "sand_kg_d", "temperature_c"] as const).map((k) => (
                      <td key={k} className="py-0.5 pr-2">
                        <Input aria-label={`history ${i + 1} ${k}`} inputMode="decimal" value={String(h[k])}
                          onChange={(e) => {
                            const v = Number(e.target.value);
                            if (Number.isFinite(v)) setD({ ...d, history: d.history.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
                          }} />
                      </td>
                    ))}
                    <td><Button size="xs" variant="ghost" aria-label={`remove history ${i + 1}`} onClick={() => setD({ ...d, history: d.history.filter((_, j) => j !== i) })}><Trash2 size={13} /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button size="xs" className="mt-1" onClick={() => setD({ ...d, history: [...d.history, { label: `period ${d.history.length + 1}`, days: 30, choke_step: 80, upstream_pressure_bara: 120, downstream_pressure_bara: 65, oil_sm3_d: 0, gas_sm3_d: 0, water_sm3_d: 0, sand_kg_d: 0, temperature_c: 60 }] })}>
            <Plus size={13} className="mr-1" />Add period
          </Button>
          {d.history.length === 0 && (
            <div className="mt-2">
              <NumField label="Trim service time before the simulation (no history)" unit="days" value={d.initial_service_days} onChange={(v) => setD({ ...d, initial_service_days: v ?? 0 })} />
            </div>
          )}
        </Panel>

        <Panel title="Inspection records (calibrate the erosion model)" className="xl:col-span-2" subtitle="Measured wear at a known service time. The service time must be covered by the operating history above.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-[12.5px]" data-testid="inspection-table">
              <thead className="text-left text-muted">
                <tr>{["Label", "Service days", "Max hole increase mm", "Cv increase %", "Plug loss mm", "Trim replaced", "Notes", ""].map((h) => <th key={h} className="pr-2">{h}</th>)}</tr>
              </thead>
              <tbody>
                {d.inspections.map((r, i) => {
                  const upd = (patch: Partial<typeof r>) => setD({ ...d, inspections: d.inspections.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
                  const num = (k: "service_days" | "measured_max_hole_increase_mm" | "measured_cv_increase_pct" | "measured_plug_loss_mm") => (
                    <Input aria-label={`inspection ${i + 1} ${k}`} inputMode="decimal" value={r[k] == null ? "" : String(r[k])}
                      onChange={(e) => {
                        const t = e.target.value.trim();
                        if (t === "") upd({ [k]: k === "service_days" ? 0 : null } as Partial<typeof r>);
                        else if (Number.isFinite(Number(t))) upd({ [k]: Number(t) } as Partial<typeof r>);
                      }} />
                  );
                  return (
                    <tr key={i}>
                      <td className="py-0.5 pr-2"><Input aria-label={`inspection ${i + 1} label`} value={r.label} onChange={(e) => upd({ label: e.target.value })} /></td>
                      <td className="pr-2">{num("service_days")}</td>
                      <td className="pr-2">{num("measured_max_hole_increase_mm")}</td>
                      <td className="pr-2">{num("measured_cv_increase_pct")}</td>
                      <td className="pr-2">{num("measured_plug_loss_mm")}</td>
                      <td className="pr-2 text-center"><input type="checkbox" aria-label={`inspection ${i + 1} trim replaced`} checked={r.trim_replaced} onChange={(e) => upd({ trim_replaced: e.target.checked })} /></td>
                      <td className="pr-2"><Input aria-label={`inspection ${i + 1} notes`} value={r.notes} onChange={(e) => upd({ notes: e.target.value })} /></td>
                      <td><Button size="xs" variant="ghost" aria-label={`remove inspection ${i + 1}`} onClick={() => setD({ ...d, inspections: d.inspections.filter((_, j) => j !== i) })}><Trash2 size={13} /></Button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Button size="xs" className="mt-1" onClick={() => setD({ ...d, inspections: [...d.inspections, { label: `inspection ${d.inspections.length + 1}`, service_days: 0, measured_max_hole_increase_mm: null, measured_cv_increase_pct: null, measured_plug_loss_mm: null, notes: "", trim_replaced: false }] })}>
            <Plus size={13} className="mr-1" />Add inspection
          </Button>
        </Panel>
      </div>
    </PageBody>
  );
}
