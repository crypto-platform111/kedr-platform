import { useEffect, useState } from "react";
import { Download, FlaskConical, Play, RefreshCw } from "lucide-react";
import { api, measuredCosts, post, type Run } from "./api";
import { Badge, ErrorPanel, Notice, Spinner } from "./components";
import { useApp } from "./context";

type Kind = "costs" | "partitions" | "walk_forward";
type Uncertainty = {
  status: string;
  weeks: number;
  minimum_weeks?: number;
  draws?: number;
  mean?: number;
  ordinary_95_interval?: [number, number];
  statistic?: string;
};
type Arm = {
  name: string;
  config: Record<string, unknown>;
  metrics: Run["metrics"];
  quality: Run["quality"];
  uncertainty: Uncertainty;
  provenance: Record<string, unknown>;
};
type ScenarioJob = {
  id: string;
  status: string;
  error?: string;
  config: Record<string, unknown>;
  result?: {
    scenario_kind: Kind;
    arms: Arm[];
    selection_performed: boolean;
    model_refitting: boolean;
    independent_validation: boolean;
    limitations: string[];
  };
};

/** Three fixed replays of the exact saved version; no optimizer or winner selection. */
export default function FixedScenarios({ run }: { run: Run }) {
  const { t, format, date } = useApp();
  const [kind, setKind] = useState<Kind>("costs"),
    [job, setJob] = useState<ScenarioJob | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [pollExpired, setPollExpired] = useState(false);
  const active = ["queued", "running"].includes(job?.status || "");
  useEffect(() => {
    if (!job?.id || !active) return;
    let current = true,
      attempt = 0;
    const id = job.id;
    const timer = setInterval(() => {
      attempt += 1;
      if (attempt > 60) {
        clearInterval(timer);
        if (current) setPollExpired(true);
        return;
      }
      api<ScenarioJob>(`/research/jobs/${id}`)
        .then((value) => {
          if (current) {
            setJob(value);
            setError("");
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    }, 2000);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [job?.id, active]);
  const labels: Record<string, string> = {
    half_cost: t("Половина затрат", "Half costs"),
    base_cost: t("Базовые затраты", "Base costs"),
    double_cost: t("Двойные затраты", "Double costs"),
    development: t("Ранняя треть", "Earlier third"),
    validation: t("Средняя треть", "Middle third"),
    test: t("Поздняя треть", "Later third"),
    forward_1: t("Последовательный период 1", "Sequential period 1"),
    forward_2: t("Последовательный период 2", "Sequential period 2"),
    forward_3: t("Последовательный период 3", "Sequential period 3"),
  };
  const submit = async () => {
    setBusy(true);
    setError("");
    setPollExpired(false);
    try {
      setJob(
        await post<ScenarioJob>("/research/scenarios", {
          strategy_id: run.strategy_id,
          version_id: run.version_id,
          dataset_id: run.dataset.id,
          config: run.config,
          scenario_kind: kind,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const refresh = async () => {
    if (!job) return;
    try {
      setJob(await api<ScenarioJob>(`/research/jobs/${job.id}`));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const download = () => {
    if (!job) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(job, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `kedr-fixed-scenarios-${job.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <div className="fixed-scenarios" data-testid="fixed-scenarios">
      <section className="panel">
        <div className="panel-head">
          <h2>
            <FlaskConical size={17} />
            {t("Три заранее заданных проверки", "Three predefined checks")}
          </h2>
          <Badge tone="ice">FIXED / DESCRIPTIVE</Badge>
        </div>
        <div className="padded">
          <p>
            {t(
              "Проверяется точная сохранённая версия стратегии на тех же данных. Параметры, сигналы и часы исполнения не подбираются по результатам.",
              "Replays the exact saved strategy version on the same data. Parameters, signals and execution clocks are never selected from results.",
            )}
          </p>
          <div className="scenario-controls">
            <label>
              {t("Проверка устойчивости", "Sensitivity check")}
              <select
                data-testid="scenario-kind"
                value={kind}
                disabled={active || busy}
                onChange={(e) => setKind(e.target.value as Kind)}
              >
                <option value="costs">
                  {t("Затраты: ×0,5 / ×1 / ×2", "Costs: ×0.5 / ×1 / ×2")}
                </option>
                <option value="partitions">
                  {t(
                    "Три хронологические части",
                    "Three chronological partitions",
                  )}
                </option>
                <option value="walk_forward">
                  {t(
                    "Последовательный повтор фиксированной политики",
                    "Sequential fixed-policy replay",
                  )}
                </option>
              </select>
            </label>
            <button
              data-testid="run-scenarios"
              className="btn primary"
              disabled={busy || active}
              onClick={() => void submit()}
            >
              <Play size={14} />
              {t("Измерить три варианта", "Measure three arms")}
            </button>
            {job && (
              <button className="btn secondary" onClick={() => void download()}>
                <Download size={14} />
                {t("Экспорт результата", "Export result")}
              </button>
            )}
          </div>
          <Notice>
            {kind === "costs"
              ? t(
                  "Комиссия и проскальзывание умножаются вместе, каждый параметр ограничен 100 bp. Эти допущения не подтверждают исполнимые котировки.",
                  "Fee and slippage are multiplied together; each is capped at 100 bp. These assumptions do not verify executable quotes.",
                )
              : t(
                  "Календарь делится на три фиксированные части с разделением в восемь свечей. Каждый счёт начинается заново с денег; ранние свечи только прогревают индикаторы. Здесь нет переобучения или нетронутого test.",
                  "The calendar is divided into three fixed parts with eight bars of separation. Each account restarts in cash; earlier candles only warm indicators. There is no refitting or untouched test.",
                )}
          </Notice>
        </div>
      </section>
      {error && <ErrorPanel message={error} retry={() => void refresh()} />}
      {job?.error && <ErrorPanel message={job.error} />}
      {job && (
        <div className="scenario-job-status">
          <Badge
            tone={
              job.status === "succeeded"
                ? "mint"
                : job.status === "failed"
                  ? "amber"
                  : ""
            }
          >
            {job.status}
          </Badge>
          <code>{job.id}</code>
          {pollExpired && (
            <button className="text-button" onClick={() => void refresh()}>
              <RefreshCw size={13} />
              {t("Обновить сохранённое состояние", "Refresh saved state")}
            </button>
          )}
        </div>
      )}
      {active && !pollExpired && (
        <Spinner
          label={t(
            "Выполняются три ограниченных прогона…",
            "Running three bounded replays…",
          )}
        />
      )}
      {pollExpired && active && (
        <Notice>
          {t(
            "Автообновление остановлено через две минуты. Задача остаётся на сервере; состояние можно проверить кнопкой выше.",
            "Automatic refresh stopped after two minutes. The server retains the job; check its saved state above.",
          )}
        </Notice>
      )}
      {job?.result && (
        <>
          <section className="panel scenario-table">
            <div className="table-scroll">
              <table data-testid="scenario-results">
                <thead>
                  <tr>
                    <th>{t("Показатель", "Measure")}</th>
                    {job.result.arms.map((arm) => (
                      <th key={arm.name}>{labels[arm.name] || arm.name}</th>
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
                    ["total_trades", t("Завершённые сделки", "Closed trades")],
                    ["exposure_pct", t("В рынке, %", "Exposure, %")],
                    ["total_costs", t("Издержки, USDT", "Costs, USDT")],
                  ].map(([key, label]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      {job.result!.arms.map((arm) => (
                        <td className="mono" key={arm.name}>
                          {format(key === "total_costs" ? measuredCosts(arm.metrics) : arm.metrics[key])}
                        </td>
                      ))}
                    </tr>
                  ))}
                  <tr>
                    <td>{t("Даты", "Dates")}</td>
                    {job.result.arms.map((arm) => (
                      <td key={arm.name}>
                        {date(String(arm.config.start))}
                        <br />
                        {date(String(arm.config.end))}
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
                    {job.result.arms.map((arm) => (
                      <td key={arm.name}>
                        {String(arm.config.fee_bps)} /{" "}
                        {String(arm.config.slippage_bps)}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel">
            <div className="panel-head">
              <h2>
                {t("Описательная неопределённость", "Descriptive uncertainty")}
              </h2>
              <Badge>WEEK CLUSTERS</Badge>
            </div>
            <div className="padded">
              <p>
                {t(
                  "Средняя разница односвечной нетто-доходности стратегии и пассивного ориентира на одинаковых свечах, в процентных пунктах. Недельные блоки повторно выбираются синхронно; это не доверительный интервал CAGR или прибыли.",
                  "Mean one-bar net strategy return minus passive return on identical bars, in percentage points. Calendar-week clusters are resampled together; this is not a CAGR or profit interval.",
                )}
              </p>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>{t("Вариант", "Arm")}</th>
                      <th>{t("Недель", "Weeks")}</th>
                      <th>{t("Средняя разница, pp", "Mean difference, pp")}</th>
                      <th>
                        {t(
                          "Обычный 95% интервал, pp",
                          "Ordinary 95% interval, pp",
                        )}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.result.arms.map((arm) => (
                      <tr key={arm.name}>
                        <td>{labels[arm.name] || arm.name}</td>
                        <td>{arm.uncertainty.weeks}</td>
                        <td>
                          {arm.uncertainty.mean == null
                            ? "—"
                            : format(100 * arm.uncertainty.mean, 5)}
                        </td>
                        <td>
                          {arm.uncertainty.ordinary_95_interval
                            ? arm.uncertainty.ordinary_95_interval
                                .map((value) => format(100 * value, 5))
                                .join(" / ")
                            : t(
                                "Не оценён: менее 20 недель",
                                "Not estimated: fewer than 20 weeks",
                              )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Notice>
                {t(
                  "1 000 повторов, seed 42. Интервалы не скорректированы за множественные сравнения; соседние недели и рыночные режимы могут оставаться зависимыми. Результаты не выбирают победителя и не являются независимой проверкой.",
                  "1,000 draws, seed 42. Intervals are unadjusted for multiple comparisons; adjacent weeks and market regimes may remain dependent. Results select no winner and are not independent validation.",
                )}
              </Notice>
              <details>
                <summary>
                  {t(
                    "Точный сохранённый результат и ограничения",
                    "Exact saved result and limitations",
                  )}
                </summary>
                <pre className="json-block">
                  {JSON.stringify(job.result, null, 2)}
                </pre>
              </details>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
