"use client";

import { useMemo } from "react";
import { Info, ShieldCheck, TrendingDown, TrendingUp, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  F8MetricRow,
  KOLBacktestViewModel,
} from "@/lib/f8-visualization";
import { BaseEChart, type F8EChartOption } from "./base-echart";

const chartColors = {
  ink: "#181512",
  muted: "#64748b",
  faint: "#cbd5e1",
  grid: "rgba(54, 38, 24, 0.1)",
  gridSoft: "rgba(54, 38, 24, 0.05)",
  band: "rgba(159, 29, 34, 0.05)",
  subject: "#9f1d22",
  benchmark: "#1e293b",
  peer: "#94a3b8",
  good: "#e11b22",
  bad: "#10b981",
  neutral: "#64748b",
};

function formatReturn(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function returnTone(value: number) {
  if (value > 0) return "text-[var(--chart-up)]";
  if (value < 0) return "text-[var(--chart-down)]";
  return "text-[var(--foreground)]";
}

type ResearchBlockProps = {
  title: string;
  meta: string;
  children: React.ReactNode;
  note?: string;
  className?: string;
};

export function ResearchBlock({
  title,
  meta,
  children,
  note,
  className,
}: ResearchBlockProps) {
  return (
    <section className={cn("research-panel flex flex-col min-w-0 mb-6", className)}>
      <div className="research-panel-header flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <h2 className="text-[17px] tracking-normal font-semibold text-[var(--foreground)]">
          {title}
        </h2>
        <div className="text-xs font-medium text-[var(--ink-soft)]">{meta}</div>
      </div>
      <div className="research-panel-body">{children}</div>
      {note && (
        <div className="border-t border-[var(--table-border)] px-5 py-3 text-[11px] leading-relaxed text-[var(--ink-soft)]">
          {note}
        </div>
      )}
    </section>
  );
}

export function KOLOverviewPanel({ model }: { model: KOLBacktestViewModel }) {
  const returnPercentile =
    model.metricRows.find((row) => row.metric === "Alpha")?.percentile ?? 0;
  const drawdownPercentile =
    model.metricRows.find((row) => row.metric === "最大回撤")?.percentile ?? 0;

  return (
    <ResearchBlock
      title="KOL Overview"
      meta={`${model.benchmark.name} / ${model.cohort.name} / 截止 ${model.dataCutoff}`}
      note={`同类定义：${model.cohort.definition}`}
    >
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <div className="flex gap-4">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-sm bg-morningstar-red text-xl font-bold text-white">
            {model.subject.name.slice(0, 1)}
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-normal text-[var(--foreground)]">
                {model.subject.name}
              </h1>
              <span className="border border-[var(--table-border)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[var(--ink-soft)]">
                {model.subject.platform}
              </span>
            </div>
            <p className="mt-2 line-clamp-3 text-sm leading-6 text-[var(--ink-soft)]">
              {model.subject.biography}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {model.subject.tags.map((tag) => (
                <span
                  key={tag}
                  className="border border-[var(--table-border)] px-2 py-0.5 text-[11px] text-[var(--foreground)]"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {model.keyStats.map((stat) => (
            <div key={stat.label} className="border-b border-[var(--table-border)] pb-3">
              <div className="text-[11px] font-medium text-[var(--ink-soft)]">
                {stat.label}
              </div>
              <div
                className={cn(
                  "mt-1 text-2xl font-semibold tabular-nums",
                  stat.tone === "positive" && "text-[var(--chart-up)]",
                  stat.tone === "negative" && "text-[var(--chart-down)]",
                  stat.tone === "neutral" && "text-[var(--foreground)]",
                )}
              >
                {stat.value}
              </div>
              <div className="mt-1 text-[11px] text-[var(--ink-soft)]">
                {stat.subLabel}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <CapabilityScale
          label="收益能力"
          percentile={returnPercentile}
          markerLabel={`前 ${100 - returnPercentile}%`}
        />
        <CapabilityScale
          label="风控能力"
          percentile={drawdownPercentile}
          markerLabel={`优于 ${drawdownPercentile}%`}
        />
      </div>
    </ResearchBlock>
  );
}

function CapabilityScale({
  label,
  percentile,
  markerLabel,
}: {
  label: string;
  percentile: number;
  markerLabel: string;
}) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="font-medium text-[var(--foreground)]">{label}</span>
        <span className="text-[var(--ink-soft)]">{markerLabel}</span>
      </div>
      <div className="relative grid h-8 grid-cols-3 border border-[var(--table-border)]">
        <div className="bg-[#f3f3f3]" />
        <div className="border-x border-[var(--table-border)] bg-white" />
        <div className="bg-[#f8efe8]" />
        <div
          className="absolute top-[-5px] h-0 w-0 border-x-[6px] border-t-[10px] border-x-transparent border-t-[var(--foreground)]"
          style={{ left: `calc(${percentile}% - 6px)` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--ink-soft)]">
        <span>后段</span>
        <span>中位</span>
        <span>前段</span>
      </div>
    </div>
  );
}

export function CumulativeReturnResearch({
  model,
}: {
  model: KOLBacktestViewModel;
}) {
  const option = useMemo<F8EChartOption>(() => {
    const xData = model.returnSeries.map((point) => point.date);
    const markAreas = xData
      .slice(0, -1)
      .map((date, index) =>
        index % 2 === 0
          ? [{ xAxis: date }, { xAxis: xData[index + 1] }]
          : null,
      )
      .filter(Boolean);

    return {
      animationDuration: 250,
      color: [chartColors.subject, chartColors.benchmark, chartColors.peer],
      tooltip: {
        trigger: "axis",
        valueFormatter: (value: number) => `${Number(value).toFixed(2)}%`,
      },
      legend: {
        left: 0,
        top: 0,
        itemWidth: 22,
        itemHeight: 3,
        textStyle: { color: chartColors.ink, fontSize: 12 },
      },
      grid: { left: 48, right: 152, top: 50, bottom: 42 },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: xData,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: chartColors.grid } },
        axisLabel: {
          color: chartColors.muted,
          formatter: (value: string) => value.replace("-", "\n"),
        },
      },
      yAxis: {
        type: "value",
        axisLabel: {
          color: chartColors.muted,
          formatter: "{value}%",
        },
        splitLine: { lineStyle: { color: chartColors.gridSoft } },
        axisLine: { lineStyle: { color: chartColors.grid } },
      },
      series: [
        {
          name: "KOL观点组合收益",
          type: "line",
          data: model.returnSeries.map((point) => point.subject),
          symbol: "none",
          lineStyle: { width: 3, color: chartColors.subject },
          markArea: {
            silent: true,
            itemStyle: { color: chartColors.band, opacity: 0.62 },
            data: markAreas,
          },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: chartColors.ink, width: 1 },
            label: { show: false },
            data: [{ yAxis: 0 }],
          },
        },
        {
          name: model.benchmark.name,
          type: "line",
          data: model.returnSeries.map((point) => point.benchmark),
          symbol: "none",
          lineStyle: { width: 2.5, color: chartColors.benchmark },
        },
        {
          name: "同类均值",
          type: "line",
          data: model.returnSeries.map((point) => point.peer),
          symbol: "none",
          lineStyle: { width: 2.5, color: chartColors.peer },
        },
      ],
      toolbox: {
        right: 0,
        top: 0,
        feature: {
          saveAsImage: {
            title: "导出",
            pixelRatio: 2,
            backgroundColor: "#ffffff",
          },
        },
      },
    } satisfies F8EChartOption;
  }, [model]);

  return (
    <ResearchBlock
      title="Cumulative Return"
      meta={`${model.dateRange.start} ~ ${model.dateRange.end}`}
      note={`收益曲线已扣除 ${(model.assumptions.commissionPct * 100).toFixed(2)}% 佣金与 ${(model.assumptions.slippagePct * 100).toFixed(2)}% 滑点；缺失月份以审计备注处理，不用平滑值替代。`}
    >
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_260px]">
        <BaseEChart
          option={option}
          height={340}
          ariaLabel={`${model.subject.name} cumulative return versus benchmark and cohort`}
        />
        <AnnualReturnTable model={model} />
      </div>
    </ResearchBlock>
  );
}

function AnnualReturnTable({ model }: { model: KOLBacktestViewModel }) {
  return (
    <div className="overflow-hidden">
      <div className="mb-2 text-xs font-semibold text-[var(--foreground)]">
        年度审计表
      </div>
      <table className="top-rule-table">
        <thead>
          <tr>
            <th>年度</th>
            <th className="text-right">本主体</th>
            <th className="text-right">基准</th>
            <th className="text-right">命中率</th>
          </tr>
        </thead>
        <tbody>
          {model.annualRows.map((row) => (
            <tr key={row.year}>
              <td className="font-medium text-[var(--foreground)]">{row.year}</td>
              <td className={cn("tabular-nums", returnTone(row.subject))}>
                {formatReturn(row.subject)}
              </td>
              <td className={cn("tabular-nums", returnTone(row.benchmark))}>
                {formatReturn(row.benchmark)}
              </td>
              <td className="tabular-nums text-[var(--foreground)]">
                {row.hitRate.toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RiskReturnResearch({ model }: { model: KOLBacktestViewModel }) {
  const option = useMemo<F8EChartOption>(() => {
    return {
      animationDuration: 250,
      tooltip: {
        trigger: "item",
        formatter: (params: { data?: [number, number, string, number] }) => {
          const data = params.data;
          if (!data) return "";
          return `${data[2]}<br/>观点波动：${data[0].toFixed(1)}%<br/>年化收益：${data[1].toFixed(1)}%<br/>命中率：${data[3].toFixed(0)}%`;
        },
      },
      grid: { left: 54, right: 28, top: 28, bottom: 58 },
      xAxis: {
        name: "观点波动",
        nameLocation: "middle",
        nameGap: 34,
        type: "value",
        axisLabel: { formatter: "{value}%", color: chartColors.muted },
        splitLine: { lineStyle: { color: chartColors.gridSoft } },
        axisLine: { lineStyle: { color: chartColors.grid } },
      },
      yAxis: {
        name: "年化收益",
        type: "value",
        axisLabel: { formatter: "{value}%", color: chartColors.muted },
        splitLine: { lineStyle: { color: chartColors.gridSoft } },
        axisLine: { lineStyle: { color: chartColors.grid } },
      },
      series: [
        {
          name: "同类 KOL",
          type: "scatter",
          symbolSize: 8,
          data: model.peerRiskReturn.map((point) => [
            point.volatility,
            point.annualizedReturn,
            point.name,
            point.hitRate,
          ]),
          itemStyle: { color: chartColors.benchmark, opacity: 0.72 },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: chartColors.benchmark, width: 1, type: "solid" },
            label: { color: chartColors.benchmark, fontSize: 10 },
            data: [
              {
                xAxis: model.cohortMedian.volatility,
                label: { formatter: "波动中位" },
              },
              {
                yAxis: model.cohortMedian.annualizedReturn,
                label: { formatter: "收益中位" },
              },
            ],
          },
        },
        {
          name: model.subject.name,
          type: "scatter",
          symbolSize: 18,
          data: [[
            model.subjectRiskReturn.volatility,
            model.subjectRiskReturn.annualizedReturn,
            model.subject.name,
            model.subjectRiskReturn.hitRate,
          ]],
          itemStyle: {
            color: chartColors.subject,
            borderColor: "#ffffff",
            borderWidth: 2,
          },
        },
      ],
      legend: {
        bottom: 0,
        left: "center",
        textStyle: { color: chartColors.ink, fontSize: 12 },
      },
    } satisfies F8EChartOption;
  }, [model]);

  return (
    <ResearchBlock
      title="Risk Return Scatter"
      meta={`${model.cohort.peerCount} 位同类 KOL / 中位线为同类样本`}
      note="横轴越低代表观点组合波动越小；纵轴越高代表年化收益越强。酒红点为当前 KOL，深蓝点为同类样本。"
    >
      <BaseEChart
        option={option}
        height={360}
        ariaLabel={`${model.subject.name} risk return scatter versus peer cohort`}
      />
    </ResearchBlock>
  );
}

export function MetricPercentileTable({
  rows,
}: {
  rows: F8MetricRow[];
}) {
  return (
    <ResearchBlock
      title="Metric Percentile Audit"
      meta="指标方向已显式标注"
      note="分位值基于同类 KOL 样本计算。收益类指标越高越好，回撤、波动、兑现速度越低越好。"
    >
      <div className="overflow-x-auto">
        <table className="top-rule-table min-w-[760px]">
          <thead>
            <tr>
              <th>指标</th>
              <th>同类表现</th>
              <th className="text-right">本主体</th>
              <th className="text-right">同类平均</th>
              <th>口径</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.metric}>
                <td>
                  <div className="flex items-center gap-1.5 font-medium text-[var(--foreground)]">
                    {row.metric}
                    <Info className="h-3.5 w-3.5 text-[var(--ink-soft)]" />
                  </div>
                  <div className="mt-1 text-[11px] text-[var(--ink-soft)]">
                    {row.direction === "higher_is_better" ? "越高越好" : "越低越好"}
                  </div>
                </td>
                <td className="text-[var(--foreground)]">
                  优于
                  <span className="px-1 font-semibold text-[var(--foreground)]">
                    {row.percentile}%
                  </span>
                  同类
                </td>
                <td className="text-right font-semibold tabular-nums text-[var(--foreground)]">
                  {row.subjectDisplay}
                </td>
                <td className="text-right tabular-nums text-[var(--ink-soft)]">
                  {row.cohortDisplay}
                </td>
                <td className="max-w-[280px] text-xs leading-5 text-[var(--ink-soft)]">
                  {row.note}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ResearchBlock>
  );
}

export function TopCallsTable({ model }: { model: KOLBacktestViewModel }) {
  return (
    <ResearchBlock
      title="Top Calls"
      meta={`更新至 ${model.dataCutoff}`}
      note="只展示对总收益解释度较高的观点，结果按已实现回测收益口径计算。"
    >
      <div className="overflow-x-auto">
        <table className="top-rule-table min-w-[720px]">
          <thead>
            <tr>
              <th>股票代码</th>
              <th>股票名称</th>
              <th>主题</th>
              <th>方向</th>
              <th className="text-right">证据强度</th>
              <th className="text-right">观点权重</th>
              <th className="text-right">结果</th>
              <th className="text-right">更新日期</th>
            </tr>
          </thead>
          <tbody>
            {model.topCalls.map((call) => (
              <tr key={call.id}>
                <td className="font-semibold text-[var(--foreground)]">{call.ticker}</td>
                <td className="text-[var(--foreground)]">{call.name}</td>
                <td className="text-[var(--ink-soft)]">{call.topic}</td>
                <td>
                  <span className="inline-flex items-center gap-1 border border-[var(--table-border)] px-2 py-0.5 text-xs text-[var(--foreground)]">
                    {call.direction === "long" ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    {call.direction === "long" ? "做多" : "做空"}
                  </span>
                </td>
                <td className="tabular-nums">
                  {call.evidenceStrength}
                </td>
                <td className="tabular-nums">
                  {call.weight.toFixed(1)}%
                </td>
                <td className={cn("font-semibold tabular-nums", returnTone(call.result))}>
                  {formatReturn(call.result)}
                </td>
                <td className="tabular-nums text-[var(--ink-soft)]">
                  {call.updatedAt}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ResearchBlock>
  );
}

export function MethodologyStrip({ model }: { model: KOLBacktestViewModel }) {
  const items = [
    {
      icon: ShieldCheck,
      title: "回测规则",
      body: `${model.assumptions.executionDelay}；${model.assumptions.holdingRule}。`,
    },
    {
      icon: Users,
      title: "同类样本",
      body: `${model.cohort.peerCount} 位 KOL，${model.cohort.definition}`,
    },
    {
      icon: Info,
      title: "费用与滑点",
      body: `佣金 ${(model.assumptions.commissionPct * 100).toFixed(2)}%，滑点 ${(model.assumptions.slippagePct * 100).toFixed(2)}%，${model.assumptions.feesIncluded ? "已计入结果" : "未计入结果"}。`,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <div key={item.title} className="border-t-2 border-[var(--foreground)] bg-white p-5">
            <Icon className="h-9 w-9 text-[var(--foreground)]" strokeWidth={1.4} />
            <h3 className="mt-4 text-base font-semibold tracking-normal text-[var(--foreground)]">
              {item.title}
            </h3>
            <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{item.body}</p>
          </div>
        );
      })}
    </div>
  );
}
