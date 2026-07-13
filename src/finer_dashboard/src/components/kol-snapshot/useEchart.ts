"use client";

import { useEffect, useRef, type DependencyList } from "react";
import * as echarts from "echarts";

/** Loose option type = exactly what setOption accepts (avoids strict authoring types). */
type ChartOption = Parameters<echarts.EChartsType["setOption"]>[0];

/**
 * Minimal ECharts binding: init on mount, re-set option when `deps` change,
 * resize with the container, dispose on unmount.
 */
export function useEchart(buildOption: () => ChartOption, deps: DependencyList) {
  const elRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: "canvas" });
    chart.setOption(buildOption());

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return elRef;
}
