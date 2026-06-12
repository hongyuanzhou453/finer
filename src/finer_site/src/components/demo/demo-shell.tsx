"use client";

import { useState } from "react";
import type { DemoView } from "./demo-header";
import { DemoWorkbench } from "./demo-workbench";
import { AnnotationWorkbench } from "./annotation-workbench";

/**
 * Owns the demo view state and switches between the research/backtest workbench
 * and the annotation walkthrough. Each workbench renders the shared DemoHeader
 * (with the segmented switch) itself, so switching is a single control.
 */
export function DemoShell() {
  const [view, setView] = useState<DemoView>("research");

  return view === "research" ? (
    <DemoWorkbench view={view} onViewChange={setView} />
  ) : (
    <AnnotationWorkbench view={view} onViewChange={setView} />
  );
}
