import {
  Activity,
  BookOpen,
  Droplets,
  Gauge,
  type LucideIcon,
  LayoutDashboard,
  Mountain,
  ListTree,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  Waves,
  HeartPulse,
  ClipboardList,
  ToggleRight,
  Archive,
  GitCompare,
} from "lucide-react";

export type RouteId =
  | "overview"
  | "trends"
  | "chemicals"
  | "integrity"
  | "valves"
  | "instruments"
  | "events"
  | "diagnostics"
  | "conditions"
  | "multiphase"
  | "mpfm"
  | "sand"
  | "chokehealth"
  | "sandinputs"
  | "scenario"
  | "records"
  | "comparison"
  | "training";

export interface RouteDef {
  id: RouteId;
  label: string;
  /** One-line description used in the page header and the command palette. */
  description: string;
  icon: LucideIcon;
  group: "Operate" | "Monitor" | "Configure" | "Learn";
  /** Keyboard shortcut digit (Alt + digit). */
  key?: string;
}

export const ROUTES: RouteDef[] = [
  { id: "overview", label: "Christmas tree", description: "Christmas tree workstation, key measurements and activity", icon: LayoutDashboard, group: "Operate", key: "1" },
  { id: "valves", label: "Valves & actuators", description: "Operate tree, annulus and injection valves", icon: ToggleRight, group: "Operate", key: "2" },
  { id: "chemicals", label: "Chemicals", description: "Injection circuits, dosing and chemical transport", icon: Droplets, group: "Operate", key: "3" },
  { id: "integrity", label: "Integrity tests", description: "Stroke, pressure-hold and inflow tests", icon: ShieldCheck, group: "Operate", key: "4" },
  { id: "multiphase", label: "Multiphase flow", description: "Oil, gas and water rates, phase behaviour, flow pattern and mass balance", icon: Waves, group: "Monitor" },
  { id: "mpfm", label: "MPFM monitoring", description: "Manifold multiphase flow meter: measured vs true, uncertainty and diagnostics", icon: Gauge, group: "Monitor" },
  { id: "sand", label: "Sand monitoring", description: "SDT-101 sand detector, sanding onset, sand rates through the screens to the choke, transport", icon: Mountain, group: "Monitor" },
  { id: "chokehealth", label: "Choke health", description: "Sand source, choke erosion, remaining life, Cv tracking, calibration and recommendation", icon: HeartPulse, group: "Monitor" },
  { id: "trends", label: "Trends", description: "Process history against simulated time", icon: Activity, group: "Monitor", key: "5" },
  { id: "instruments", label: "Instruments", description: "Every transmitter, its value and quality", icon: Gauge, group: "Monitor", key: "6" },
  { id: "events", label: "Event history", description: "Operations, outcomes and system events", icon: ListTree, group: "Monitor", key: "7" },
  { id: "diagnostics", label: "Diagnostics", description: "Solver status and model-validity checks", icon: Stethoscope, group: "Monitor", key: "8" },
  { id: "conditions", label: "Conditions", description: "Reservoir, boundary and fluid properties", icon: SlidersHorizontal, group: "Configure", key: "9" },
  { id: "sandinputs", label: "Sand & choke inputs", description: "Reservoir, geomechanics, completion, sand, choke trim, acceptance criteria, history and inspections", icon: ClipboardList, group: "Configure" },
  { id: "comparison", label: "Scenario comparison", description: "Compare operating options with the same models: production, sanding, erosion life, cavitation", icon: GitCompare, group: "Configure" },
  { id: "records", label: "Simulation records", description: "Saved assessments: inputs, results, methods, provenance, uncertainty and validation", icon: Archive, group: "Configure" },
  { id: "scenario", label: "Scenario & model", description: "Training scenarios and simulation model", icon: Settings2, group: "Configure" },
  { id: "training", label: "Training", description: "Guided exercises with assessment", icon: BookOpen, group: "Learn" },
];

export const ROUTE_BY_ID = Object.fromEntries(ROUTES.map((r) => [r.id, r])) as Record<RouteId, RouteDef>;
export const GROUPS = ["Operate", "Monitor", "Configure", "Learn"] as const;
