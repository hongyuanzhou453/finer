/**
 * L4 bridge: resolve a viewpoint id (from any KOL timeline / ticker cross-section /
 * actionable call) back to its viewpoint + KOL context, so each data point can drill
 * to a per-viewpoint evidence audit.
 *
 * HONESTY NOTE: demo viewpoints carry F2 evidence (the KOL's words) + F5 action basics
 * + F8 backtest outcome, but NOT the full source text, four execution clocks, or real
 * F3 intent / F4 policy. The audit view shows what's present and flags the rest; it does
 * NOT fabricate a canonical F3→F4→F5 trace. Full canonical examples live at /audit.
 */
import { KOL_RADAR_FIXTURE } from "./kol-radar";
import { KOL_SNAPSHOT_FIXTURE, type SnapshotViewpoint } from "./kol-snapshot";

export interface ViewpointLocator {
  viewpoint: SnapshotViewpoint;
  kolId: string;
  kolName: string;
  kolStyle: string;
}

/** Find a viewpoint by id across the radar (per-KOL) and standalone snapshot fixtures. */
export function findViewpointById(id: string): ViewpointLocator | null {
  for (const k of KOL_RADAR_FIXTURE.kols) {
    const vp = k.viewpoints.find((v) => v.id === id);
    if (vp) {
      return { viewpoint: vp, kolId: k.kolId, kolName: k.name, kolStyle: k.style };
    }
  }
  const s = KOL_SNAPSHOT_FIXTURE;
  const vp = s.viewpoints.find((v) => v.id === id);
  if (vp) {
    return { viewpoint: vp, kolId: s.kolId, kolName: s.kolName, kolStyle: s.style };
  }
  return null;
}
