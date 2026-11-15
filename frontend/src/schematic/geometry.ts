import type { LayoutPoint } from "@/types/simulation";

export function polylineLength(pts: LayoutPoint[]): number {
  let L = 0;
  for (let i = 0; i < pts.length - 1; i++) L += Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y);
  return L;
}

/** Point and direction (degrees) at fraction f of a polyline's length. */
export function pointAlong(pts: LayoutPoint[], f: number): { x: number; y: number; angle: number } {
  const total = polylineLength(pts);
  let target = total * f;
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (target <= seg || i === pts.length - 2) {
      const t = seg === 0 ? 0 : Math.min(1, target / seg);
      return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI };
    }
    target -= seg;
  }
  return { x: pts[0].x, y: pts[0].y, angle: 0 };
}

/** Sub-polyline between fractions f0 < f1 of the total length. */
export function subPath(pts: LayoutPoint[], f0: number, f1: number): LayoutPoint[] {
  const total = polylineLength(pts);
  const a = Math.max(0, Math.min(1, f0)) * total;
  const b = Math.max(0, Math.min(1, f1)) * total;
  const out: LayoutPoint[] = [];
  let acc = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const p = pts[i];
    const q = pts[i + 1];
    const seg = Math.hypot(q.x - p.x, q.y - p.y);
    const s0 = acc;
    const s1 = acc + seg;
    if (s1 >= a && s0 <= b && seg > 0) {
      const t0 = Math.max(0, (a - s0) / seg);
      const t1 = Math.min(1, (b - s0) / seg);
      if (!out.length) out.push({ x: p.x + (q.x - p.x) * t0, y: p.y + (q.y - p.y) * t0 });
      out.push({ x: p.x + (q.x - p.x) * t1, y: p.y + (q.y - p.y) * t1 });
    }
    acc = s1;
  }
  return out;
}

export function pathD(pts: LayoutPoint[]): string {
  return pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

/** Midpoints of every segment long enough to carry a flow arrow. */
export function arrowPositions(pts: LayoutPoint[], minLen = 60): { x: number; y: number; angle: number }[] {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (seg >= minLen) {
      out.push({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, angle: (Math.atan2(b.y - a.y, b.x - a.x) * 180) / Math.PI });
    }
  }
  return out;
}
