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
