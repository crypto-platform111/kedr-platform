import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as echarts from "echarts";
import {
  Activity,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Download,
  FileCheck2,
  GitBranch,
  Info,
  Layers3,
  Maximize2,
  Share2,
  ShieldCheck,
  Sparkles,
  Table2,
} from "lucide-react";
import { api, post, type Run } from "./api";
import {
  Badge,
  Empty,
  ErrorPanel,
  Metric,
  Modal,
  Notice,
  PageHead,
  SourceBadge,
  Spinner,
  useLoad,
} from "./components";
import { useApp } from "./context";
import { researchCopy } from "./researchCopy";
import MarketTerminal from "./charting";
import Copilot from "./copilot";
import FixedScenarios from "./scenarios";

export function Chart({
  option,
  height = 300,
  className = "",
}: {
  option: echarts.EChartsOption;
  height?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { theme, t } = useApp();
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.setOption(option);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option, theme]);
  return (
    <div
      ref={ref}
      role="img"
      aria-label={t(
        "Интерактивный график исследования",
        "Interactive research chart",
      )}
      className={`echart ${className}`}
      style={{ height, width: "100%" }}
    />
  );
}
export function useChartStyle() {
  const { theme, locale, timezone, date, format } = useApp();
  return useMemo(
    () => ({
      textStyle: {
        fontFamily: "IBM Plex Sans",
        color: theme === "dark" ? "#849795" : "#62716d",
        fontSize: 11,
      },
      backgroundColor: "transparent",
      animationDuration: 450,
      grid: { left: 45, right: 25, top: 28, bottom: 32 },
      tooltip: {
        trigger: "axis" as const,
        renderMode: "richText" as const,
        formatter: (
          params: echarts.TooltipComponentFormatterCallbackParams,
        ) => {
          const rows = Array.isArray(params) ? params : [params];
          const first = rows[0];
          const raw = first?.value;
          const clock = Array.isArray(raw) ? raw[0] : undefined;
          const header =
            typeof clock === "string" && !Number.isNaN(Date.parse(clock))
              ? `${date(clock, true)} · ${timezone}`
              : first?.name || "";
          return [
            header,
            ...rows.map((row) => {
              const value = Array.isArray(row.value) ? row.value[1] : row.value;
              return `${row.seriesName}: ${typeof value === "number" ? format(value) : String(value ?? "—")}`;
            }),
          ].join("\n");
        },
        backgroundColor: theme === "dark" ? "#1c292b" : "#ffffff",
        borderColor: theme === "dark" ? "#374443" : "#dbe4dd",
        textStyle: {
          color: theme === "dark" ? "#edf4f0" : "#1f302b",
          fontFamily: "IBM Plex Sans",
          fontSize: 12,
        },
      },
      xAxis: {
        type: "time" as const,
        axisLine: {
          lineStyle: { color: theme === "dark" ? "#2c3b3d" : "#dce4df" },
        },
        axisTick: { show: false },
        axisLabel: {
          hideOverlap: true,
          formatter: (value: number) =>
            new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", {
              timeZone: timezone,
              month: "short",
              year: "2-digit",
            }).format(new Date(value)),
        },
      },
      yAxis: {
        type: "value" as const,
        splitLine: {
          lineStyle: {
            color: theme === "dark" ? "#243234" : "#e4eae5",
            type: "dashed" as const,
          },
        },
      },
    }),
    [theme, locale, timezone, date, format],
  );
}
function download(name: string, data: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Results() {
  const { id = "" } = useParams();
  const { t, format, date, locale } = useApp();
  const request = useLoad(() => api<Run>(`/backtests/${id}`), id);
  const [tab, setTab] = useState("overview"),
    [range, setRange] = useState("all"),
    [publish, setPublish] = useState(false),
    [trade, setTrade] = useState<Run["trades"][number] | null>(null);
  const base = useChartStyle();
  const run = request.data;
  const equity = useMemo(() => {
    if (!run) return [];
    const rows = run.equity || [];
    if (range === "all" || !rows.length) return rows;
    const end = new Date(rows[rows.length - 1].time).getTime();
    const days = range === "1y" ? 365 : 180;
    return rows.filter(
      (r) => new Date(r.time).getTime() >= end - days * 86400000,
    );
  }, [run, range]);
  const equityOption: echarts.EChartsOption = useMemo(
    () => ({
      ...base,
      legend: {
        top: 0,
        right: 15,
        itemWidth: 15,
        itemHeight: 7,
        textStyle: base.textStyle,
        data: [
          t("Стратегия, нетто", "Strategy, net"),
          t("Пассивный ориентир", "Passive benchmark"),
        ],
      },
      yAxis: {
        ...base.yAxis,
        scale: true,
        axisLabel: {
          formatter: (v: number) =>
            Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v),
        },
      },
      dataZoom: [{ type: "inside", filterMode: "none" }],
      series: [
        {
          name: t("Стратегия, нетто", "Strategy, net"),
          type: "line",
          data: equity.map((e) => [e.time, e.equity]),
          showSymbol: false,
          lineStyle: { color: "#9edabc", width: 2 },
          itemStyle: { color: "#9edabc" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(158,218,188,.18)" },
              { offset: 1, color: "rgba(158,218,188,0)" },
            ]),
          },
        },
        {
          name: t("Пассивный ориентир", "Passive benchmark"),
          type: "line",
          data: equity.map((e) => [e.time, e.benchmark_equity]),
          showSymbol: false,
          lineStyle: { color: "#89aaba", width: 1.3, type: "dashed" },
          itemStyle: { color: "#89aaba" },
        },
      ],
    }),
    [equity, t, base],
  );
  const drawdownOption: echarts.EChartsOption = useMemo(
    () => ({
      ...base,
      grid: { left: 45, right: 25, top: 16, bottom: 28 },
      yAxis: { ...base.yAxis, axisLabel: { formatter: "{value}%" } },
      series: [
        {
          name: t("Просадка, %", "Drawdown, %"),
          type: "line",
          data: equity.map((e) => [e.time, -Math.abs(e.drawdown_pct)]),
          showSymbol: false,
          lineStyle: { color: "#cf9b7e", width: 1.4 },
          areaStyle: { color: "rgba(207,155,126,.17)" },
          itemStyle: { color: "#cf9b7e" },
        },
      ],
    }),
    [equity, t, base],
  );
  const priceOption: echarts.EChartsOption = useMemo(
    () => ({
      ...base,
      yAxis: { ...base.yAxis, scale: true },
      dataZoom: [{ type: "inside" }],
      series: [
        {
          name: t("Цена актива", "Asset price"),
          type: "line",
          data: equity.map((e) => [e.time, e.price]),
          showSymbol: false,
          lineStyle: { color: "#8ab4c3", width: 1.5 },
          itemStyle: { color: "#8ab4c3" },
        },
        {
          name: t("Вход", "Entry"),
          type: "scatter",
          data:
            run?.trades
              ?.filter((tr) => equity.length && tr.entry_time >= equity[0].time)
              .map((tr) => [tr.entry_time, tr.entry_price]) || [],
          symbol: "triangle",
          symbolSize: 9,
          itemStyle: {
            color: "#a1dcbf",
            borderColor: "#233b31",
            borderWidth: 1,
          },
        },
        {
          name: t("Выход", "Exit"),
          type: "scatter",
          data:
            run?.trades
              ?.filter(
                (tr) =>
                  tr.exit_time &&
                  equity.length &&
                  tr.exit_time >= equity[0].time,
              )
              .map((tr) => [tr.exit_time!, tr.exit_price!]) || [],
          symbol: "triangle",
          symbolRotate: 180,
          symbolSize: 9,
          itemStyle: { color: "#d29c80", borderWidth: 1 },
        },
      ],
    }),
    [equity, run, t, base],
  );
  const distribution = useMemo(() => {
    const values = (run?.equity || [])
      .slice(1)
      .map((row, i) => (row.equity / run!.equity[i].equity - 1) * 100)
      .filter(Number.isFinite);
    if (!values.length) return { labels: [], counts: [] };
    const min = Math.min(...values),
      max = Math.max(...values),
      width = Math.max((max - min) / 20, 0.00001);
    const counts = Array.from({ length: 20 }, () => 0);
    values.forEach(
      (v) => counts[Math.min(19, Math.floor((v - min) / width))]++,
    );
    return {
      labels: counts.map((_, i) => `${format(min + i * width, 1)}%`),
      counts,
    };
  }, [run, format]);
  if (request.loading)
    return (
      <Spinner
        label={t(
          "Открываем сохранённый результат…",
          "Loading the saved result…",
        )}
      />
    );
  if (request.error || !run)
    return (
      <ErrorPanel
        message={request.error || "No result"}
        retry={request.reload}
      />
    );
  const m = run.metrics || {},
    last = run.equity?.[run.equity.length - 1];
  const initial = Number(
    run.config?.initial_cash || run.equity?.[0]?.equity || 1,
  );
  const passiveReturn =
    last?.benchmark_equity == null
      ? null
      : (last.benchmark_equity / initial - 1) * 100;
  const tabs = [
    ["overview", t("Обзор результата", "Overview")],
    ["terminal", t("График и логика", "Chart & logic")],
    ["trades", t("Журнал сделок", "Trades")],
    ["scenarios", t("Фиксированные проверки", "Fixed scenarios")],
    ["copilot", t("Помощник", "Copilot")],
    ["quality", t("Качество исследования", "Research quality")],
    ["details", t("Методология и версии", "Methodology & versions")],
  ];
  const metricCards = [
    [
      t("Чистая доходность", "Net return"),
      `${format(m.net_return_pct)}%`,
      t("После комиссии и проскальзывания", "After fees and slippage"),
    ],
    [
      t("Максимальная просадка", "Maximum drawdown"),
      `${format(m.max_drawdown_pct)}%`,
      `${format(m.longest_drawdown_days, 0)} ${t("дней под максимумом", "days below peak")}`,
    ],
    [
      "Sharpe",
      format(m.sharpe),
      t(
        "Историческая оценка, не гарантия",
        "Historical estimate, not a guarantee",
      ),
    ],
    [
      t("Завершённые сделки", "Closed trades"),
      format(m.total_trades, 0),
      `${t("В рынке", "Exposure")}: ${format(m.exposure_pct, 1)}%`,
    ],
  ];
  return (
    <>
      <div className="result-back">
        <Link to={`/builder/${run.strategy_id}`} className="text-button">
          <ArrowLeft size={15} />
          {t("К стратегии", "Back to strategy")}
        </Link>
        <span className="mono">RUN / {id.slice(0, 12)}</span>
      </div>
      <PageHead
        eyebrow={t("СОХРАНЁННОЕ ИССЛЕДОВАНИЕ", "SAVED RESEARCH")}
        title={
          run.strategy_name ||
          t("Результат исторического теста", "Historical backtest result")
        }
        description={`${run.dataset?.symbol || ""} · ${run.dataset?.timeframe || "4h"} · ${date(String(run.config?.start))} — ${date(String(run.config?.end))}`}
        actions={
          <>
            <button
              className="btn secondary"
              onClick={() =>
                download(`kedr-run-${id}.json`, JSON.stringify(run, null, 2))
              }
            >
              <Download size={15} />
              {t("Экспорт", "Export")}
            </button>
            <button
              className="btn primary"
              data-testid="publish-result"
              onClick={() => setPublish(true)}
            >
              <Share2 size={15} />
              {t("Поделиться версией", "Share version")}
            </button>
          </>
        }
      />
      <div className="result-context">
        <SourceBadge
          type={run.quality?.source_type || run.dataset?.source_type}
        />
        <Badge>{t("Историческая симуляция", "Historical simulation")}</Badge>
        <Badge>
          {t("Без независимой валидации", "No independent validation")}
        </Badge>
        <span className="context-time">
          <CheckCheckIcon />
          {t("Точная версия сохранена", "Exact version preserved")}
        </span>
      </div>
      <div className="result-summary">
        {metricCards.map(([label, value, sub], i) => (
          <Metric
            key={label}
            label={label}
            value={value}
            sub={sub}
            positive={
              i === 0 && m.net_return_pct != null
                ? m.net_return_pct >= 0
                : undefined
            }
          />
        ))}
      </div>
      <div className="page-tabs">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            data-testid={`result-tab-${key}`}
            className={tab === key ? "active" : ""}
            onClick={() => setTab(key)}
          >
            {label}
            {key === "trades" && <span>{run.trades?.length || 0}</span>}
          </button>
        ))}
      </div>
      {tab === "terminal" && <MarketTerminal run={run} embedded/>}
      {tab === "scenarios" && <FixedScenarios run={run}/>}
      {tab === "copilot" && <div className="results-copilot"><Copilot strategyId={run.strategy_id} runId={run.id}/></div>}
      {tab === "overview" && (
        <div className="result-overview">
          <section className="panel chart-panel">
            <div className="panel-head">
              <div>
                <h2>{t("Динамика капитала", "Equity trajectory")}</h2>
                <p>
                  {t(
                    "Нетто-капитал и пассивное владение · USDT",
                    "Net equity and passive holding · USDT",
                  )}
                </p>
              </div>
              <div className="chart-range">
                {[
                  ["6m", "6M"],
                  ["1y", "1Y"],
                  ["all", t("Всё", "All")],
                ].map(([key, label]) => (
                  <button
                    className={range === key ? "active" : ""}
                    key={key}
                    onClick={() => setRange(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {equity.length ? (
              <Chart option={equityOption} height={340} />
            ) : (
              <Empty
                title={t(
                  "Нет поддержанных наблюдений",
                  "No supported observations",
                )}
                text={t(
                  "Проверьте период и требования прогрева.",
                  "Check the date range and indicator warmup.",
                )}
              />
            )}
            <div className="chart-comparison">
              <div>
                <i className="mint-dot" />
                <span>{t("Стратегия", "Strategy")}</span>
                <b>{format(m.net_return_pct)}%</b>
              </div>
              <div>
                <i className="ice-dot" />
                <span>{t("Пассивный ориентир", "Passive benchmark")}</span>
                <b>{format(passiveReturn)}%</b>
              </div>
              <div>
                <span>{t("Конечный капитал", "Final equity")}</span>
                <b>{format(last?.equity)} USDT</b>
              </div>
            </div>
          </section>
          <section className="panel chart-panel">
            <div className="panel-head">
              <div>
                <h2>{t("Просадка", "Drawdown")}</h2>
                <p>
                  {t(
                    "Относительно предыдущего максимума капитала",
                    "Relative to the previous equity peak",
                  )}
                </p>
              </div>
              <Badge tone="amber">
                {format(m.max_drawdown_pct)}% {t("макс.", "max")}
              </Badge>
            </div>
            <Chart option={drawdownOption} height={180} />
          </section>
          <div className="analytics-two">
            <section className="panel chart-panel">
              <div className="panel-head">
                <div>
                  <h2>{t("Цена и сделки", "Price and executions")}</h2>
                  <p>
                    {t(
                      "Маркеры показывают моделируемое исполнение",
                      "Markers show simulated executions",
                    )}
                  </p>
                </div>
                <Activity size={17} />
              </div>
              <Chart option={priceOption} height={260} />
            </section>
            <section className="panel chart-panel">
              <div className="panel-head">
                <div>
                  <h2>
                    {t("Распределение доходностей", "Return distribution")}
                  </h2>
                  <p>
                    {t(
                      "Изменение нетто-капитала за свечу, %",
                      "Net equity change per bar, %",
                    )}
                  </p>
                </div>
              </div>
              <Chart
                option={{
                  ...base,
                  xAxis: {
                    type: "category",
                    data: distribution.labels,
                    axisLabel: { interval: 4, fontSize: 10 },
                    axisLine: { lineStyle: { color: base.textStyle.color } },
                    axisTick: { show: false },
                  },
                  yAxis: base.yAxis,
                  series: [
                    {
                      type: "bar",
                      data: distribution.counts,
                      itemStyle: {
                        color: "#83b5a2",
                        borderRadius: [2, 2, 0, 0],
                      },
                      barCategoryGap: "12%",
                    },
                  ],
                }}
                height={260}
              />
            </section>
          </div>
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>{t("Месяц за месяцем", "Month by month")}</h2>
                <p>
                  {t(
                    "Все месяцы, без отбора удачных периодов",
                    "Every month, with no favorable-period selection",
                  )}
                </p>
              </div>
              <Badge>{t("Нетто", "Net")}</Badge>
            </div>
            <MonthlyTable
              monthly={run.monthly || []}
              annual={run.annual || []}
            />
          </section>
          <div className="results-bottom-grid">
            <section className="panel key-metrics">
              <div className="panel-head">
                <h2>{t("Дополнительные показатели", "Additional metrics")}</h2>
              </div>
              {[
                [
                  t("CAGR · годовой темп роста", "CAGR · annualized growth"),
                  `${format(m.cagr_pct)}%`,
                ],
                [
                  t("Доля прибыльных сделок", "Win rate"),
                  `${format(m.win_rate_pct)}%`,
                ],
                [t("Фактор прибыли", "Profit factor"), format(m.profit_factor)],
                [t("Комиссии", "Fees"), `${format(m.fees)} USDT`],
                [
                  t("Стоимость проскальзывания", "Slippage cost"),
                  `${format(m.slippage_cost)} USDT`,
                ],
                [
                  t("Доходность до издержек¹", "Gross return¹"),
                  `${format(m.gross_return_pct)}%`,
                ],
              ].map(([label, val]) => (
                <div className="key-metric-row" key={label}>
                  <span>{label}</span>
                  <b>{val}</b>
                </div>
              ))}
              <small>
                {t(
                  "¹ Определение gross сохранено в методологии движка. Это не обещание результата без комиссий.",
                  "¹ The engine methodology defines gross. It is not a promise of cost-free performance.",
                )}
              </small>
            </section>
            <section className="analyst-callout">
              <div className="analyst-orb">
                <Sparkles size={31} strokeWidth={1.2} />
              </div>
              <Badge tone="mint">
                {t("ОФЛАЙН-ИССЛЕДОВАТЕЛЬ", "OFFLINE ANALYST")}
              </Badge>
              <h2>
                {t("Что стоит за цифрами?", "What is behind the numbers?")}
              </h2>
              <p>
                {t(
                  "Разберите измеренные риски, издержки и ограничения. Без выдуманных выводов и обещаний.",
                  "Review measured risks, costs and limitations. No invented conclusions or promises.",
                )}
              </p>
              <Link className="btn primary" to={`/analyst/${id}`}>
                {t("Открыть разбор", "Open the analysis")}
                <ArrowRight size={16} />
              </Link>
              <small>
                {t(
                  "Детерминированные правила, не генеративный AI",
                  "Deterministic rules, not generative AI",
                )}
              </small>
            </section>
          </div>
          <Notice>
            {t(
              "Результат зависит от выбранных правил, источника и издержек. Исторический тест не доказывает будущую прибыльность. «—» означает, что показатель не определён.",
              "Results depend on rules, source and costs. A historical backtest does not prove future profitability. “—” means a metric is undefined.",
            )}
          </Notice>
        </div>
      )}
      {tab === "trades" && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>
                {t(
                  "Каждая сделка — открыта для проверки",
                  "Every trade, open to inspection",
                )}
              </h2>
              <p>
                {t(
                  "Открытые позиции отмечены по последней цене, без вымышленного выхода.",
                  "Open positions are marked at the final price, without an invented exit.",
                )}
              </p>
            </div>
            <button
              className="btn secondary compact"
              onClick={() => {
                const keys = [
                  "entry_time",
                  "exit_time",
                  "entry_price",
                  "exit_price",
                  "quantity",
                  "net_pnl",
                  "fees",
                  "status",
                ];
                download(
                  `kedr-trades-${id}.csv`,
                  [
                    keys.join(","),
                    ...run.trades.map((tr) =>
                      keys.map((k) => String((tr as any)[k] ?? "")).join(","),
                    ),
                  ].join("\n"),
                  "text/csv",
                );
              }}
            >
              <Download size={14} />
              CSV
            </button>
          </div>
          {run.trades?.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>{t("Вход", "Entry")}</th>
                    <th>{t("Выход", "Exit")}</th>
                    <th>{t("Цена входа", "Entry price")}</th>
                    <th>{t("Цена выхода", "Exit price")}</th>
                    <th>{t("Объём", "Quantity")}</th>
                    <th>{t("Нетто, USDT", "Net, USDT")}</th>
                    <th>{t("Статус", "Status")}</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {run.trades.map((tr, i) => (
                    <tr
                      key={i}
                      onClick={() => setTrade(tr)}
                      className="clickable"
                    >
                      <td className="muted">
                        {String(i + 1).padStart(2, "0")}
                      </td>
                      <td>{date(tr.entry_time, true)}</td>
                      <td>{tr.exit_time ? date(tr.exit_time, true) : "—"}</td>
                      <td className="mono">{format(tr.entry_price)}</td>
                      <td className="mono">{format(tr.exit_price)}</td>
                      <td className="mono">{format(tr.quantity, 6)}</td>
                      <td
                        className={`mono ${(tr.net_pnl || 0) < 0 ? "negative" : "positive"}`}
                      >
                        {format(tr.net_pnl)}
                      </td>
                      <td>
                        <Badge tone={tr.status === "closed" ? "" : "amber"}>
                          {tr.status === "closed"
                            ? t("Закрыта", "Closed")
                            : t("Открыта", "Open")}
                        </Badge>
                      </td>
                      <td>
                        <ArrowUpRight size={14} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              icon={Table2}
              title={t("Нет исполненных сделок", "No executed trades")}
              text={t(
                "Условия могли не сработать или не пройти прогрев. Денежный результат сохраняется как есть.",
                "Conditions may not have fired or warmup may be insufficient. The account result is preserved as observed.",
              )}
            />
          )}
        </section>
      )}
      {tab === "quality" && (
        <div className="quality-layout">
          <section className="panel quality-card">
            <div className="panel-head">
              <h2>{t("Качество доказательств", "Evidence quality")}</h2>
              <ShieldCheck size={18} />
            </div>
            <div className="coverage-number">
              <span>
                {format(run.quality?.data_coverage_pct, 1)}
                <small>%</small>
              </span>
              <p>
                {t(
                  "Покрытие данных в выбранном интервале",
                  "Data coverage within the selected period",
                )}
              </p>
            </div>
            <div className="coverage-track">
              <i
                style={{
                  width: `${Math.min(100, run.quality?.data_coverage_pct || 0)}%`,
                }}
              />
            </div>
            <div className="quality-check">
              <Check size={15} />
              <div>
                <b>
                  {t(
                    "Версия и источник зафиксированы",
                    "Version and source preserved",
                  )}
                </b>
                <p>
                  {t(
                    "Правила и параметры этого запуска не меняются при редактировании стратегии.",
                    "This run’s rules and parameters do not change when you edit the draft.",
                  )}
                </p>
              </div>
            </div>
            <div className="quality-check">
              <Info size={15} />
              <div>
                <b>
                  {t(
                    "Независимая проверка отсутствует",
                    "No independent evaluation",
                  )}
                </b>
                <p>
                  {t(
                    "Период не зарегистрирован как нетронутая выборка. Повторный подбор параметров повышает риск переобучения.",
                    "The period is not registered as an untouched sample. Repeated parameter selection raises overfitting risk.",
                  )}
                </p>
              </div>
            </div>
            <div className="quality-check">
              <Info size={15} />
              <div>
                <b>
                  {t(
                    "Цена свечи — не подтверждённое исполнение",
                    "A candle price is not a verified fill",
                  )}
                </b>
                <p>
                  {t(
                    "Комиссия и проскальзывание заданы явно. Реальные спреды, глубина и задержки здесь не наблюдаются.",
                    "Fees and slippage are explicit. Actual spreads, depth and latency are not observed here.",
                  )}
                </p>
              </div>
            </div>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2>
                {t("Допущения и ограничения", "Assumptions & limitations")}
              </h2>
            </div>
            <div className="assumptions-list">
              {[
                ...(run.quality?.warnings || []),
                ...(run.quality?.assumptions || []),
              ].map((warning, i) => (
                <div key={i}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <p>{researchCopy(warning, locale)}</p>
                </div>
              ))}
            </div>
            <Notice>
              {t(
                "Небольшое число сделок и общие рыночные циклы ограничивают выводы. Сравнивайте с простыми ориентирами и сохраняйте отрицательные результаты.",
                "Few trades and shared market cycles limit conclusions. Compare simple benchmarks and preserve negative results.",
              )}
            </Notice>
          </section>
        </div>
      )}
      {tab === "details" && (
        <div className="details-grid">
          <section className="panel">
            <div className="panel-head">
              <h2>{t("Конфигурация запуска", "Run configuration")}</h2>
              <GitBranch size={17} />
            </div>
            <dl className="definition-list">
              {Object.entries(run.config || {}).map(([key, val]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{String(val)}</dd>
                </div>
              ))}
              <div>
                <dt>strategy_version</dt>
                <dd>{run.version_id}</dd>
              </div>
              <div>
                <dt>run_id</dt>
                <dd>{run.id}</dd>
              </div>
              <div>
                <dt>created_at</dt>
                <dd>{date(run.created_at, true)}</dd>
              </div>
            </dl>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2>
                {t("Происхождение и методология", "Provenance & methodology")}
              </h2>
              <FileCheck2 size={17} />
            </div>
            <pre className="json-block">
              {JSON.stringify(
                { dataset: run.dataset, provenance: run.provenance },
                null,
                2,
              )}
            </pre>
          </section>
        </div>
      )}
      {publish && <PublishModal run={run} onClose={() => setPublish(false)} />}{" "}
      {trade && (
        <Modal
          title={t("Детали исполнения", "Execution details")}
          onClose={() => setTrade(null)}
        >
          <dl className="definition-list">
            {Object.entries(trade).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v == null ? "—" : String(v)}</dd>
              </div>
            ))}
          </dl>
          <Notice>
            {t(
              "Все цены — моделируемое исполнение с заданным проскальзыванием. Это не биржевые квитанции.",
              "Prices are simulated executions with stated slippage, not exchange receipts.",
            )}
          </Notice>
        </Modal>
      )}
    </>
  );
}
function CheckCheckIcon() {
  return <Check size={13} />;
}
export function MonthlyTable({
  monthly,
  annual,
}: {
  monthly: Run["monthly"];
  annual: Run["annual"];
}) {
  const { t, locale, format } = useApp();
  const years = [...new Set(monthly.map((m) => m.period.slice(0, 4)))];
  const months = Array.from({ length: 12 }, (_, i) =>
    new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en", {
      month: "short",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(2024, i, 1))),
  );
  return (
    <div className="table-scroll monthly-table">
      <table>
        <thead>
          <tr>
            <th>{t("Год", "Year")}</th>
            {months.map((m) => (
              <th key={m}>{m}</th>
            ))}
            <th>{t("За год", "Year total")}</th>
          </tr>
        </thead>
        <tbody>
          {years.map((year) => (
            <tr key={year}>
              <td>{year}</td>
              {months.map((_, i) => {
                const item = monthly.find(
                  (m) =>
                    m.period === `${year}-${String(i + 1).padStart(2, "0")}`,
                );
                return (
                  <td key={i}>
                    <span
                      className={`heat-cell ${!item ? "absent" : item.return_pct >= 0 ? "gain" : "loss"}`}
                      style={
                        item
                          ? {
                              backgroundColor:
                                item.return_pct >= 0
                                  ? `rgba(136,199,166,${Math.min(0.3, 0.05 + Math.abs(item.return_pct) / 80)})`
                                  : `rgba(206,147,119,${Math.min(0.3, 0.05 + Math.abs(item.return_pct) / 80)})`,
                            }
                          : {}
                      }
                    >
                      {item ? `${format(item.return_pct, 1)}%` : "—"}
                    </span>
                  </td>
                );
              })}
              <td className="mono">
                {format(annual.find((a) => a.period === year)?.return_pct, 1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!years.length && (
        <p className="panel-footnote">
          {t(
            "Нет поддержанных месячных периодов.",
            "No supported monthly periods.",
          )}
        </p>
      )}
    </div>
  );
}
function PublishModal({ run, onClose }: { run: Run; onClose: () => void }) {
  const { t, notify } = useApp();
  const [description, setDescription] = useState(""),
    [tags, setTags] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Modal
      title={t("Поделиться исследованием", "Share your research")}
      onClose={onClose}
    >
      <Notice>
        {t(
          "Публикуется точная неизменяемая версия вместе с реальным результатом. Это воспроизводимая симуляция, а не независимое подтверждение доходности.",
          "Publishes the exact immutable version with its actual result. This is a reproducible simulation, not independent validation of profitability.",
        )}
      </Notice>
      <label>
        {t("Что исследовали?", "What did you investigate?")}
        <textarea
          rows={4}
          maxLength={2000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t(
            "Опишите идею и её ограничения",
            "Describe the idea and its limitations",
          )}
        />
      </label>
      <label>
        {t("Теги через запятую", "Tags, comma-separated")}
        <input
          value={tags}
          maxLength={200}
          onChange={(e) => setTags(e.target.value)}
          placeholder="trend, BTC, research"
        />
      </label>
      <div className="publication-preview">
        <SourceBadge type={run.dataset?.source_type} />
        <span>
          {run.dataset?.symbol} · {run.dataset?.timeframe}
        </span>
        <code>version / {run.version_id?.slice(0, 12)}</code>
      </div>
      {error && (
        <div className="inline-error" role="alert">
          {error}
        </div>
      )}
      <div className="modal-actions">
        <button className="btn secondary" onClick={onClose}>
          {t("Отмена", "Cancel")}
        </button>
        <button
          data-testid="confirm-publish"
          className="btn primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await post("/community", {
                strategy_id: run.strategy_id,
                version_id: run.version_id,
                run_id: run.id,
                description,
                tags: tags
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              });
              notify(
                t(
                  "Версия опубликована в библиотеке сообщества",
                  "Version published to the community library",
                ),
              );
              onClose();
            } catch (e: any) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Share2 size={14} />
          {busy
            ? t("Публикуем…", "Publishing…")
            : t("Опубликовать версию", "Publish version")}
        </button>
      </div>
    </Modal>
  );
}
