import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Command, GitCompareArrows, Search, X } from "lucide-react";
import { api, measuredCosts, type Run } from "./api";
import {
  Badge,
  Empty,
  ErrorPanel,
  Modal,
  Notice,
  PageHead,
  Spinner,
  useLoad,
} from "./components";
import { useApp } from "./context";
import { Chart, useChartStyle } from "./results";

export function CommandPalette() {
  const { t } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState("");
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const actions = [
    [
      "/new",
      t("Создать стратегию с нуля", "Create a strategy from scratch"),
      "strategy blank builder",
    ],
    [
      "/market",
      t("Открыть рыночный терминал", "Open market terminal"),
      "chart candles indicators",
    ],
    [
      "/compare",
      t("Сравнить сохранённые тесты", "Compare saved backtests"),
      "compare results research",
    ],
    [
      "/ml",
      t("ML: ограниченное обучение", "ML: bounded model training"),
      "model fit logistic ridge",
    ],
    [
      "/dashboard",
      t("Мои стратегии и результаты", "My strategies and results"),
      "dashboard home",
    ],
    [
      "/integrations",
      t("Статус провайдеров", "Provider status"),
      "AI settings connection",
    ],
    [
      "/settings",
      t("Настройки интерфейса", "Interface preferences"),
      "theme language timezone",
    ],
  ];
  return (
    <>
      <button
        className="command-trigger"
        aria-label={t("Командная палитра", "Command palette")}
        onClick={() => setOpen(true)}
      >
        <Search size={14} />
        <span>{t("Перейти к…", "Jump to…")}</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <Modal
          title={t("Команды рабочего пространства", "Workspace commands")}
          onClose={() => setOpen(false)}
        >
          <div className="search-input">
            <Search size={17} />
            <input
              autoFocus
              data-testid="command-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("Найти действие…", "Find an action…")}
            />
          </div>
          <div className="command-actions">
            {actions
              .filter(([path, title, keywords]) =>
                `${path} ${title} ${keywords}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map(([path, title]) => (
                <button
                  key={path}
                  onClick={() => {
                    navigate(path);
                    setOpen(false);
                  }}
                >
                  <Command size={15} />
                  <span>{title}</span>
                  <ArrowRight size={15} />
                </button>
              ))}
          </div>
        </Modal>
      )}
    </>
  );
}

export default function ComparisonWorkspace() {
  const { t, date, format } = useApp();
  const runs = useLoad(() => api<Run[]>("/backtests"));
  const [ids, setIds] = useState<string[]>([]);
  const details = useLoad(
    () => Promise.all(ids.map((id) => api<Run>(`/backtests/${id}`))),
    ids,
  );
  const base = useChartStyle();
  const selected = details.data || [];
  const check = (r: Run) =>
    JSON.stringify({
      dataset: r.dataset?.sha256,
      start: r.config.start,
      end: r.config.end,
      initial_cash: r.config.initial_cash,
      fee: r.config.fee_bps,
      slippage: r.config.slippage_bps,
      delay: r.config.execution_delay_bars,
      mode: r.config.execution_mode,
      engine: r.provenance?.engine_version,
    });
  const comparable =
    selected.length >= 2 &&
    selected.every((r) => check(r) === check(selected[0]));
  const series = selected.map((r, i) => ({
    name: r.strategy_name || r.id.slice(0, 8),
    type: "line" as const,
    showSymbol: false,
    data: r.equity.map((e) => [e.time, e.equity]),
    lineStyle: {
      width: 1.8,
      color: ["#a5dbbd", "#a5c8d6", "#d7b58a", "#c2abcf"][i],
    },
    itemStyle: { color: ["#a5dbbd", "#a5c8d6", "#d7b58a", "#c2abcf"][i] },
  }));
  return (
    <>
      <PageHead
        eyebrow="RESEARCH / COMPARE"
        title={t(
          "Правила рядом. Допущения видны.",
          "Rules side by side. Assumptions visible.",
        )}
        description={t(
          "Сравните до четырёх реальных сохранённых тестов. Разные данные, затраты или часы исполнения делают сопоставление описательным.",
          "Compare up to four actual saved backtests. Different data, costs or execution clocks make the comparison descriptive.",
        )}
        actions={
          <Badge tone="ice">
            <GitCompareArrows size={13} />
            SAVED RUNS
          </Badge>
        }
      />
      <div className="comparison-layout">
        <aside className="panel">
          <div className="panel-head">
            <h2>{t("Выберите результаты", "Select results")}</h2>
            <span>{ids.length} / 4</span>
          </div>
          {runs.loading ? (
            <Spinner />
          ) : runs.error ? (
            <ErrorPanel message={runs.error} />
          ) : !runs.data?.length ? (
            <Empty
              icon={GitCompareArrows}
              title={t("Сначала измерьте результат", "Measure a result first")}
              text={t(
                "Сохранённые тесты появятся здесь.",
                "Saved backtests will appear here.",
              )}
              action={t("Создать стратегию", "Create strategy")}
              to="/new"
            />
          ) : (
            runs.data.map((r) => (
              <label key={r.id} className="comparison-choice">
                <input
                  type="checkbox"
                  checked={ids.includes(r.id)}
                  disabled={!ids.includes(r.id) && ids.length >= 4}
                  onChange={(e) =>
                    setIds(
                      e.target.checked
                        ? [...ids, r.id]
                        : ids.filter((v) => v !== r.id),
                    )
                  }
                />
                <div>
                  <b>{r.strategy_name || r.id.slice(0, 12)}</b>
                  <small>
                    {r.dataset?.symbol} · {r.dataset?.timeframe} ·{" "}
                    {date(r.created_at)}
                  </small>
                  <code>{r.id.slice(0, 12)}</code>
                </div>
              </label>
            ))
          )}
        </aside>
        <div>
          {details.loading && ids.length > 0 ? (
            <Spinner />
          ) : details.error ? (
            <ErrorPanel message={details.error} />
          ) : !selected.length ? (
            <section className="panel comparison-empty">
              <GitCompareArrows size={43} strokeWidth={1} />
              <h2>
                {t(
                  "Сопоставляйте идеи, а не обещания",
                  "Compare ideas, not promises",
                )}
              </h2>
              <p>
                {t(
                  "Выберите результаты слева. Ни один вариант не будет автоматически объявлен победителем.",
                  "Select results on the left. No variant will be automatically promoted as a winner.",
                )}
              </p>
            </section>
          ) : (
            <>
              <Notice>
                {comparable
                  ? t(
                      "Источники, даты, капитал, затраты и режимы совпадают. Сравнение остаётся ретроспективным; подбор по уже просмотренным результатам не создаёт независимого подтверждения.",
                      "Sources, dates, capital, costs and execution modes match. This remains retrospective; selecting from inspected results does not create independent confirmation.",
                    )
                  : t(
                      "Условия результатов различаются или выбран только один тест. Таблица описательная: разницу нельзя приписывать только правилам стратегии.",
                      "Conditions differ, or only one run is selected. This table is descriptive: differences cannot be attributed solely to strategy rules.",
                    )}
              </Notice>
              <section className="panel">
                <div className="panel-head">
                  <h2>
                    {t(
                      "Реальные сохранённые траектории",
                      "Actual saved equity paths",
                    )}
                  </h2>
                  <Badge tone={comparable ? "mint" : "amber"}>
                    {comparable
                      ? t("Сопоставимые условия", "Matched conditions")
                      : t(
                          "Описательное сопоставление",
                          "Descriptive comparison",
                        )}
                  </Badge>
                </div>
                <Chart
                  option={{
                    ...base,
                    legend: { top: 0, textStyle: base.textStyle },
                    dataZoom: [{ type: "inside" }],
                    series,
                  }}
                  height={380}
                />
              </section>
              <section className="panel comparison-table">
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("Показатель", "Measure")}</th>
                        {selected.map((r) => (
                          <th key={r.id}>
                            <Link to={`/backtests/${r.id}`}>
                              {r.strategy_name || r.id.slice(0, 8)}
                            </Link>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        [
                          "net_return_pct",
                          t("Чистая доходность, %", "Net return, %"),
                        ],
                        [
                          "max_drawdown_pct",
                          t("Макс. просадка, %", "Max drawdown, %"),
                        ],
                        ["sharpe", "Sharpe"],
                        [
                          "total_trades",
                          t("Завершённые сделки", "Closed trades"),
                        ],
                        ["exposure_pct", t("В рынке, %", "Exposure, %")],
                        ["total_costs", t("Издержки, USDT", "Costs, USDT")],
                      ].map(([key, label]) => (
                        <tr key={key}>
                          <td>{label}</td>
                          {selected.map((r) => (
                            <td className="mono" key={r.id}>
                              {format(key === "total_costs" ? measuredCosts(r.metrics) : r.metrics[key])}
                            </td>
                          ))}
                        </tr>
                      ))}
                      <tr>
                        <td>{t("Данные", "Data")}</td>
                        {selected.map((r) => (
                          <td key={r.id}>
                            {r.dataset?.symbol} / {r.dataset?.timeframe}
                            <small>{r.dataset?.source_type}</small>
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td>{t("Даты", "Dates")}</td>
                        {selected.map((r) => (
                          <td key={r.id}>
                            {String(r.config.start)} → {String(r.config.end)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td>
                          {t(
                            "Комиссия / проскальзывание, bp",
                            "Fee / slippage, bp",
                          )}
                        </td>
                        {selected.map((r) => (
                          <td key={r.id}>
                            {String(r.config.fee_bps)} /{" "}
                            {String(r.config.slippage_bps)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td>{t("Источник / версия", "Source / version")}</td>
                        {selected.map((r) => (
                          <td key={r.id}>
                            <code>{r.dataset?.sha256.slice(0, 12)}</code>
                            <small>
                              {String(r.provenance?.engine_version || "legacy")}
                            </small>
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </>
  );
}
