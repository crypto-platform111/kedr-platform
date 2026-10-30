import { datasetIsAvailable, preferredDataset } from "./datasetSelection";
import { useEffect, useState } from "react";
import {
  ArrowRight,
  Database,
  FileCheck2,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldCheck,
  Square,
} from "lucide-react";
import { api, post, type Dataset } from "./api";
import {
  Badge,
  ErrorPanel,
  Metric,
  Notice,
  PageHead,
  SourceBadge,
  Spinner,
  useLoad,
} from "./components";
import { useApp } from "./context";

type Experiment = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  error?: string;
  config: Record<string, any>;
  result?: {
    metrics: Record<string, Record<string, number | null>>;
    baseline_metrics: Record<string, Record<string, number | null>>;
    calibration: Record<string, any>[];
    splits: Record<string, any>;
    features: string[];
    feature_contributions: { feature: string; coefficient: number }[];
    limitations: string[];
    artifact: Record<string, any>;
    summary: {
      test_score: number;
      baseline_score: number;
      score_name: string;
      improvement: number;
    };
  };
};
export default function MLResearch() {
  const { t, format, date, notify } = useApp();
  const datasets = useLoad(() => api<Dataset[]>("/datasets")),
    list = useLoad(() => api<Experiment[]>("/ml/experiments"));
  const [selected, setSelected] = useState(""),
    [experiment, setExperiment] = useState<Experiment | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [draftConfig, setConfig] = useState({
      name: "BTC · direction · logistic",
      dataset_id: "",
      target: "direction",
      model_family: "logistic",
      horizon_bars: 6,
      feature_groups: ["momentum", "volatility", "calendar"],
      start: "",
      end: "",
    });
  const initialDataset = preferredDataset(datasets.data || []);
  // Derive the initial choice from installed sources; never replace an explicit choice.
  const config = draftConfig.dataset_id ? draftConfig : {
    ...draftConfig,
    dataset_id: initialDataset?.id || "",
    start: initialDataset?.start.slice(0, 10) || "",
    end: initialDataset?.end.slice(0, 10) || "",
  };
  const [tab, setTab] = useState("metrics");
  const selectedDataset = datasets.data?.find((d) => d.id === config.dataset_id);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    const update = async () => {
      try {
        const e = await api<Experiment>(`/ml/experiments/${selected}`);
        if (active) {
          setExperiment(e);
          if (!["queued", "running"].includes(e.status)) clearInterval(timer);
        }
      } catch (e: any) {
        if (active) setError(e.message);
      }
    };
    const timer = setInterval(() => void update(), 1500);
    void update();
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selected]);
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const e = await post<Experiment>("/ml/train", config);
      setSelected(e.id);
      setExperiment(e);
      list.reload();
      notify(
        t(
          "Ограниченное обучение поставлено в отдельный процесс",
          "Bounded training queued in a separate process",
        ),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const cancel = async () => {
    if (!experiment) return;
    try {
      await post(`/ml/experiments/${experiment.id}/cancel`);
      setExperiment(await api(`/ml/experiments/${experiment.id}`));
      list.reload();
    } catch (e: any) {
      notify(e.message, true);
    }
  };
  const result = experiment?.result,
    test = result?.metrics?.test;
  const active = ["queued", "running"].includes(experiment?.status || "");
  return (
    <>
      <PageHead
        eyebrow="ML / BOUNDED RESEARCH"
        title={t(
          "От гипотезы — к измерению",
          "From a hypothesis to a measurement",
        )}
        description={t(
          "Настоящее небольшое обучение на разрешённой истории. Причинные признаки, хронологические разделы и простые контрольные прогнозы.",
          "Real small-scale training on authorized history. Causal features, chronological splits and simple baseline forecasts.",
        )}
        actions={
          <Badge tone="ice">
            <FlaskConical size={13} />
            {t("Ретроспективное исследование", "Retrospective research")}
          </Badge>
        }
      />
      <div className="ml-research-layout">
        <aside>
          <section className="panel">
            <div className="panel-head">
              <h2>{t("Новый эксперимент", "New experiment")}</h2>
              <Database size={17} />
            </div>
            <div className="padded">
              <label>
                {t("Название", "Name")}
                <input
                  aria-label={t(
                    "Название ML-эксперимента",
                    "ML experiment name",
                  )}
                  value={config.name}
                  maxLength={120}
                  onChange={(e) =>
                    setConfig({ ...config, name: e.target.value })
                  }
                />
              </label>
              <label>
                {t("Набор данных", "Dataset")}
                <select
                  data-testid="ml-dataset"
                  value={config.dataset_id}
                  onChange={(e) => {
                    const d = datasets.data?.find(
                      (v) => v.id === e.target.value,
                    );
                    setConfig({
                      ...config,
                      dataset_id: e.target.value,
                      start: d?.start.slice(0, 10) || config.start,
                      end: d?.end.slice(0, 10) || config.end,
                    });
                  }}
                >
                  {datasets.data?.map((d) => (
                    <option key={d.id} value={d.id} disabled={!datasetIsAvailable(d)} title={d.error}>
                      {d.name}{!datasetIsAvailable(d) ? t(" — недоступен", " — unavailable") : d.source_type === "synthetic_demo" ? " — DEMO" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <SourceBadge
                type={
                  datasets.data?.find((d) => d.id === config.dataset_id)
                    ?.source_type
                }
              />
              {selectedDataset?.source_type === "synthetic_demo" && (
                <Notice>{t(
                  "Синтетические данные: только проверка обучения и интерфейса. Метрики не описывают рынок и не доказывают предсказательную способность.",
                  "Synthetic data: training and interface demonstration only. These metrics do not describe the market or establish predictive ability.",
                )}</Notice>
              )}
              {datasets.data?.some((d) => !datasetIsAvailable(d)) && (
                <p className="fine-print" data-testid="ml-unavailable-data">{t("Архивы не установлены и не используются автоматически.", "Uninstalled archives are unavailable and are never used automatically.")}</p>
              )}
              <div className="form-row">
                <label>
                  {t("Цель", "Target")}
                  <select
                    value={config.target}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        target: e.target.value,
                        model_family:
                          e.target.value === "direction" ? "logistic" : "ridge",
                      })
                    }
                  >
                    <option value="direction">P(return &gt; 0)</option>
                    <option value="return">
                      {t("Терминальный log return", "Terminal log return")}
                    </option>
                  </select>
                </label>
                <label>
                  {t("Модель", "Model")}
                  <select
                    data-testid="ml-model"
                    value={config.model_family}
                    onChange={(e) =>
                      setConfig({ ...config, model_family: e.target.value })
                    }
                  >
                    <option
                      value={
                        config.target === "direction" ? "logistic" : "ridge"
                      }
                    >
                      {config.target === "direction"
                        ? "Logistic regression"
                        : "Ridge regression"}
                    </option>
                  </select>
                </label>
              </div>
              <label>
                {t("Горизонт, свечей", "Horizon, bars")}
                <input
                  data-testid="ml-horizon"
                  type="number"
                  min={1}
                  max={42}
                  value={config.horizon_bars}
                  onChange={(e) =>
                    setConfig({ ...config, horizon_bars: +e.target.value })
                  }
                />
              </label>
              <div className="form-row">
                <label>
                  {t("Начало", "Start")}
                  <input
                    type="date"
                    min="2022-01-01"
                    max={config.end}
                    value={config.start}
                    onChange={(e) =>
                      setConfig({ ...config, start: e.target.value })
                    }
                  />
                </label>
                <label>
                  {t("Конец", "End")}
                  <input
                    type="date"
                    min={config.start}
                    max="2025-12-31"
                    value={config.end}
                    onChange={(e) =>
                      setConfig({ ...config, end: e.target.value })
                    }
                  />
                </label>
              </div>
              <div className="feature-group-options">
                <span className="eyebrow">
                  {t("ПРИЧИННЫЕ ПРИЗНАКИ", "CAUSAL FEATURES")}
                </span>
                {[
                  [
                    "momentum",
                    t(
                      "Прошлая доходность и импульс",
                      "Past returns and momentum",
                    ),
                  ],
                  ["volatility", t("Прошлая изменчивость", "Past volatility")],
                  [
                    "calendar",
                    t("Известный UTC-календарь", "Known UTC calendar"),
                  ],
                ].map(([id, label]) => (
                  <label className="checkbox-label" key={id}>
                    <input
                      type="checkbox"
                      checked={config.feature_groups.includes(id)}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          feature_groups: e.target.checked
                            ? [...config.feature_groups, id]
                            : config.feature_groups.filter((g) => g !== id),
                        })
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
              <p className="fine-print">
                {t(
                  "Параметры и разделы фиксированы сервером. Поиск гиперпараметров и произвольный Python не допускаются.",
                  "Parameters and splits are fixed server-side. Hyperparameter search and arbitrary Python are unavailable.",
                )}
              </p>
              {error && (
                <div className="inline-error" role="alert">
                  {error}
                </div>
              )}
              <button
                data-testid="ml-train"
                className="btn primary full"
                onClick={() => void submit()}
                disabled={busy || active || !config.feature_groups.length || !selectedDataset || !datasetIsAvailable(selectedDataset)}
              >
                <Play size={15} />
                {busy
                  ? t("Отправка…", "Submitting…")
                  : t("Обучить и оценить", "Train and evaluate")}
              </button>
            </div>
          </section>
          <section className="panel experiment-list">
            <div className="panel-head">
              <h3>{t("Реестр экспериментов", "Experiment registry")}</h3>
              <button
                className="icon-btn"
                onClick={list.reload}
                aria-label={t("Обновить реестр", "Refresh registry")}
              >
                <RefreshCw size={15} />
              </button>
            </div>
            {list.loading ? (
              <Spinner />
            ) : list.error ? (
              <ErrorPanel message={list.error} />
            ) : !list.data?.length ? (
              <p className="padded muted">
                {t("Реальных запусков пока нет.", "No actual runs yet.")}
              </p>
            ) : (
              list.data.map((e) => (
                <button
                  className={`experiment-row ${selected === e.id ? "selected" : ""}`}
                  key={e.id}
                  onClick={() => {
                    setSelected(e.id);
                    setTab("metrics");
                  }}
                >
                  <div>
                    <b>{e.name}</b>
                    <small>{date(e.created_at, true)}</small>
                  </div>
                  <Badge tone={e.status === "succeeded" ? "mint" : ""}>
                    {e.status}
                  </Badge>
                </button>
              ))
            )}
          </section>
        </aside>
        <div>
          {!experiment ? (
            <section className="panel ml-start">
              <div className="ml-research-emblem">
                <FlaskConical size={48} strokeWidth={1} />
              </div>
              <span className="eyebrow">
                CAUSAL · CHRONOLOGICAL · REPRODUCIBLE
              </span>
              <h2>
                {t("Сначала контрольный прогноз", "Start with a baseline")}
              </h2>
              <p>
                {t(
                  "Модель должна сравниваться с более простым прогнозом на тех же исходах. Обучение, validation и test разделяются по времени. Данные после целевого исхода не входят в признаки.",
                  "A model must be compared with a simpler forecast on the same outcomes. Training, validation and test are separated chronologically. Information after the target outcome never enters features.",
                )}
              </p>
              <div className="ml-workflow-steps">
                {[
                  t("Причинный набор", "Causal dataset"),
                  t("Раннее обучение", "Earlier training"),
                  t("Отложенная оценка", "Held-out evaluation"),
                  t("Версионный артефакт", "Versioned artifact"),
                ].map((text, i) => (
                  <div key={text}>
                    <span>0{i + 1}</span>
                    {text}
                    {i < 3 && <ArrowRight size={14} />}
                  </div>
                ))}
              </div>
              <Notice>
                {t(
                  "Это ещё один анализ уже доступной истории. Даже хороший test не является независимым подтверждением будущей эффективности.",
                  "This analyzes already available history. Even a favorable test is not independent confirmation of future performance.",
                )}
              </Notice>
            </section>
          ) : (
            <>
              <section className="panel ml-job-head">
                <div>
                  <span className="eyebrow">
                    EXPERIMENT / {experiment.id.slice(0, 12)}
                  </span>
                  <h2>{experiment.name || config.name}</h2>
                  <p>{date(experiment.created_at, true)}</p>
                </div>
                <Badge
                  tone={
                    experiment.status === "succeeded"
                      ? "mint"
                      : experiment.status === "failed"
                        ? "amber"
                        : ""
                  }
                >
                  {experiment.status}
                </Badge>
                {active && (
                  <button
                    className="btn secondary"
                    data-testid="cancel-ml"
                    onClick={() => void cancel()}
                  >
                    <Square size={13} />
                    {t("Отменить процесс", "Cancel worker")}
                  </button>
                )}
              </section>
              {active && (
                <section className="panel">
                  <Spinner
                    label={t(
                      "Изолированный Python-процесс строит признаки и оценивает модель…",
                      "An isolated Python process is building features and evaluating the model…",
                    )}
                  />
                  <p className="padded muted">
                    {t(
                      "Без сетевых запросов, пользовательского кода и автоматического прикрепления модели к стратегии.",
                      "No network calls, user code or automatic strategy attachment.",
                    )}
                  </p>
                </section>
              )}
              {experiment.error && <ErrorPanel message={experiment.error} />}{" "}
              {result && (
                <>
                  <div className="ml-score-grid">
                    <Metric
                      label={
                        result.summary?.score_name ||
                        t("Основная ошибка", "Primary score")
                      }
                      value={format(result.summary?.test_score, 5)}
                      sub={t("Модель · test", "Model · test")}
                    />
                    <Metric
                      label={t("Простой контроль", "Simple baseline")}
                      value={format(result.summary?.baseline_score, 5)}
                      sub={t("Те же исходы test", "Identical test outcomes")}
                    />
                    <Metric
                      label={t("Разница ошибок", "Score difference")}
                      value={format(
                        (result.summary?.test_score || 0) -
                          (result.summary?.baseline_score || 0),
                        5,
                      )}
                      sub={t("Отрицательная лучше", "Negative favors model")}
                    />
                  </div>
                  <div className="page-tabs">
                    {[
                      [
                        "metrics",
                        t("Измеренные результаты", "Measured results"),
                      ],
                      [
                        "splits",
                        t("Разделы и причинность", "Splits and causality"),
                      ],
                      [
                        "artifact",
                        t("Артефакт и признаки", "Artifact and features"),
                      ],
                    ].map(([key, label]) => (
                      <button
                        key={key}
                        className={tab === key ? "active" : ""}
                        onClick={() => setTab(key)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  {tab === "metrics" && (
                    <section className="panel">
                      <div className="panel-head">
                        <h2>
                          {t(
                            "Сопоставление с контролем",
                            "Baseline comparison",
                          )}
                        </h2>
                        <Badge>HISTORICAL / NOT VALIDATED</Badge>
                      </div>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>{t("Метрика", "Metric")}</th>
                              {["train", "validation", "test"].map((split) => (
                                <th key={split}>{split} · model / baseline</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {Object.keys(test || {}).map((key) => (
                              <tr key={key}>
                                <td>{key}</td>
                                {["train", "validation", "test"].map(
                                  (split) => (
                                    <td className="mono" key={split}>
                                      {format(
                                        result.metrics?.[split]?.[key],
                                        5,
                                      )}{" "}
                                      /{" "}
                                      {format(
                                        result.baseline_metrics?.[split]?.[key],
                                        5,
                                      )}
                                    </td>
                                  ),
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {result.calibration?.length > 0 && (
                        <>
                          <div className="panel-head">
                            <h3>
                              {t(
                                "Калибровка test: фиксированные бины",
                                "Test calibration: fixed bins",
                              )}
                            </h3>
                          </div>
                          <div className="table-scroll">
                            <table>
                              <thead>
                                <tr>
                                  {Object.keys(result.calibration[0]).map(
                                    (key) => (
                                      <th key={key}>{key}</th>
                                    ),
                                  )}
                                </tr>
                              </thead>
                              <tbody>
                                {result.calibration.map((bin, i) => (
                                  <tr key={i}>
                                    {Object.values(bin).map((value, j) => (
                                      <td key={j}>
                                        {typeof value === "number"
                                          ? format(value, 4)
                                          : String(value ?? "—")}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </>
                      )}
                      {result.limitations?.map((lim, i) => (
                        <Notice key={i}>{lim}</Notice>
                      ))}
                    </section>
                  )}
                  {tab === "splits" && (
                    <section className="panel">
                      <div className="panel-head">
                        <h2>
                          {t(
                            "Точный манифест разделов",
                            "Exact split manifest",
                          )}
                        </h2>
                        <ShieldCheck size={17} />
                      </div>
                      <Notice>
                        {t(
                          "Преобразования обучаются только на train. Между разделами удаляются исходы, пересекающие границы. Разделы нельзя менять по результатам test.",
                          "Preprocessing fits training data only. Outcomes crossing boundaries are purged. Do not change splits after observing test results.",
                        )}
                      </Notice>
                      <pre className="json-block">
                        {JSON.stringify(result.splits, null, 2)}
                      </pre>
                    </section>
                  )}
                  {tab === "artifact" && (
                    <section className="panel">
                      <div className="panel-head">
                        <h2>
                          {t(
                            "Воспроизводимый артефакт",
                            "Reproducible artifact",
                          )}
                        </h2>
                        <FileCheck2 size={17} />
                      </div>
                      <Notice>
                        {t(
                          "Коэффициенты — обучающие ассоциации, а не причинные эффекты. Этот артефакт не подключает ML-узел автоматически: нужна проверенная временная совместимость.",
                          "Coefficients are training associations, not causal effects. This artifact does not automatically activate an ML node; temporal compatibility must be verified.",
                        )}
                      </Notice>
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>{t("Признак", "Feature")}</th>
                              <th>
                                {t(
                                  "Стандартизированный коэффициент",
                                  "Standardized coefficient",
                                )}
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {result.feature_contributions?.map((c) => (
                              <tr key={c.feature}>
                                <td>{c.feature}</td>
                                <td className="mono">
                                  {format(c.coefficient, 6)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <details className="padded" open>
                        <summary>
                          {t(
                            "Безопасные числовые параметры и происхождение",
                            "Safe numeric parameters and provenance",
                          )}
                        </summary>
                        <pre className="json-block">
                          {JSON.stringify(result.artifact, null, 2)}
                        </pre>
                      </details>
                    </section>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
