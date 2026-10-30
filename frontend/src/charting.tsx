import { datasetIsAvailable, preferredDataset } from "./datasetSelection";
import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import {
  Crosshair,
  Maximize2,
  Minimize2,
  RefreshCw,
  Settings2,
  ShieldCheck,
  CandlestickChart,
  Layers3,
  ArrowUpRight,
  X,
  Bot,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, put, type Dataset, type Run, type DecisionTraces } from "./api";
import {
  Badge,
  Empty,
  ErrorPanel,
  Notice,
  SourceBadge,
  Spinner,
  useLoad,
} from "./components";
import { useApp } from "./context";

export type MarketBar = {
  time: string;
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume?: number;
  number_of_trades?: number;
};
type IndicatorConfig = {
  id: string;
  kind: string;
  params: Record<string, number | string>;
};
type MarketResponse = {
  dataset: Dataset;
  bars: MarketBar[];
  gaps: unknown[];
  provenance: Record<string, unknown>;
  indicators: {
    id: string;
    kind: string;
    values: (number | null)[];
    status?: string;
    message?: string;
  }[];
  truncated: boolean;
  warmup_bars: number;
};
const choices = [
  { kind: "ema", label: "EMA", params: { period: 20 }, pane: false },
  { kind: "sma", label: "SMA", params: { period: 60 }, pane: false },
  {
    kind: "bollinger",
    label: "Bollinger · upper",
    params: { period: 20, stddev: 2, output: "upper" },
    pane: false,
  },
  {
    kind: "vwap",
    label: "VWAP · rolling",
    params: { period: 28 },
    pane: false,
  },
  {
    kind: "donchian",
    label: "Donchian · upper",
    params: { period: 20, output: "upper" },
    pane: false,
  },
  { kind: "rsi", label: "RSI", params: { period: 14 }, pane: true },
  {
    kind: "macd",
    label: "MACD",
    params: { fast: 12, slow: 26, signal: 9, output: "histogram" },
    pane: true,
  },
  { kind: "atr", label: "ATR", params: { period: 14 }, pane: true },
  {
    kind: "volatility",
    label: "Realized volatility",
    params: { period: 28 },
    pane: true,
  },
] as const;
const defaultIndicators: IndicatorConfig[] = [
  { id: "ema20", kind: "ema", params: { period: 20 } },
  { id: "sma60", kind: "sma", params: { period: 60 } },
  { id: "rsi14", kind: "rsi", params: { period: 14 } },
];
const palette = [
  "#a5dbbd",
  "#a5c8d6",
  "#d7b58a",
  "#c2abcf",
  "#a4b4e2",
  "#deb5ab",
];

/** Market renderer boundary: no market data vendor; replace this ECharts adapter independently. */
export function FinancialChart({
  bars,
  indicators,
  configs,
  orders = [],
  account = [],
  onEvent,
  height = 620,
  autoscale = true,
  priceBounds,
  reset = 0,
}: {
  bars: MarketBar[];
  indicators: MarketResponse["indicators"];
  configs: IndicatorConfig[];
  orders?: DecisionTraces["orders"];
  account?: DecisionTraces["account"];
  onEvent?: (index: number) => void;
  height?: number;
  autoscale?: boolean;
  priceBounds?: { min: number; max: number };
  reset?: number;
}) {
  const { theme, locale, t, date, timezone, format } = useApp();
  const element = useRef<HTMLDivElement>(null);
  const option = useMemo(() => {
    const dark = theme === "dark",
      text = dark ? "#8c9e9d" : "#62716d",
      border = dark ? "#2a393b" : "#dce4df";
    const dates = bars.map((b) => b.time),
      lookup = new Map(bars.map((b, i) => [b.timestamp, i]));
    const step = bars.reduce(
      (smallest, b, i) =>
        i ? Math.min(smallest, b.timestamp - bars[i - 1].timestamp) : smallest,
      Infinity,
    );
    const nearest = (clock: string) => {
      const ts = Date.parse(clock);
      if (lookup.has(ts)) return lookup.get(ts)!;
      let lo = 0,
        hi = bars.length - 1;
      while (lo < hi) {
        const mid = Math.floor((lo + hi + 1) / 2);
        if (bars[mid].timestamp <= ts) lo = mid;
        else hi = mid - 1;
      }
      return lo;
    };
    const oscillator = configs.find(
        (c) => choices.find((x) => x.kind === c.kind)?.pane,
      ),
      third = !!oscillator;
    const grids = [
      { left: 64, right: 66, top: 42, bottom: third ? "41%" : "26%" },
      {
        left: 64,
        right: 66,
        top: third ? "62%" : "79%",
        bottom: third ? "26%" : 55,
      },
      ...(third ? [{ left: 64, right: 66, top: "79%", bottom: 55 }] : []),
    ];
    const axes = grids.map((_, i) => ({
      type: "category" as const,
      gridIndex: i,
      data: dates,
      boundaryGap: true,
      axisLine: { lineStyle: { color: border } },
      axisTick: { show: false },
      axisLabel: {
        show: i === grids.length - 1,
        color: text,
        hideOverlap: true,
        formatter: (value: string) =>
          new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", {
            timeZone: timezone,
            month: "short",
            day: "numeric",
          }).format(new Date(value)),
      },
      axisPointer: {
        show: true,
        label: { formatter: (p: { value: string }) => date(p.value, true) },
      },
    }));
    const yaxes = grids.map((_, i) => ({
      type: "value" as const,
      gridIndex: i,
      scale: true,
      ...(i === 0 && !autoscale && priceBounds
        ? { min: priceBounds.min, max: priceBounds.max }
        : {}),
      position: "right" as const,
      axisLabel: {
        color: text,
        formatter: (value: number) =>
          Math.abs(value) >= 1000000
            ? `${(value / 1000000).toFixed(1)}m`
            : Math.abs(value) >= 1000
              ? `${(value / 1000).toFixed(1)}k`
              : String(Number(value.toFixed(2))),
      },
      splitLine: {
        show: i === 0,
        lineStyle: { color: border, type: "dashed" as const },
      },
      axisLine: { show: false },
      axisPointer: { label: { show: true } },
    }));
    const series: echarts.SeriesOption[] = [
      {
        name: "OHLC",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: bars.map((b) => [b.open, b.close, b.low, b.high]),
        itemStyle: {
          color: "#a5dbbd",
          color0: "#d89e87",
          borderColor: "#a5dbbd",
          borderColor0: "#d89e87",
        },
        barMaxWidth: 12,
      },
      {
        name: t("Объём", "Volume"),
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: bars.map((b) => ({
          value: b.volume,
          itemStyle: { color: b.close >= b.open ? "#a5dbbd75" : "#d89e8765" },
        })),
      },
    ];
    indicators.forEach((line, index) => {
      const config = configs.find((c) => c.id === line.id);
      if (!config) return;
      const pane = choices.find((x) => x.kind === config.kind)?.pane;
      if (pane && config.id !== oscillator?.id) return;
      series.push({
        name: `${config.kind.toUpperCase()} ${config.params.period || ""}`,
        type: config.kind === "macd" ? "bar" : "line",
        xAxisIndex: pane ? 2 : 0,
        yAxisIndex: pane ? 2 : 0,
        data: line.values,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { width: 1.35, color: palette[index % palette.length] },
        itemStyle: { color: palette[index % palette.length] },
        animation: false,
      } as echarts.SeriesOption);
    });
    const eventData = orders
      .map((order, index) => {
        const clock =
          order.execution_time || order.decision_time || order.signal_time;
        if (!clock || !bars.length) return null;
        const clockMs = Date.parse(clock);
        if (
          !Number.isFinite(clockMs) ||
          clockMs < bars[0].timestamp ||
          clockMs >= bars.at(-1)!.timestamp + (Number.isFinite(step) ? step : 1)
        )
          return null;
        const barIndex = nearest(clock);
        if (Number.isFinite(step) && clockMs >= bars[barIndex].timestamp + step)
          return null;
        return {
          value: [
            barIndex,
            order.fill_price || order.reference_price || bars[barIndex]?.close,
          ],
          eventIndex: index,
          symbol: order.status === "executed" ? "triangle" : "diamond",
          symbolRotate: order.action === "exit" ? 180 : 0,
          symbolSize: order.status === "executed" ? 12 : 7,
          itemStyle: {
            color:
              order.status === "executed"
                ? order.action === "enter"
                  ? "#b6ebcb"
                  : "#e5ac91"
                : "#8d9f9d",
          },
          name: `${order.action} / ${order.status}`,
        };
      })
      .filter(Boolean);
    if (eventData.length)
      series.push({
        name: t("События движка", "Engine events"),
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: eventData,
        z: 8,
      } as echarts.SeriesOption);
    for (const [key, label, color] of [
      ["stop_price", "Stop", "#d89e87"],
      ["take_profit_price", "Take profit", "#a5c8d6"],
      ["trailing_stop_price", "Trailing stop", "#d7b58a"],
    ] as const) {
      if (account.some((a) => a[key] != null)) {
        const map = new Map(account.map((a) => [a.time, a[key]]));
        series.push({
          name: label,
          type: "line",
          xAxisIndex: 0,
          yAxisIndex: 0,
          data: bars.map((b) => map.get(b.time) ?? null),
          connectNulls: false,
          showSymbol: false,
          step: "end",
          lineStyle: { width: 1, type: "dashed", color },
          itemStyle: { color },
        });
      }
    }
    return {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "IBM Plex Sans", color: text },
      legend: {
        type: "scroll",
        left: 12,
        top: 4,
        right: 12,
        itemHeight: 8,
        textStyle: { fontSize: 11, color: text },
      },
      grid: grids,
      xAxis: axes,
      yAxis: yaxes,
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
        type: "cross",
        lineStyle: { color: "#748d89", type: "dashed" },
      },
      tooltip: {
        trigger: "axis",
        renderMode: "richText",
        confine: true,
        backgroundColor: dark ? "#1c292b" : "#fff",
        borderColor: border,
        textStyle: { color: dark ? "#edf4f0" : "#1f302b", fontSize: 12 },
        formatter: (parameters: any) => {
          const entries = Array.isArray(parameters) ? parameters : [parameters];
          const i = entries[0]?.dataIndex,
            bar = bars[i];
          if (!bar) return "";
          return [
            date(bar.time, true) + ` · ${timezone}`,
            `O ${format(bar.open)}   H ${format(bar.high)}`,
            `L ${format(bar.low)}   C ${format(bar.close)}`,
            `${t("Объём", "Volume")} ${format(bar.volume, 3)}`,
            ...entries
              .filter(
                (p: any) =>
                  !["OHLC", t("Объём", "Volume")].includes(p.seriesName),
              )
              .map(
                (p: any) =>
                  `${p.seriesName}: ${Array.isArray(p.value) ? format(p.value[1]) : format(p.value)}`,
              ),
          ].join("\n");
        },
      },
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: grids.map((_, i) => i),
          start: 75,
          end: 100,
        },
        {
          type: "slider",
          xAxisIndex: grids.map((_, i) => i),
          height: 18,
          bottom: 8,
          borderColor: border,
          fillerColor: "#a5dbbd22",
          handleStyle: { color: "#a5dbbd" },
          textStyle: { color: text },
          start: 75,
          end: 100,
        },
      ],
      series,
    } as echarts.EChartsOption;
  }, [
    bars,
    indicators,
    configs,
    orders,
    account,
    theme,
    locale,
    t,
    date,
    timezone,
    format,
    autoscale,
    priceBounds,
  ]);
  useEffect(() => {
    if (!element.current) return;
    const chart = echarts.init(element.current, undefined, {
      renderer: "canvas",
    });
    chart.setOption(option);
    chart.on("click", (p: any) => {
      if (p.data?.eventIndex != null) onEvent?.(p.data.eventIndex);
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option, onEvent, reset]);
  return (
    <div
      className="financial-chart"
      data-testid="candlestick-chart"
      role="img"
      aria-label={t(
        "Свечной график с объёмом и индикаторами. Колесо — масштаб, перетаскивание — прокрутка.",
        "Candlestick chart with volume and indicators. Scroll to zoom, drag to pan.",
      )}
      ref={element}
      style={{ height, width: "100%" }}
    />
  );
}

export default function MarketTerminal({
  run,
  embedded = false,
}: {
  run?: Run;
  embedded?: boolean;
}) {
  const { t, date, format, notify } = useApp();
  const datasets = useLoad(() => api<Dataset[]>("/datasets"));
  const [datasetChoice, setDatasetId] = useState(
      run?.dataset?.id || "",
    ),
    [configs, setConfigs] = useState<IndicatorConfig[]>(defaultIndicators),
    [selectedIndicator, setSelectedIndicator] = useState("ema"),
    [period, setPeriod] = useState(20),
    [fullscreen, setFullscreen] = useState(false),
    [settings, setSettings] = useState(false),
    [autoscale, setAutoscale] = useState(true),
    [reset, setReset] = useState(0),
    [eventIndex, setEventIndex] = useState<number | null>(null),
    [filter, setFilter] = useState("all"),
    [selectedDecision, setSelectedDecision] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [manualPrice, setManualPrice] = useState({ min: "", max: "" });
  const [periodRange, setPeriodRange] = useState({
    start: run ? String(run.config.start) : "",
    end: run ? String(run.config.end) : "",
  });
  const preferencesKey = run ? `run-${run.id}` : "market-terminal";
  const datasetId = datasetChoice || preferredDataset(datasets.data || [])?.id || "";
  const market = useLoad(
    () =>
      datasetId ? api<MarketResponse>(
        `/market/chart?dataset_id=${encodeURIComponent(datasetId)}&limit=5000${periodRange.start ? `&start=${periodRange.start}` : ""}${periodRange.end ? `&end=${periodRange.end}` : ""}&indicators=${encodeURIComponent(JSON.stringify(configs))}`,
      ) : Promise.resolve(null),
    [datasetId, configs, periodRange],
  );
  useEffect(() => {
    if (!datasets.data) return;
    let active = true;
    api<{ preferences: Record<string, any> }>(
      `/chart-preferences/${preferencesKey}`,
    )
      .then((r) => {
        if (!active) return;
        const prefs = r.preferences;
        const savedSourceAvailable = typeof prefs?.dataset_id === "string" &&
          datasets.data!.some((d) => d.id === prefs.dataset_id && datasetIsAvailable(d));
        if (Array.isArray(prefs?.indicators) && prefs.indicators.length <= 8)
          setConfigs(prefs.indicators);
        if (typeof prefs?.autoscale === "boolean")
          setAutoscale(prefs.autoscale);
        if (
          prefs?.price_bounds &&
          typeof prefs.price_bounds.min === "number" &&
          typeof prefs.price_bounds.max === "number" &&
          prefs.price_bounds.min > 0 &&
          prefs.price_bounds.min < prefs.price_bounds.max
        )
          setManualPrice({
            min: String(prefs.price_bounds.min),
            max: String(prefs.price_bounds.max),
          });
        if (
          !run &&
          savedSourceAvailable
        )
          setDatasetId(prefs.dataset_id);
        if (
          !run &&
          (!prefs?.dataset_id || savedSourceAvailable) &&
          typeof prefs?.start === "string" &&
          typeof prefs?.end === "string" &&
          (!prefs.start || /^20[0-2][0-9]-\d{2}-\d{2}$/.test(prefs.start)) &&
          (!prefs.end || /^20[0-2][0-9]-\d{2}-\d{2}$/.test(prefs.end))
        )
          setPeriodRange({ start: prefs.start, end: prefs.end });
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [preferencesKey, datasets.data, run]);
  useEffect(() => {
    const update = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);
  const priceBounds =
    Number(manualPrice.min) > 0 &&
    Number(manualPrice.max) > Number(manualPrice.min)
      ? { min: Number(manualPrice.min), max: Number(manualPrice.max) }
      : undefined;
  const savePrefs = async () => {
    try {
      await put(`/chart-preferences/${preferencesKey}`, {
        preferences: {
          indicators: configs,
          autoscale,
          dataset_id: datasetId,
          ...periodRange,
          ...(priceBounds ? { price_bounds: priceBounds } : {}),
        },
      });
      notify(t("Настройки графика сохранены", "Chart preferences saved"));
    } catch (e: any) {
      notify(e.message, true);
    }
  };
  const orders = run?.traces?.orders || [],
    decisions = run?.traces?.decisions || [],
    account = run?.traces?.account || [];
  const event = eventIndex == null ? null : orders[eventIndex];
  const decision = decisions.find(
    (d) => d.id === (selectedDecision || event?.decision_id),
  );
  const visibleOrders = orders
    .map((order, index) => ({ order, index }))
    .filter(({ order }) => filter === "all" || order.status === filter);
  const activeDataset =
    datasets.data?.find((d) => d.id === datasetId) || run?.dataset;
  const addIndicator = () => {
    const definition = choices.find((c) => c.kind === selectedIndicator);
    if (!definition || configs.length >= 8) return;
    const params: Record<string, number | string> = {
      ...definition.params,
      ...("period" in definition.params ? { period } : {}),
    };
    const extra: IndicatorConfig[] = [
      {
        id: `${selectedIndicator}_${crypto.randomUUID().slice(0, 8)}`,
        kind: selectedIndicator,
        params,
      },
    ];
    if (
      ["bollinger", "donchian"].includes(selectedIndicator) &&
      configs.length <= 6
    )
      extra.push({
        id: `${selectedIndicator}_lower_${crypto.randomUUID().slice(0, 8)}`,
        kind: selectedIndicator,
        params: { ...params, output: "lower" },
      });
    setConfigs([
      ...configs.filter(
        (c) =>
          !(choices.find((x) => x.kind === c.kind)?.pane && definition.pane),
      ),
      ...extra,
    ]);
  };
  return (
    <div
      className={`market-studio ${embedded ? "embedded" : ""} ${fullscreen ? "is-fullscreen" : ""}`}
      ref={panel}
    >
      {!embedded && (
        <div className="studio-page-head">
          <div>
            <div className="eyebrow">MARKET / RESEARCH TERMINAL</div>
            <h1>{t("Рынок под микроскопом", "Market under the microscope")}</h1>
            <p>
              {t(
                "Архивные свечи или явно обозначенное синтетическое демо. Видимые допущения. Никаких текущих котировок.",
                "Archived candles or explicitly labelled synthetic demo. Visible assumptions. No live-quote claim.",
              )}
            </p>
          </div>
          <Badge tone="ice">ARCHIVE / DEMO ? NOT LIVE</Badge>
        </div>
      )}
      {activeDataset?.source_type === "synthetic_demo" && (
        <Notice>{t(
          "Показаны синтетические демонстрационные свечи, а не реальные рыночные наблюдения. Локальные архивы не подменяются демонстрационными данными.",
          "These are synthetic demonstration candles, not real market observations. Demo data never substitutes for a requested archive.",
        )}</Notice>
      )}
      {activeDataset?.status === "unavailable" && (
        <Notice>{activeDataset.error || t("Архив не установлен.", "The archive is not installed.")}</Notice>
      )}
      <section className="panel terminal-panel">
        <div className="terminal-toolbar">
          <div className="terminal-market-controls">
            <CandlestickChart size={20} />
            <select
              data-testid="chart-dataset"
              aria-label={t("Рынок и интервал", "Market and interval")}
              value={datasetId}
              disabled={!!run}
              onChange={(e) => {
                setDatasetId(e.target.value);
                setPeriodRange({ start: "", end: "" });
              }}
            >
              {(datasets.data || [])
                .map((d) => (
                  <option key={d.id} value={d.id} disabled={!datasetIsAvailable(d)} title={d.error}>
                    {d.symbol} · {d.timeframe} ·{" "}
                    {d.source_type === "synthetic_demo" ? "DEMO" : "ARCHIVE"}{!datasetIsAvailable(d) ? t(" — недоступен", " — unavailable") : ""}
                  </option>
                ))}
            </select>
            <SourceBadge type={activeDataset?.source_type} />
          </div>
          <div className="terminal-buttons">
            <button
              className={`icon-btn ${settings ? "active" : ""}`}
              onClick={() => setSettings(!settings)}
              title={t("Индикаторы и настройки", "Indicators and preferences")}
              aria-label={t(
                "Индикаторы и настройки",
                "Indicators and preferences",
              )}
            >
              <Settings2 size={17} />
            </button>
            <button
              className="icon-btn"
              onClick={() => setReset((v) => v + 1)}
              title={t("Сбросить масштаб", "Reset zoom")}
              aria-label={t("Сбросить масштаб", "Reset zoom")}
            >
              <RefreshCw size={16} />
            </button>
            <button
              className="icon-btn"
              onClick={async () => {
                if (document.fullscreenElement) await document.exitFullscreen();
                else await panel.current?.requestFullscreen();
              }}
              aria-label={t("Полноэкранный график", "Fullscreen chart")}
            >
              {fullscreen ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
            </button>
          </div>
        </div>
        {settings && (
          <div className="chart-settings" data-testid="chart-settings">
            <label>
              {t("Индикатор", "Indicator")}
              <select
                value={selectedIndicator}
                onChange={(e) => setSelectedIndicator(e.target.value)}
              >
                {choices.map((c) => (
                  <option key={c.kind} value={c.kind}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("Период, свечей", "Period, bars")}
              <input
                type="number"
                value={period}
                min={2}
                max={500}
                onChange={(e) =>
                  setPeriod(Math.max(2, Math.min(500, +e.target.value)))
                }
              />
            </label>
            <button
              className="btn secondary"
              disabled={configs.length >= 8}
              onClick={addIndicator}
            >
              {t("Добавить", "Add")}
            </button>
            <label className="checkbox-label">
              <input
                data-testid="chart-autoscale"
                type="checkbox"
                checked={autoscale}
                onChange={(e) => {
                  setAutoscale(e.target.checked);
                  if (
                    !e.target.checked &&
                    !priceBounds &&
                    market.data?.bars.length
                  ) {
                    const values = market.data.bars;
                    setManualPrice({
                      min: String(
                        Number(
                          (
                            Math.min(...values.map((b) => b.low)) * 0.98
                          ).toPrecision(8),
                        ),
                      ),
                      max: String(
                        Number(
                          (
                            Math.max(...values.map((b) => b.high)) * 1.02
                          ).toPrecision(8),
                        ),
                      ),
                    });
                  }
                }}
              />
              {t("Автомасштаб цены", "Price autoscale")}
            </label>
            {!autoscale && (
              <>
                <label>
                  {t("Мин. цена", "Min. price")}
                  <input
                    data-testid="chart-price-min"
                    type="number"
                    min={0.00000001}
                    step="any"
                    value={manualPrice.min}
                    onChange={(e) =>
                      setManualPrice({ ...manualPrice, min: e.target.value })
                    }
                  />
                </label>
                <label>
                  {t("Макс. цена", "Max. price")}
                  <input
                    data-testid="chart-price-max"
                    type="number"
                    min={0.00000001}
                    step="any"
                    value={manualPrice.max}
                    onChange={(e) =>
                      setManualPrice({ ...manualPrice, max: e.target.value })
                    }
                  />
                </label>
              </>
            )}
            <button
              className="btn secondary"
              disabled={!autoscale && !priceBounds}
              onClick={() => void savePrefs()}
            >
              {t("Сохранить вид", "Save layout")}
            </button>
          </div>
        )}
        {!run && (
          <div className="chart-range-controls">
            <label>
              {t("С, UTC", "From, UTC")}
              <input
                data-testid="chart-start"
                type="date"
                min={activeDataset?.start.slice(0, 10)}
                max={
                  periodRange.end ||
                  activeDataset?.end.slice(0, 10) ||
                  "2025-12-31"
                }
                value={periodRange.start}
                onChange={(e) =>
                  setPeriodRange({ ...periodRange, start: e.target.value })
                }
              />
            </label>
            <label>
              {t("По, UTC", "Through, UTC")}
              <input
                data-testid="chart-end"
                type="date"
                min={periodRange.start || activeDataset?.start.slice(0, 10)}
                max={activeDataset?.end.slice(0, 10) || "2025-12-31"}
                value={periodRange.end}
                onChange={(e) =>
                  setPeriodRange({ ...periodRange, end: e.target.value })
                }
              />
            </label>
            <button
              className="text-button"
              onClick={() => setPeriodRange({ start: "", end: "" })}
            >
              {t("Весь доступный диапазон", "All available dates")}
            </button>
          </div>
        )}
        <div className="chart-indicator-chips">
          {configs.map((c) => (
            <button
              key={c.id}
              onClick={() => setConfigs(configs.filter((x) => x.id !== c.id))}
              title={t("Убрать индикатор", "Remove indicator")}
            >
              {c.kind.toUpperCase()} {c.params.period || ""}
              <X size={11} />
            </button>
          ))}
          <span>
            <Crosshair size={12} />
            {t("Курсор · прокрутка · масштаб", "Crosshair · pan · zoom")}
          </span>
        </div>
        {!autoscale && !priceBounds && (
          <Notice>
            {t(
              "Задайте положительную минимальную цену и большую максимальную. До этого используется автоматический масштаб.",
              "Set a positive minimum price and a larger maximum. Automatic scaling applies until both are valid.",
            )}
          </Notice>
        )}
        {market.loading ? (
          <Spinner
            label={t(
              "Проверяем источник и рассчитываем индикаторы…",
              "Verifying the source and calculating indicators…",
            )}
          />
        ) : market.error ? (
          <ErrorPanel message={market.error} retry={market.reload} />
        ) : market.data?.bars.length ? (
          <FinancialChart
            bars={market.data.bars}
            indicators={market.data.indicators || []}
            configs={configs}
            orders={orders}
            account={account}
            onEvent={setEventIndex}
            autoscale={autoscale}
            priceBounds={priceBounds}
            reset={reset}
            height={
              fullscreen
                ? Math.max(500, window.innerHeight - 210)
                : embedded
                  ? 560
                  : 620
            }
          />
        ) : (
          <Empty
            icon={CandlestickChart}
            title={t("Недостаточно свечей", "Insufficient candles")}
            text={t(
              "Измените диапазон или выберите поддерживаемый набор.",
              "Change the range or select a supported dataset.",
            )}
          />
        )}
        <div className="terminal-status">
          <span>
            <ShieldCheck size={13} />
            {activeDataset?.symbol} · {format(market.data?.bars.length, 0)}{" "}
            {t("свечей", "candles")} · {activeDataset?.timeframe}
          </span>
          <span>
            {market.data?.bars[0] && date(market.data.bars[0].time)} —{" "}
            {market.data?.bars.at(-1) && date(market.data.bars.at(-1)!.time)}
          </span>
          <code>{(activeDataset?.sha256 || "").slice(0, 16)}</code>
        </div>
      </section>
      {market.data?.indicators
        ?.filter((line) => line.status && line.status !== "available")
        .map((line) => (
          <Notice key={line.id}>
            {line.kind.toUpperCase()}:{" "}
            {line.message ||
              t(
                "Входы недоступны. Значения не подставлены.",
                "Required inputs are unavailable; no values substituted.",
              )}
          </Notice>
        ))}
      {settings && (
        <p className="chart-pane-note">
          {t(
            "Отдельная панель поддерживает один осциллятор: новый заменяет предыдущий. Полосы/каналы настраиваются верхним и нижним выходом отдельно.",
            "The separate pane supports one oscillator: a new one replaces the previous. Bands/channels use separately configured upper and lower outputs.",
          )}
        </p>
      )}
      {market.data?.truncated && (
        <Notice>
          {t(
            "Ответ ограничен последними 5 000 свечами выбранного диапазона. Индикаторы прогреты на более ранней истории; график не меняет сохранённые результаты теста.",
            "The response contains the last 5,000 candles of the selected range. Indicators use earlier history for warm-up; the chart does not change saved backtest results.",
          )}
        </Notice>
      )}
      <div className="chart-source-row">
        <details>
          <summary>
            <Layers3 size={14} />
            {t("Данные, разрывы и происхождение", "Data, gaps and provenance")}
          </summary>
          <pre className="json-block">
            {JSON.stringify(
              {
                gaps: market.data?.gaps,
                warmup_bars: market.data?.warmup_bars,
                provenance: market.data?.provenance,
              },
              null,
              2,
            )}
          </pre>
        </details>
        {!run && (
          <Link className="text-button" to="/new">
            {t("Перейти к правилам", "Build strategy rules")}
            <ArrowUpRight size={14} />
          </Link>
        )}
      </div>
      {run && (
        <section className="trace-layout">
          <div className="panel trace-timeline">
            <div className="panel-head">
              <h2>
                <Bot size={17} />
                {t("События стратегии", "Strategy events")}
              </h2>
              <select
                aria-label={t("Фильтр событий", "Event filter")}
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">{t("Все события", "All events")}</option>
                {["submitted", "executed", "cancelled", "rejected"].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            {!run.traces ? (
              <Empty
                icon={Bot}
                title={t(
                  "Старый результат без трассировки",
                  "Legacy result without traces",
                )}
                text={t(
                  "Движок v1 не сохранял причинные состояния. Объяснения не восстановлены задним числом. Новый тест v2 сохранит их.",
                  "Engine v1 did not save causal states. Explanations are not reconstructed after the fact. A new v2 run will save them.",
                )}
              />
            ) : (
              <>
                <div className="timeline-rows">
                  {visibleOrders.length ? (
                    visibleOrders.map(({ order, index }) => (
                      <button
                        key={order.event_id || `${order.id}-${index}`}
                        data-testid={`trace-event-${index}`}
                        className={`trace-row ${eventIndex === index ? "selected" : ""}`}
                        onClick={() => {
                          setEventIndex(index);
                          setSelectedDecision(null);
                        }}
                      >
                        <span
                          className={`trace-event-dot ${order.status === "executed" ? "executed" : ""}`}
                        />
                        <div>
                          <b>
                            {order.action === "enter"
                              ? t("Вход", "Entry")
                              : t("Выход", "Exit")}{" "}
                            <Badge
                              tone={order.status === "executed" ? "mint" : ""}
                            >
                              {order.status}
                            </Badge>
                          </b>
                          <small>
                            {order.execution_time || order.decision_time
                              ? date(
                                  order.execution_time || order.decision_time!,
                                  true,
                                )
                              : "—"}
                          </small>
                          <span>{order.reason}</span>
                        </div>
                        <code>
                          {order.fill_price == null
                            ? "—"
                            : format(order.fill_price)}
                        </code>
                      </button>
                    ))
                  ) : (
                    <p className="padded muted">
                      {t(
                        "Ордеров с этим статусом нет.",
                        "No orders with this status.",
                      )}
                    </p>
                  )}
                </div>
                {run.traces.truncated && (
                  <Notice>
                    {t(
                      "Хранилище трассировки ограничено. Часть событий не сохранена; метрики рассчитаны по полному прогону.",
                      "Trace storage is bounded. Some records were not saved; metrics use the full run.",
                    )}
                  </Notice>
                )}
                <details className="padded">
                  <summary>
                    {t(
                      "Просмотреть решения без ордера",
                      "Inspect decisions without an order",
                    )}{" "}
                    ({decisions.length})
                  </summary>
                  <select
                    value={selectedDecision || ""}
                    onChange={(e) => {
                      setSelectedDecision(e.target.value);
                      setEventIndex(null);
                    }}
                  >
                    <option value="">
                      {t("Выберите решение", "Select a decision")}
                    </option>
                    {decisions.map((d) => (
                      <option key={d.id} value={d.id}>
                        {date(d.decision_time, true)} ·{" "}
                        {d.action || "no action"}
                      </option>
                    ))}
                  </select>
                </details>
              </>
            )}
          </div>
          <aside className="panel logic-inspector">
            <div className="panel-head">
              <h2>{t("Что было известно боту", "What the bot knew")}</h2>
              <Badge>ENGINE TRACE</Badge>
            </div>
            {!event && !decision ? (
              <Empty
                icon={Crosshair}
                title={t("Выберите событие", "Select an event")}
                text={t(
                  "Нажмите маркер на графике или строку журнала. Здесь появятся сохранённые условия, часы и состояние счёта.",
                  "Click a chart marker or timeline row to inspect saved conditions, clocks and account state.",
                )}
              />
            ) : (
              <div className="padded">
                {event && (
                  <>
                    <div className="logic-inspector-title">
                      <Badge tone="mint">
                        {event.action} / {event.status}
                      </Badge>
                      <code>{event.id}</code>
                    </div>
                    <dl className="definition-list">
                      {[
                        [
                          t("Сигнальная свеча", "Signal candle"),
                          event.signal_time,
                        ],
                        [t("Решение", "Decision"), event.decision_time],
                        [
                          t("Ордер допустим", "Order eligible"),
                          event.eligible_at,
                        ],
                        [t("Исполнение", "Execution"), event.execution_time],
                      ].map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{v ? date(v, true) : "—"}</dd>
                        </div>
                      ))}
                      <div>
                        <dt>{t("Ценовой ориентир", "Reference price")}</dt>
                        <dd>{format(event.reference_price)}</dd>
                      </div>
                      <div>
                        <dt>
                          {t("Цена с проскальзыванием", "Price after slippage")}
                        </dt>
                        <dd>{format(event.fill_price)}</dd>
                      </div>
                      <div>
                        <dt>
                          {t("Комиссия / проскальзывание", "Fee / slippage")}
                        </dt>
                        <dd>
                          {format(event.fee)} / {format(event.slippage_cost)}{" "}
                          USDT
                        </dd>
                      </div>
                    </dl>
                    <p>{event.reason}</p>
                    {event.time_precision === "bar_interval" && (
                      <Notice>
                        {t(
                          "Внутрисвечной порядок неизвестен: время обозначает интервал, а цена — консервативное правило симуляции. Это не подтверждённая заявка.",
                          "Intrabar sequencing is unknown: this timestamp denotes an interval and the price follows a conservative simulation rule. It is not a verified fill.",
                        )}
                      </Notice>
                    )}
                  </>
                )}
                {decision ? (
                  <>
                    <h4 className="section-mini-title">
                      {t(
                        "Причинное состояние условий",
                        "Causal condition state",
                      )}
                    </h4>
                    <div className="condition-values">
                      {Object.entries(decision.node_values).map(
                        ([key, value]) => (
                          <div key={key}>
                            <code>{key}</code>
                            <span
                              className={
                                value === true
                                  ? "positive"
                                  : value === false
                                    ? "negative"
                                    : "mono"
                              }
                            >
                              {value === null
                                ? t("Не готово", "Not ready")
                                : String(value)}
                            </span>
                          </div>
                        ),
                      )}
                    </div>
                    <details>
                      <summary>
                        {t("Точные часы и состояние", "Exact clocks and state")}
                      </summary>
                      <pre className="json-block">
                        {JSON.stringify(decision, null, 2)}
                      </pre>
                    </details>
                  </>
                ) : (
                  <Notice>
                    {t(
                      "Для этого события нет сохранённого решения — например, стоп определяется состоянием риска. Причина не выдумывается.",
                      "No saved decision is linked to this event; a stop may arise from risk state. No cause is invented.",
                    )}
                  </Notice>
                )}
                {event?.account_after && (
                  <pre className="json-block">
                    {JSON.stringify(event.account_after, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </aside>
        </section>
      )}
    </div>
  );
}
