import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  Bot,
  Check,
  ChevronRight,
  Clock3,
  Cpu,
  Database,
  ExternalLink,
  Eye,
  FileCheck2,
  FlaskConical,
  GitFork,
  GitBranch,
  Globe2,
  Layers3,
  LockKeyhole,
  Network,
  Newspaper,
  Plus,
  Radio,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Terminal,
  Users,
  X,
} from "lucide-react";
import { api, post, type Dataset, type Run } from "./api";
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

export function Analyst() {
  const { id } = useParams();
  const { t, locale, format, date } = useApp();
  const navigate = useNavigate();
  const runs = useLoad(() => api<Run[]>("/backtests"));
  const selected = id || "";

  const analysis = useLoad(async () => {
    if (!selected) return null;
    return Promise.all([
      api(`/backtests/${selected}/analysis?locale=${locale}`),
      api<Run>(`/backtests/${selected}`),
    ]);
  }, [selected, locale]);
  const report = analysis.data?.[0],
    run = analysis.data?.[1];
  return (
    <>
      <PageHead
        eyebrow={t("ОТ МЕТРИК — К ПОНИМАНИЮ", "FROM METRICS TO UNDERSTANDING")}
        title={t("Исследователь стратегии", "Strategy research analyst")}
        description={t(
          "Прозрачный разбор измеренных результатов и ограничений.",
          "A transparent review of measured results and limitations.",
        )}
        actions={
          <Badge tone="mint">
            <span className="status-dot small" />
            {t("Офлайн-правила активны", "Offline rules active")}
          </Badge>
        }
      />
      <div className="analyst-layout">
        <aside className="panel analyst-selection">
          <div className="panel-head">
            <h2>{t("Контекст исследования", "Research context")}</h2>
            <Layers3 size={17} />
          </div>
          <div className="padded">
            <label>
              {t("Сохранённый тест", "Saved backtest")}
              <select
                value={selected}
                onChange={(e) => {
                  navigate(
                    e.target.value ? `/analyst/${e.target.value}` : "/analyst",
                  );
                }}
              >
                <option value="">
                  {t("Выберите результат", "Select a result")}
                </option>
                {runs.data?.map((r) => (
                  <option value={r.id} key={r.id}>
                    {r.strategy_name || r.dataset?.symbol || r.id.slice(0, 12)}{" "}
                    · {date(r.created_at)}
                  </option>
                ))}
              </select>
            </label>
            {run && (
              <>
                <SourceBadge type={run.dataset?.source_type} />
                <div className="analysis-reference">
                  <span>{t("Чистая доходность", "Net return")}</span>
                  <b>{format(run.metrics.net_return_pct)}%</b>
                  <span>{t("Максимальная просадка", "Maximum drawdown")}</span>
                  <b>{format(run.metrics.max_drawdown_pct)}%</b>
                  <span>{t("Завершённых сделок", "Closed trades")}</span>
                  <b>{format(run.metrics.total_trades, 0)}</b>
                </div>
                <Link to={`/backtests/${selected}`} className="text-button">
                  {t("Открыть исходный результат", "Open source result")}
                  <ArrowUpRight size={14} />
                </Link>
              </>
            )}
            <div className="analyst-provider">
              <Sparkles size={18} />
              <b>
                {t(
                  "Генеративный AI не подключён",
                  "Generative AI is disconnected",
                )}
              </b>
              <p>
                {t(
                  "Этот разбор составлен детерминированными правилами по сохранённым метрикам. Внешние модели не используются.",
                  "This report uses deterministic rules applied to saved metrics. No external model is used.",
                )}
              </p>
              <Link to="/integrations">
                {t("Статус интеграций", "Integration status")}
                <ChevronRight size={13} />
              </Link>
            </div>
          </div>
        </aside>
        <div className="analyst-report">
          {!selected ? (
            <section className="panel analyst-welcome">
              <div className="analyst-orb">
                <Sparkles size={35} strokeWidth={1.2} />
              </div>
              <div className="eyebrow">RESEARCH / EXPLAIN</div>
              <h2>
                {t("Правильные вопросы важнее", "The right questions matter")}
              </h2>
              <p>
                {t(
                  "Выберите сохранённый результат. Мы объясним измеренные риски, сравнение с ориентиром и то, что этот тест не устанавливает.",
                  "Select a saved result. We will explain measured risks, the benchmark comparison and what the test does not establish.",
                )}
              </p>
              <div className="question-chips">
                {[
                  t("Где возникает просадка?", "Where does drawdown occur?"),
                  t(
                    "Что остаётся после издержек?",
                    "What remains after costs?",
                  ),
                  t("Достаточно ли сделок?", "Are there enough trades?"),
                ].map((s) => (
                  <span key={s}>{s}</span>
                ))}
              </div>
              {!runs.data?.length && (
                <Link to="/new" className="btn primary">
                  {t("Создать первый тест", "Create your first test")}
                  <ArrowRight size={15} />
                </Link>
              )}
            </section>
          ) : analysis.loading ? (
            <Spinner />
          ) : analysis.error ? (
            <ErrorPanel message={analysis.error} retry={analysis.reload} />
          ) : (
            report && (
              <>
                <section className="report-summary">
                  <div className="eyebrow">
                    <Sparkles size={15} />
                    {t(
                      "РЕЗЮМЕ ПО ФИКСИРОВАННЫМ ПРАВИЛАМ",
                      "FIXED-RULE SUMMARY",
                    )}
                  </div>
                  <h2>
                    {t("Что показывает этот тест", "What this test shows")}
                  </h2>
                  <p>
                    {typeof report.summary === "string"
                      ? report.summary
                      : JSON.stringify(report.summary)}
                  </p>
                  <div>
                    <Badge>
                      {t("Без генеративного AI", "No generative AI")}
                    </Badge>
                    <Badge>
                      {t("Только измеренные значения", "Measured values only")}
                    </Badge>
                  </div>
                </section>
                {report.sections?.map((section: any, i: number) => (
                  <section className="panel analysis-section" key={i}>
                    <div className="analysis-number">
                      {String(i + 1).padStart(2, "0")}
                    </div>
                    <div>
                      <h2>{section.title}</h2>
                      <p>
                        {typeof section.body === "string"
                          ? section.body
                          : JSON.stringify(section.body)}
                      </p>
                      {section.references && (
                        <code>{JSON.stringify(section.references)}</code>
                      )}
                    </div>
                  </section>
                ))}
                <Notice>
                  {t(
                    "Это объяснение сохранённой симуляции. Оно не создаёт новые измерения, не является финансовой рекомендацией и не подтверждает будущую доходность.",
                    "This explains the saved simulation. It creates no new measurements, is not financial advice and does not establish future returns.",
                  )}
                </Notice>
              </>
            )
          )}
        </div>
      </div>
    </>
  );
}

export function MLStudio() {
  const { t, date, notify } = useApp();
  const ml = useLoad(() => api("/ml"));
  const [name, setName] = useState(""),
    [target, setTarget] = useState("direction_24h"),
    [family, setFamily] = useState("logistic"),
    [features, setFeatures] = useState(["returns_7d", "historical_volatility"]),
    [busy, setBusy] = useState(false),
    [draft, setDraft] = useState<any>(null);
  const featureOptions = [
    ["returns_1d", t("Доходность 1 день", "1-day returns")],
    ["returns_7d", t("Импульс 7 дней", "7-day momentum")],
    [
      "historical_volatility",
      t("Прошлая волатильность", "Historical volatility"),
    ],
    ["volume_ratio", t("Относительный объём", "Relative volume")],
    ["calendar", t("Известный календарь", "Known calendar")],
  ];
  return (
    <>
      <PageHead
        eyebrow="RESEARCH / MACHINE LEARNING"
        title="ML Studio"
        description={t(
          "Зафиксируйте исследовательский замысел, прежде чем обучать модель.",
          "Freeze a research question before training a model.",
        )}
        actions={
          <Badge tone="amber">
            <LockKeyhole size={12} />
            {t("Обучение не подключено", "Training is disconnected")}
          </Badge>
        }
      />
      <div className="ml-intro">
        <div className="ml-intro-copy">
          <span className="eyebrow">DESIGN FIRST. TRAIN LATER.</span>
          <h2>
            {t("Модель начинается", "A model starts")}
            <br />
            <span>
              {t("с хорошего эксперимента.", "with a good experiment.")}
            </span>
          </h2>
          <p>
            {t(
              "Сохраняйте цель, признаки и схему проверки. Эта версия не запускает обучение и не показывает вымышленные прогнозы.",
              "Save the target, features and evaluation design. This version does not train models or display invented forecasts.",
            )}
          </p>
        </div>
        <div className="ml-pipeline">
          {[
            [Database, "DATA"],
            [Layers3, "FEATURES"],
            [Cpu, "MODEL"],
            [ShieldCheck, "VALIDATE"],
          ].map(([Icon, label], i) => {
            const I = Icon as typeof Cpu;
            return (
              <div key={String(label)}>
                <span>
                  <I size={20} />
                </span>
                <small>{String(label)}</small>
                {i < 3 && <ChevronRight className="pipeline-arrow" size={13} />}
              </div>
            );
          })}
        </div>
      </div>
      <div className="ml-workspace">
        <section className="panel">
          <div className="panel-head">
            <h2>{t("План эксперимента", "Experiment plan")}</h2>
            <Badge>{t("Сохраняемый черновик", "Persistent draft")}</Badge>
          </div>
          <form
            className="padded"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await post("/ml/drafts", {
                  name:
                    name || t("Исследование направления", "Direction research"),
                  config: {
                    target,
                    model_family: family,
                    features,
                    split: {
                      method: "chronological",
                      train_pct: 70,
                      validation_pct: 15,
                      test_pct: 15,
                    },
                    purge: "maximum_label_horizon",
                    baseline: [
                      "unconditional_prior",
                      "momentum_volatility_calendar",
                    ],
                    training_requested: false,
                  },
                });
                notify(
                  t(
                    "Замысел сохранён. Обучение не запускалось.",
                    "Draft saved. No training was started.",
                  ),
                );
                ml.reload();
              } catch (error: any) {
                notify(error.message, true);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              {t("Название исследования", "Research name")}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t(
                  "Например: импульс и направление",
                  "For example: momentum and direction",
                )}
                maxLength={120}
              />
            </label>
            <div className="form-row">
              <label>
                {t("Цель прогноза", "Prediction target")}
                <select
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="direction_24h">
                    {t("Направление за 24 часа", "24-hour direction")}
                  </option>
                  <option value="variance_24h">
                    {t("Дисперсия за 24 часа", "24-hour variance")}
                  </option>
                </select>
              </label>
              <label>
                {t("Семейство модели", "Model family")}
                <select
                  value={family}
                  onChange={(e) => setFamily(e.target.value)}
                >
                  <option value="logistic">
                    {t("Логистическая регрессия", "Logistic regression")}
                  </option>
                  <option value="ridge">Ridge</option>
                </select>
              </label>
            </div>
            <label>
              {t("Предварительный набор признаков", "Initial feature set")}
            </label>
            <div className="feature-checkboxes">
              {featureOptions.map(([key, label]) => (
                <label className="check-row" key={key}>
                  <input
                    type="checkbox"
                    checked={features.includes(key)}
                    onChange={(e) =>
                      setFeatures((v) =>
                        e.target.checked
                          ? [...v, key]
                          : v.filter((f) => f !== key),
                      )
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
            <label>
              {t("Хронологическое разделение", "Chronological split")}
            </label>
            <div className="split-bar">
              <span>TRAIN / 70%</span>
              <span>VALID / 15%</span>
              <span>TEST / 15%</span>
            </div>
            <div className="inspector-tip">
              {t(
                "План, а не фактическая разметка данных. Перед обучением нужны точные даты, причинные признаки, purge/embargo и оценка мощности.",
                "A plan, not an actual data split. Training requires exact dates, causal features, purge/embargo and a precision plan.",
              )}
            </div>
            <div className="modal-actions">
              <button type="submit" className="btn primary" disabled={busy}>
                <FileCheck2 size={15} />
                {busy
                  ? t("Сохраняем…", "Saving…")
                  : t("Сохранить исследовательский план", "Save research plan")}
              </button>
            </div>
          </form>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Сохранённые планы", "Saved plans")}</h2>
            <FlaskConical size={18} />
          </div>
          {ml.loading ? (
            <Spinner />
          ) : ml.error ? (
            <ErrorPanel message={ml.error} retry={ml.reload} />
          ) : ml.data?.drafts?.length ? (
            <div className="draft-list">
              {ml.data.drafts.map((d: any) => (
                <button key={d.id} onClick={() => setDraft(d)}>
                  <span>
                    <FlaskConical size={18} />
                  </span>
                  <div>
                    <b>{d.name}</b>
                    <small>{date(d.created_at)}</small>
                  </div>
                  <Badge>{t("Черновик", "Draft")}</Badge>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
          ) : (
            <Empty
              icon={FlaskConical}
              title={t(
                "История начинается с вопроса",
                "A history starts with a question",
              )}
              text={t(
                "Сохранённые конфигурации появятся здесь. Обученных моделей пока нет.",
                "Saved configurations will appear here. There are no trained models yet.",
              )}
            />
          )}
          <div className="panel-footnote">
            {t(
              "Walk-forward, сравнение моделей и подключение прогнозов к стратегии требуют отдельного backend обучения.",
              "Walk-forward evaluation, model comparisons and strategy prediction nodes need a separate training backend.",
            )}
          </div>
        </section>
      </div>
      {draft && (
        <Modal title={draft.name} onClose={() => setDraft(null)}>
          <Badge tone="amber">
            {t(
              "Только конфигурация — без обучения",
              "Configuration only — no training",
            )}
          </Badge>
          <pre className="json-block">
            {JSON.stringify(draft.config, null, 2)}
          </pre>
        </Modal>
      )}
    </>
  );
}

export function Intelligence() {
  const { t, locale, date } = useApp();
  const [symbol, setSymbol] = useState("BTCUSDT");
  const news = useLoad(
    () => api(`/news?symbol=${symbol}&locale=${locale}`),
    [symbol, locale],
  );
  return (
    <>
      <PageHead
        eyebrow="COIN INTELLIGENCE"
        title={t("Информация с контекстом", "Information with context")}
        description={t(
          "Новости, происхождение и тональность. Отдельно от прогноза цены.",
          "News, provenance and sentiment. Separate from price prediction.",
        )}
        actions={
          <div className="segmented coin-selector">
            {["BTCUSDT", "ETHUSDT", "SOLUSDT"].map((s) => (
              <button
                key={s}
                className={symbol === s ? "active" : ""}
                onClick={() => setSymbol(s)}
              >
                {s.slice(0, -4)}
              </button>
            ))}
          </div>
        }
      />
      <div className="fixture-banner">
        <Newspaper size={21} />
        <div>
          <b>
            {t(
              "Учебная лента, а не актуальные новости",
              "An educational feed, not current news",
            )}
          </b>
          <p>
            {t(
              "Статичные демонстрационные записи показывают формат источников. Живой новостной и sentiment-провайдер не подключены.",
              "Static demonstration records show the source format. Live news and sentiment providers are disconnected.",
            )}
          </p>
        </div>
        <Badge tone="amber">DEMO FIXTURE</Badge>
      </div>
      <div className="intelligence-layout">
        <div>
          {news.loading ? (
            <Spinner />
          ) : news.error ? (
            <ErrorPanel message={news.error} retry={news.reload} />
          ) : (
            news.data?.articles?.map((article: any, i: number) => (
              <article className="news-card" key={article.id}>
                <div className={`news-art art-${i}`}>
                  <Newspaper size={42} strokeWidth={0.8} />
                  <span>{symbol.slice(0, -4)} / DEMO</span>
                </div>
                <div className="news-card-content">
                  <div>
                    <Badge>{t("Учебная запись", "Educational fixture")}</Badge>
                    <span className={`sentiment ${article.sentiment}`}>
                      {article.sentiment === "positive"
                        ? t("Позитивная тональность", "Positive sentiment")
                        : article.sentiment === "negative"
                          ? t("Негативная тональность", "Negative sentiment")
                          : t("Нейтральная тональность", "Neutral sentiment")}
                    </span>
                  </div>
                  <h2>{article.title}</h2>
                  <p>{article.summary}</p>
                  <div className="news-times">
                    <span>
                      <Clock3 size={13} />
                      {t("Опубликовано", "Published")}:{" "}
                      {date(article.published_at, true)}
                    </span>
                    <span>
                      {t("Впервые увидено", "First seen")}:{" "}
                      {date(article.first_seen_at, true)}
                    </span>
                  </div>
                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-button"
                    >
                      {t("Источник", "Source")}
                      <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
        <aside>
          <section className="panel intelligence-status">
            <div className="panel-head">
              <h2>{t("Состояние сигналов", "Signal availability")}</h2>
              <Radio size={17} />
            </div>
            <div className="status-row">
              <span>{t("Новости", "News")}</span>
              <Badge tone="amber">{t("Демо", "Demo")}</Badge>
            </div>
            <div className="status-row">
              <span>{t("AI-сводка", "AI summary")}</span>
              <Badge>{t("Не подключено", "Disconnected")}</Badge>
            </div>
            <div className="status-row">
              <span>{t("Текущие котировки", "Live quotes")}</span>
              <Badge>{t("Не подключено", "Disconnected")}</Badge>
            </div>
            <div className="status-row">
              <span>{t("Модель тональности", "Sentiment model")}</span>
              <Badge>{t("Не обучена", "Not trained")}</Badge>
            </div>
            <Link to="/integrations" className="btn secondary full">
              {t("Об интеграциях", "About integrations")}
              <ArrowRight size={15} />
            </Link>
          </section>
          <div className="sentiment-note">
            <AudioLines size={25} strokeWidth={1.3} />
            <h3>
              {t(
                "Тональность ≠ направление цены",
                "Sentiment ≠ price direction",
              )}
            </h3>
            <p>
              {t(
                "Позитивная статья не означает будущий рост. Для проверки сигнала важны время первого наблюдения и отдельная независимая оценка.",
                "A positive article does not imply a future price rise. First-observed timing and separate independent evaluation are essential.",
              )}
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

export function Community() {
  const { t, format, date, notify } = useApp();
  const navigate = useNavigate();
  const request = useLoad(() => api<any[]>("/community"));
  const [search, setSearch] = useState(""),
    [symbol, setSymbol] = useState("all"),
    [detail, setDetail] = useState<any>(null),
    [busy, setBusy] = useState("");
  const publications = request.data || [];
  const filtered = publications.filter(
    (p) =>
      `${p.name} ${p.description} ${(p.tags || []).join(" ")}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (symbol === "all" || p.symbol === symbol),
  );
  const fork = async (id: string) => {
    setBusy(id);
    try {
      const strategy = await post(`/community/${id}/fork`);
      notify(t("Приватная копия создана", "Private fork created"));
      navigate(`/builder/${strategy.id}`);
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <PageHead
        eyebrow={t("ОТКРЫТАЯ ЛАБОРАТОРИЯ", "OPEN WORKSPACE")}
        title={t("Идеи, которыми делятся", "Ideas worth sharing")}
        description={t(
          "Изучайте точные правила и сохранённые тесты. Копируйте в своё приватное пространство.",
          "Explore exact rules and saved tests. Fork them into your private workspace.",
        )}
        actions={
          <Link className="btn primary" to="/dashboard">
            <Plus size={16} />
            {t("Мои исследования", "My research")}
          </Link>
        }
      />
      <div className="community-banner">
        <div>
          <span className="eyebrow">COMMUNITY / REPRODUCIBLE BY DESIGN</span>
          <h2>
            {t(
              "Не обещания. Открытая методология.",
              "No promises. Open methodology.",
            )}
          </h2>
          <p>
            {t(
              "Каждая публикация связана с реальной версией и её результатом. Воспроизводимость не означает независимую валидацию.",
              "Every publication links to an actual version and result. Reproducibility is not independent validation.",
            )}
          </p>
        </div>
        <Users size={74} strokeWidth={0.7} />
      </div>
      <div className="community-filters">
        <div className="search-input">
          <Search size={16} />
          <input
            aria-label={t("Поиск стратегий", "Search strategies")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("Название, идея или тег…", "Name, idea or tag…")}
          />
        </div>
        <select
          aria-label={t("Фильтр по активу", "Filter by asset")}
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
        >
          <option value="all">{t("Все активы", "All assets")}</option>
          <option>BTCUSDT</option>
          <option>ETHUSDT</option>
          <option>SOLUSDT</option>
        </select>
        <span>
          {filtered.length} {t("исследований", "studies")}
        </span>
      </div>
      {request.loading ? (
        <Spinner />
      ) : request.error ? (
        <ErrorPanel message={request.error} retry={request.reload} />
      ) : !filtered.length ? (
        <section className="panel">
          <Empty
            icon={Users}
            title={
              search
                ? t(
                    "По этому запросу ничего не найдено",
                    "No results for this search",
                  )
                : t(
                    "Пространство для первой публикации",
                    "Room for the first publication",
                  )
            }
            text={t(
              "Запустите тест и опубликуйте конкретную версию на странице результата. Мы не подменяем сообщество вымышленными авторами.",
              "Run a test and publish an exact version from its result page. We do not populate the community with invented authors.",
            )}
            action={t("К моим стратегиям", "My strategies")}
            to="/dashboard"
          />
        </section>
      ) : (
        <div className="community-grid">
          {filtered.map((p) => (
            <article className="publication-card" key={p.id}>
              <div className="publication-top">
                <span className="publication-asset">
                  <GitBranch size={19} />
                  {p.symbol}
                </span>
                <Badge tone="ice">
                  <FileCheck2 size={11} />
                  {t("Снимок теста", "Run snapshot")}
                </Badge>
              </div>
              <button
                className="publication-title"
                onClick={async () => {
                  try {
                    setDetail(await api(`/community/${p.id}`));
                  } catch (e: any) {
                    notify(e.message, true);
                  }
                }}
              >
                {p.name}
                <ArrowUpRight size={17} />
              </button>
              <p>
                {p.description ||
                  t(
                    "Автор не добавил описание.",
                    "The author did not add a description.",
                  )}
              </p>
              <div className="publication-tags">
                {p.tags?.map((tag: string) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
              <div className="publication-metrics">
                <div>
                  <span>{t("Нетто-доходность", "Net return")}</span>
                  <b
                    className={
                      (p.metrics?.net_return_pct || 0) < 0
                        ? "negative"
                        : "positive"
                    }
                  >
                    {format(p.metrics?.net_return_pct)}%
                  </b>
                </div>
                <div>
                  <span>{t("Просадка", "Drawdown")}</span>
                  <b>{format(p.metrics?.max_drawdown_pct)}%</b>
                </div>
                <div>
                  <span>{t("Сделки", "Trades")}</span>
                  <b>{format(p.metrics?.total_trades, 0)}</b>
                </div>
              </div>
              <div className="publication-source">
                <SourceBadge type={p.dataset?.source_type} />
                <span>{p.dataset?.timeframe || "4h"}</span>
              </div>
              <div className="publication-author">
                <span className="avatar small">
                  {String(p.author?.name || p.author || "K").slice(0, 1)}
                </span>
                <span>
                  {p.author?.name ||
                    p.author ||
                    t("Исследователь", "Researcher")}
                  <small>{date(p.created_at)}</small>
                </span>
                <button
                  className="btn secondary compact"
                  data-testid={`fork-${p.id}`}
                  disabled={!!busy}
                  onClick={() => void fork(p.id)}
                >
                  <GitFork size={14} />
                  {t("Копировать", "Fork")}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {detail && (
        <Modal title={detail.name} onClose={() => setDetail(null)} wide>
          <div className="publication-detail">
            <SourceBadge type={detail.dataset?.source_type} />
            <Badge>
              {detail.verification === "reproducible_snapshot" &&
              detail.reproduction?.status === "matched"
                ? t(
                    "Пересчёт совпал · не независимая валидация",
                    "Replay matched · not independent validation",
                  )
                : t(
                    "Сохранённый снимок · пересчёт не подтверждён",
                    "Saved snapshot · replay not established",
                  )}
            </Badge>
            <p>{detail.description}</p>
            <div className="summary-grid">
              <Metric
                label={t("Нетто-доходность", "Net return")}
                value={`${format(detail.metrics?.net_return_pct)}%`}
              />
              <Metric
                label={t("Просадка", "Drawdown")}
                value={`${format(detail.metrics?.max_drawdown_pct)}%`}
              />
              <Metric
                label={t("Сделки", "Trades")}
                value={format(detail.metrics?.total_trades, 0)}
              />
              <Metric label={t("Актив", "Asset")} value={detail.symbol} />
            </div>
            {detail.verification === "reproducible_snapshot" &&
              detail.reproduction?.status === "matched" && (
                <div className="reproduction-proof">
                  <div className="quality-check">
                    <FileCheck2 size={17} />
                    <div>
                      <b>
                        {t(
                          "Полный повторный расчёт совпал",
                          "Complete replay matched",
                        )}
                      </b>
                      <p>
                        {t("Проверено", "Checked")}:{" "}
                        {date(detail.reproduction.checked_at, true)} ·{" "}
                        {detail.reproduction.engine_version}
                      </p>
                    </div>
                  </div>
                  <pre className="json-block">
                    {JSON.stringify(detail.reproduction, null, 2)}
                  </pre>
                </div>
              )}
            <dl className="definition-list">
              <div>
                <dt>{t("Набор данных", "Dataset")}</dt>
                <dd>{detail.dataset?.name}</dd>
              </div>
              <div>
                <dt>{t("Версия", "Version")}</dt>
                <dd>{detail.version_id}</dd>
              </div>
              <div>
                <dt>run_id</dt>
                <dd>{detail.run_id}</dd>
              </div>
            </dl>
            {detail.spec && (
              <details>
                <summary>
                  {t("Показать точные правила", "Show exact rules")}
                </summary>
                <pre className="json-block">
                  {JSON.stringify(detail.spec, null, 2)}
                </pre>
              </details>
            )}
            <div className="modal-actions">
              <button
                className="btn primary"
                disabled={!!busy}
                onClick={() => void fork(detail.id)}
              >
                <GitFork size={15} />
                {t("Создать приватную копию", "Create a private fork")}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

export function Bots() {
  const { t, date } = useApp();
  const state = useLoad(() => Promise.all([api("/bots"), api("/audit")]));
  const events = Array.isArray(state.data?.[1])
    ? state.data?.[1]
    : state.data?.[1]?.events || [];
  return (
    <>
      <PageHead
        eyebrow="PAPER / MONITORING"
        title={t("Центр ботов", "Bot monitoring")}
        description={t(
          "Рабочее место наблюдения за исполнением. Пока — честный предварительный просмотр.",
          "An execution monitoring workspace. Currently an honest preview.",
        )}
        actions={
          <Badge tone="amber">
            <Eye size={12} />
            PREVIEW ONLY
          </Badge>
        }
      />
      <div className="bot-preview-layout">
        <section className="bot-empty-terminal">
          <div className="terminal-title">
            <span className="status-dot neutral" />
            <span>EXECUTION / NO WORKER CONNECTED</span>
            <LockKeyhole size={14} />
          </div>
          <div className="bot-empty-content">
            <div className="bot-mark">
              <Bot size={58} strokeWidth={1} />
            </div>
            <h2>
              {t(
                "Сначала правила. Затем исполнение.",
                "First the rules. Then execution.",
              )}
            </h2>
            <p>
              {t(
                "Сохранённая стратегия не запускает бота автоматически. Локальный paper-движок и биржевое исполнение здесь не подключены.",
                "A saved strategy does not start a bot. The local paper engine and exchange execution are not connected.",
              )}
            </p>
            <Link className="btn primary" to="/dashboard">
              <GitBranch size={15} />
              {t("Перейти к стратегиям", "Go to strategies")}
            </Link>
            <div className="bot-placeholder-metrics">
              <div>
                <span>{t("Баланс", "Balance")}</span>
                <b>—</b>
              </div>
              <div>
                <span>{t("Позиции", "Positions")}</span>
                <b>—</b>
              </div>
              <div>
                <span>P&L</span>
                <b>—</b>
              </div>
              <div>
                <span>{t("Сигнал", "Signal")}</span>
                <b>—</b>
              </div>
            </div>
          </div>
          <div className="terminal-bottom">
            <span>
              <ShieldCheck size={14} />
              {t(
                "Торговля на реальном счёте отключена",
                "Live account execution is disabled",
              )}
            </span>
            <code>NO ORDERS</code>
          </div>
        </section>
        <aside>
          <section className="panel">
            <div className="panel-head">
              <h2>{t("Состояние сервисов", "Service status")}</h2>
              <Radio size={16} />
            </div>
            {[
              [
                t("Поток котировок", "Quote feed"),
                t("Не подключён", "Disconnected"),
              ],
              [
                t("Paper-исполнение", "Paper execution"),
                t("Не настроено", "Not configured"),
              ],
              [
                t("Биржевые счета", "Exchange accounts"),
                t("Не подключены", "Disconnected"),
              ],
              [
                t("Уведомления", "Notifications"),
                t("Не настроены", "Not configured"),
              ],
            ].map(([label, val]) => (
              <div className="status-row" key={label}>
                <span>{label}</span>
                <Badge>{val}</Badge>
              </div>
            ))}
            <div className="padded">
              <Link to="/integrations" className="btn secondary full">
                {t("Интеграционный центр", "Integration center")}
                <ArrowRight size={15} />
              </Link>
            </div>
          </section>
          <Notice>
            {t(
              "Кнопки запуска появятся только после подключения сервиса с проверяемыми квитанциями исполнения. Сейчас ничего не торгует.",
              "Start controls require a connected service with verifiable execution receipts. Nothing is trading now.",
            )}
          </Notice>
        </aside>
      </div>
      <section className="panel">
        <div className="panel-head">
          <h2>{t("Аудит рабочего пространства", "Workspace audit")}</h2>
          <Badge>{t("Только ваши события", "Your events only")}</Badge>
        </div>
        {state.loading ? (
          <Spinner />
        ) : state.error ? (
          <ErrorPanel message={state.error} retry={state.reload} />
        ) : !events.length ? (
          <Empty
            icon={BookOpen}
            title={t("Событий пока нет", "No events yet")}
            text={t(
              "Здесь появятся реальные сохранения и проверки.",
              "Actual saves and tests will appear here.",
            )}
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>{t("Время", "Time")}</th>
                  <th>{t("Действие", "Action")}</th>
                  <th>{t("Объект", "Resource")}</th>
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 15).map((e: any, i: number) => (
                  <tr key={e.id || i}>
                    <td>{date(e.created_at, true)}</td>
                    <td>
                      <code>{e.action}</code>
                    </td>
                    <td className="muted mono">
                      {e.resource_id || e.entity_id || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

const providerCopy: Record<
  string,
  {
    name: [string, string];
    text: [string, string];
    icon: typeof Database;
    env?: string;
  }
> = {
  historical_data: {
    name: ["Исторические данные", "Historical market data"],
    text: [
      "Проверенные локальные архивы и явно маркированные синтетические данные. Чтение только из разрешённой истории.",
      "Verified local archives and explicitly labelled synthetic data. Reads are restricted to authorized historical periods.",
    ],
    icon: Database,
  },
  analysis: {
    name: ["Офлайн-исследователь", "Offline research analyst"],
    text: [
      "Детерминированный разбор сохранённых метрик. Работает без ключей и не называется генеративным AI.",
      "Deterministic analysis of saved metrics. Works without keys and is not described as generative AI.",
    ],
    icon: BookOpen,
  },
  ai: {
    name: ["AI-провайдер", "AI provider"],
    text: [
      "Интерфейс структурированных ответов подготовлен. Внешний адаптер, лимиты и проверка соединения ещё не включены.",
      "Structured response contracts are ready. The outbound adapter, limits and connection verification are not enabled.",
    ],
    icon: Sparkles,
    env: "KEDR_AI_API_KEY",
  },
  news: {
    name: ["Новости и тональность", "News and sentiment"],
    text: [
      "Сейчас только учебная лента. Публикация, first-seen и источник разделены в контракте.",
      "Currently an educational feed only. Publication time, first-seen time and source are separate in the contract.",
    ],
    icon: Newspaper,
    env: "KEDR_NEWS_API_KEY",
  },
  ml: {
    name: ["Обучение моделей", "Model training"],
    text: [
      "Сохранение исследовательских планов работает. Обучение, регистрация моделей и прогнозы не подключены.",
      "Research plans can be saved. Training, model registration and predictions are disconnected.",
    ],
    icon: Cpu,
  },
  execution: {
    name: ["Исполнение и paper trading", "Execution and paper trading"],
    text: [
      "Биржевые аккаунты, маршрутизация заявок и paper-заполнения не подключены. Реальная торговля отключена.",
      "Exchange accounts, order routing and paper fills are disconnected. Real trading is disabled.",
    ],
    icon: Bot,
  },
};
export function Integrations() {
  const { t, format } = useApp();
  const providers = useLoad(() =>
    Promise.all([api<any[]>("/providers"), api<Dataset[]>("/datasets")]),
  );
  const [detail, setDetail] = useState<string | null>(null);
  const statusLabel: Record<string, string> = {
    local_only: t("Локально подключено", "Locally connected"),
    offline_rules: t("Работает офлайн", "Working offline"),
    demo_fixture: t("Учебное демо", "Demo fixture"),
    not_connected: t("Не подключено", "Disconnected"),
    not_configured: t("Не настроено", "Not configured"),
    preview_only: t("Предпросмотр", "Preview only"),
  };
  return (
    <>
      <PageHead
        eyebrow={t("СЕРВИСЫ / КОНФИГУРАЦИЯ", "SERVICES / CONFIGURATION")}
        title={t("Интеграционный центр", "Integration center")}
        description={t(
          "Всё, что подключено. И всё, что пока требует подключения.",
          "Everything that is connected, and everything still awaiting integration.",
        )}
        actions={
          <button
            className="btn secondary"
            disabled={providers.loading}
            onClick={providers.reload}
          >
            <RefreshCw size={15} />
            {t("Обновить статусы", "Refresh status")}
          </button>
        }
      />
      <Notice>
        {t(
          "Внешние ключи никогда не вводятся в браузере. Будущие провайдеры настраиваются на сервере через окружение. Наличие переменной не означает работающую интеграцию.",
          "External keys are never entered in the browser. Future providers are configured server-side through the environment. An environment variable does not prove a working integration.",
        )}
      </Notice>
      {providers.loading ? (
        <Spinner />
      ) : providers.error ? (
        <ErrorPanel message={providers.error} retry={providers.reload} />
      ) : (
        <>
          <div className="integration-grid">
            {providers.data?.[0].map((p) => {
              const copy = providerCopy[p.id];
              const Icon = copy?.icon || Layers3;
              const ready = ["local_only", "offline_rules"].includes(p.status);
              return (
                <article className="integration-card" key={p.id}>
                  <div className="integration-card-top">
                    <span
                      className={`integration-icon ${ready ? "ready" : ""}`}
                    >
                      <Icon size={23} strokeWidth={1.4} />
                    </span>
                    <Badge
                      tone={
                        ready
                          ? "mint"
                          : p.status === "demo_fixture"
                            ? "amber"
                            : ""
                      }
                    >
                      <span
                        className={`status-dot small ${ready ? "" : "neutral"}`}
                      />
                      {statusLabel[p.status] || p.status}
                    </Badge>
                  </div>
                  <h2>{copy ? t(...copy.name) : p.name}</h2>
                  <p>{copy ? t(...copy.text) : p.message}</p>
                  <div className="integration-capabilities">
                    {p.capabilities?.map((c: string) => (
                      <code key={c}>{c}</code>
                    ))}
                  </div>
                  <button
                    className="text-button"
                    onClick={() => setDetail(p.id)}
                  >
                    {t("Контракт и подключение", "Contract and configuration")}
                    <ArrowUpRight size={15} />
                  </button>
                </article>
              );
            })}
          </div>
          <section className="panel">
            <div className="panel-head">
              <h2>
                {t("Каталог доступных наборов", "Available dataset catalog")}
              </h2>
              <Database size={18} />
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{t("Набор", "Dataset")}</th>
                    <th>{t("Источник", "Source")}</th>
                    <th>{t("Период", "Period")}</th>
                    <th>{t("Свечей", "Bars")}</th>
                    <th>SHA256</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.data?.[1].map((d) => (
                    <tr key={d.id}>
                      <td>
                        <b>{d.name}</b>
                        <small className="table-subtext">
                          {d.symbol} · {d.timeframe}
                        </small>
                        {d.status === "unavailable" && <small className="table-subtext">{d.error || t("Не установлен", "Not installed")}</small>}
                      </td>
                      <td>
                        <SourceBadge type={d.source_type} />
                      </td>
                      <td className="mono">
                        {d.start.slice(0, 10)}
                        <br />
                        {d.end.slice(0, 10)}
                      </td>
                      <td className="mono">{format(d.bars, 0)}</td>
                      <td>
                        <code title={d.sha256}>{d.sha256?.slice(0, 15)}…</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="future-integrations">
            <span>{t("Следующие контракты", "Future contracts")}</span>
            <Badge>{t("Уведомления", "Notifications")}</Badge>
            <Badge>
              {t("Региональная доступность", "Regional availability")}
            </Badge>
            <Badge>{t("Биллинг", "Billing")}</Badge>
            <p>
              {t(
                "Не подключены. Оплата и публичное развёртывание не активированы.",
                "Disconnected. Payments and public deployment are not enabled.",
              )}
            </p>
          </div>
        </>
      )}
      {detail && (
        <Modal
          title={
            providerCopy[detail] ? t(...providerCopy[detail].name) : detail
          }
          onClose={() => setDetail(null)}
        >
          <Badge>
            {
              statusLabel[
                providers.data?.[0].find((p) => p.id === detail)?.status ||
                  "not_configured"
              ]
            }
          </Badge>
          <p>{providerCopy[detail] && t(...providerCopy[detail].text)}</p>
          {providerCopy[detail]?.env && (
            <>
              <label>
                {t(
                  "Серверная переменная окружения",
                  "Server-side environment variable",
                )}
              </label>
              <pre className="json-block">{providerCopy[detail].env}=…</pre>
              <Notice>
                {t(
                  "Ключ сам по себе не активирует внешние запросы. Нужны адаптер, проверка здоровья, лимиты, безопасные ошибки и контроль стоимости.",
                  "A key alone does not enable outbound requests. An adapter, health checks, limits, safe errors and cost control are required.",
                )}
              </Notice>
            </>
          )}
          <p className="fine-print">
            {t(
              "Подробности реализации находятся в документации проекта DATA_PROVIDERS.md, AI_INTEGRATION.md и SECURITY.md.",
              "Implementation details are in DATA_PROVIDERS.md, AI_INTEGRATION.md and SECURITY.md in the project documentation.",
            )}
          </p>
          <div className="modal-actions">
            <button className="btn secondary" onClick={() => setDetail(null)}>
              {t("Понятно", "Understood")}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

export function Settings() {
  const {
    t,
    user,
    locale,
    setLocale,
    timezone,
    setTimezone,
    theme,
    setTheme,
    updateProfile,
    notify,
    date,
  } = useApp();
  const [name, setName] = useState(user?.name || ""),
    [level, setLevel] = useState(user?.level || "beginner"),
    [busy, setBusy] = useState(false);
  const zones = [
    "UTC",
    "Europe/Minsk",
    "Europe/Moscow",
    "Europe/Kyiv",
    "Asia/Almaty",
    "Asia/Tashkent",
    "Asia/Bishkek",
    "Asia/Tbilisi",
    "Europe/London",
    "America/New_York",
  ];
  return (
    <>
      <PageHead
        eyebrow={t("ЛИЧНОЕ ПРОСТРАНСТВО", "PERSONAL WORKSPACE")}
        title={t("Настройки", "Settings")}
        description={t(
          "Язык, время и оформление — в вашем привычном ритме.",
          "Language, time and appearance, at your own pace.",
        )}
      />
      <div className="settings-grid">
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Ваш профиль", "Your profile")}</h2>
            <Badge>
              {user?.is_demo
                ? t("Локальное демо", "Local demo")
                : t("Приватный аккаунт", "Private account")}
            </Badge>
          </div>
          <form
            className="padded"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                await updateProfile({ name, level });
                notify(t("Профиль обновлён", "Profile updated"));
              } catch (error: any) {
                notify(error.message, true);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              {t("Имя", "Name")}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
              />
            </label>
            <label>
              Email
              <input value={user?.email || ""} disabled />
            </label>
            <label>
              {t("Уровень знакомства", "Experience level")}
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                <option value="beginner">{t("Начинающий", "Beginner")}</option>
                <option value="intermediate">
                  {t("Средний", "Intermediate")}
                </option>
                <option value="advanced">{t("Продвинутый", "Advanced")}</option>
              </select>
            </label>
            <button className="btn primary" disabled={busy} type="submit">
              <Check size={15} />
              {t("Сохранить профиль", "Save profile")}
            </button>
          </form>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Язык и время", "Language & time")}</h2>
            <Globe2 size={18} />
          </div>
          <div className="padded">
            <label>
              {t("Язык интерфейса", "Interface language")}
              <select
                value={locale}
                onChange={(e) => setLocale(e.target.value as "ru" | "en")}
              >
                <option value="ru">Русский</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              {t("Часовой пояс отображения", "Display timezone")}
              <select
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              >
                {zones.map((z) => (
                  <option key={z}>{z}</option>
                ))}
              </select>
              <small>
                {t(
                  "Расчёты и сохранённые временные метки используют UTC. Эта настройка меняет только отображение.",
                  "Calculations and stored timestamps use UTC. This setting changes display only.",
                )}
              </small>
            </label>
            <div className="timezone-preview">
              <Clock3 size={16} />
              <span>{t("Пример формата", "Format preview")}</span>
              <code>{date("2025-12-31T12:00:00Z", true)}</code>
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Оформление", "Appearance")}</h2>
            <Sun size={18} />
          </div>
          <div className="theme-cards">
            <button
              className={`theme-card dark ${theme === "dark" ? "selected" : ""}`}
              onClick={() => setTheme("dark")}
            >
              <div className="theme-preview">
                <i />
                <div>
                  <span />
                  <span />
                  <span />
                </div>
              </div>
              <span>
                {t("Графит", "Graphite")}
                {theme === "dark" && <Check size={14} />}
              </span>
            </button>
            <button
              className={`theme-card light ${theme === "light" ? "selected" : ""}`}
              onClick={() => setTheme("light")}
            >
              <div className="theme-preview">
                <i />
                <div>
                  <span />
                  <span />
                  <span />
                </div>
              </div>
              <span>
                {t("Минерал", "Mineral")}
                {theme === "light" && <Check size={14} />}
              </span>
            </button>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Приватность и доступ", "Privacy & access")}</h2>
            <ShieldCheck size={18} />
          </div>
          <div className="padded">
            <div className="quality-check">
              <LockKeyhole size={17} />
              <div>
                <b>
                  {t(
                    "Стратегии приватны по умолчанию",
                    "Strategies are private by default",
                  )}
                </b>
                <p>
                  {t(
                    "Публикация доступна только по вашему действию для конкретной версии и сохранённого результата.",
                    "Publishing requires your action for an exact version and saved result.",
                  )}
                </p>
              </div>
            </div>
            <div className="quality-check">
              <ShieldCheck size={17} />
              <div>
                <b>
                  {t(
                    "Счета и ключи не запрашиваются",
                    "No accounts or keys requested",
                  )}
                </b>
                <p>
                  {t(
                    "Региональные условия, биржевой доступ и промышленная безопасность требуют отдельной настройки до публичного запуска.",
                    "Regional terms, exchange access and production security require separate configuration before public launch.",
                  )}
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
