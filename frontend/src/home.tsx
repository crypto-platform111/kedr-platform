import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Code2,
  Database,
  FlaskConical,
  GitBranch,
  Layers3,
  LockKeyhole,
  Network,
  Play,
  Plus,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Users,
  Waves,
} from "lucide-react";
import {
  api,
  brand,
  post,
  type Dataset,
  type Run,
  type Strategy,
  type Template,
} from "./api";
import {
  Badge,
  Empty,
  ErrorPanel,
  Metric,
  Notice,
  PageHead,
  SourceBadge,
  Spinner,
  Steps,
  useLoad,
} from "./components";
import { useApp } from "./context";
import { Brand, LocaleToggle, ThemeToggle } from "./App";

export function LandingPage() {
  const { t, user, authenticate, locale, notify } = useApp();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const demo = async () => {
    if (user) {
      navigate("/dashboard");
      return;
    }
    setBusy(true);
    try {
      await authenticate("/auth/demo");
      navigate("/onboarding");
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="landing">
      <div className="landing-grid" />
      <header className="landing-header">
        <Brand />
        <nav>
          <a href="#workflow">{t("Как это работает", "How it works")}</a>
          <a href="#research">{t("Возможности", "Capabilities")}</a>
          <a href="#pricing">{t("Доступ", "Access")}</a>
        </nav>
        <div>
          <LocaleToggle />
          <ThemeToggle />
          <Link
            to={user ? "/dashboard" : "/auth"}
            className="btn secondary compact"
          >
            {user ? t("В пространство", "Workspace") : t("Войти", "Log in")}
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </header>
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="status-dot" />
            {t("ОТ ИДЕИ — К ДОКАЗАТЕЛЬСТВАМ", "FROM AN IDEA TO EVIDENCE")}
          </div>
          <h1>
            {t("Ваша стратегия.", "Your strategy.")}
            <br />
            <span>{t("Ясная логика.", "Clear logic.")}</span>
            <br />
            {t("Честная проверка.", "Honest testing.")}
          </h1>
          <p>
            {t(
              "Собирайте криптостратегии визуально. Проверяйте на истории. Понимайте результат — прежде чем рисковать капиталом.",
              "Build crypto strategies visually. Test them against history. Understand the results before putting capital at risk.",
            )}
          </p>
          <div className="hero-buttons">
            <button
              data-testid="demo-login"
              className="btn primary large"
              disabled={busy}
              onClick={demo}
            >
              {busy
                ? t("Открываем…", "Opening…")
                : t("Открыть лабораторию", "Open the workspace")}
              <ArrowRight size={18} />
            </button>
            <a className="text-button" href="#workflow">
              <Play size={14} />
              {t("Посмотреть, как устроено", "See how it works")}
            </a>
          </div>
          <div className="hero-note">
            <Check size={14} />
            {t("Без кода", "No code")}
            <span /> <Check size={14} />
            {t("Без API-ключей", "No API keys")}
            <span />
            <Check size={14} />
            {t("Локальный демо-доступ", "Local demo access")}
          </div>
        </div>
        <div className="hero-art">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="preview-terminal">
            <div className="preview-top">
              <div className="traffic">
                <i />
                <i />
                <i />
              </div>
              <span>kedr / strategy-workspace</span>
              <span className="mono">01</span>
            </div>
            <div className="preview-toolbar">
              <span className="preview-icon">
                <Network size={17} />
              </span>
              <div>
                <strong>
                  {t("Тренд. Без лишнего шума.", "Trend. Without the noise.")}
                </strong>
                <small>
                  BTC / 4H <span>•</span>{" "}
                  {t("Схема стратегии", "Strategy diagram")}
                </small>
              </div>
              <Badge tone="mint">
                {t("Визуальный редактор", "Visual editor")}
              </Badge>
            </div>
            <div className="preview-canvas">
              <svg
                className="preview-wires"
                viewBox="0 0 600 320"
                aria-hidden="true"
              >
                <path d="M138 90 C210 90 190 174 260 174" />
                <path d="M138 246 C210 246 190 198 260 198" />
                <path d="M395 186 C440 186 430 186 464 186" />
              </svg>
              <div className="preview-node price">
                <span>
                  <Activity size={14} />
                  {t("Цена закрытия", "Close price")}
                </span>
                <code>market.close</code>
                <i />
              </div>
              <div className="preview-node average">
                <span>
                  <Waves size={14} />
                  {t("Средняя цена", "Moving average")}
                </span>
                <code>SMA · 28</code>
                <i />
              </div>
              <div className="preview-node logic">
                <span>
                  <GitBranch size={14} />
                  {t("Выше средней?", "Above average?")}
                </span>
                <code>price &gt; SMA</code>
                <i className="input one" />
                <i className="input two" />
                <i />
              </div>
              <div className="preview-node action">
                <span>
                  <ArrowUpRight size={14} />
                  {t("Войти", "Enter")}
                </span>
                <code>LONG</code>
                <i className="input" />
              </div>
              <div className="canvas-label">
                {t(
                  "ИЛЛЮСТРАЦИЯ ПРАВИЛ · НЕ ТОРГОВЫЙ СИГНАЛ",
                  "RULE DIAGRAM · NOT A TRADE SIGNAL",
                )}
              </div>
            </div>
            <div className="preview-bottom">
              <span>
                <ShieldCheck size={15} />
                {t(
                  "Прозрачные правила. Воспроизводимый результат.",
                  "Transparent rules. Reproducible results.",
                )}
              </span>
              <span className="preview-arrow">
                <ArrowRight size={18} />
              </span>
            </div>
          </div>
          <div className="floating-note">
            <FlaskConical size={21} />
            <div>
              <b>
                {t(
                  "Красивый график — ещё не доказательство",
                  "A beautiful chart is not evidence",
                )}
              </b>
              <span>
                {t(
                  "Проверяйте издержки, риски и качество данных.",
                  "Check costs, risks and data quality.",
                )}
              </span>
            </div>
          </div>
        </div>
      </section>
      <div className="landing-strip">
        <span>
          {t(
            "СОЗДАНО ДЛЯ ОСМЫСЛЕННЫХ РЕШЕНИЙ",
            "BUILT FOR THOUGHTFUL DECISIONS",
          )}
        </span>
        <div>
          <Database size={17} />{" "}
          {t("Источники с происхождением", "Data provenance")}
        </div>
        <div>
          <GitBranch size={17} />
          {t("Версии правил", "Versioned rules")}
        </div>
        <div>
          <ShieldCheck size={17} />
          {t("Исследовательская дисциплина", "Research discipline")}
        </div>
      </div>
      <section className="landing-section" id="workflow">
        <div className="section-intro">
          <div className="eyebrow">
            01 / {t("ВАШ РАБОЧИЙ ПРОЦЕСС", "YOUR WORKFLOW")}
          </div>
          <h2>
            {t("Сложные идеи.", "Complex ideas.")}
            <br />
            <span>{t("Понятные шаги.", "Simple steps.")}</span>
          </h2>
          <p>
            {t(
              "Один рабочий процесс: от первого правила до сохранённого исследования.",
              "One connected workflow from your first rule to a saved research record.",
            )}
          </p>
        </div>
        <div className="workflow-cards">
          {[
            [
              Network,
              t("Соберите логику", "Build your logic"),
              t(
                "Начните с готового шаблона. Соединяйте данные, индикаторы и действия.",
                "Start with a template. Connect data, indicators and actions.",
              ),
            ],
            [
              Activity,
              t("Проверьте на истории", "Test against history"),
              t(
                "Выберите источник и период. Задайте комиссию, проскальзывание и задержку.",
                "Choose a source and period. Set fees, slippage and execution delay.",
              ),
            ],
            [
              FlaskConical,
              t("Разберитесь в результате", "Understand the results"),
              t(
                "Посмотрите сделки, просадку и ограничения. Сохраните точную версию.",
                "Inspect trades, drawdown and limitations. Preserve the exact version.",
              ),
            ],
          ].map(([Icon, title, text], i) => {
            const I = Icon as typeof Network;
            return (
              <div className="workflow-card" key={i}>
                <span className="step-index">0{i + 1}</span>
                <I size={26} strokeWidth={1.3} />
                <h3>{String(title)}</h3>
                <p>{String(text)}</p>
              </div>
            );
          })}
        </div>
      </section>
      <section className="landing-section capabilities" id="research">
        <div className="section-intro">
          <div className="eyebrow">
            02 / {t("БОЛЬШЕ, ЧЕМ БЭКТЕСТ", "BEYOND A BACKTEST")}
          </div>
          <h2>
            {t("Не просто результат.", "More than a result.")}
            <br />
            <span>{t("Контекст для решения.", "Context for a decision.")}</span>
          </h2>
        </div>
        <div className="feature-mosaic">
          <div className="feature-tile feature-large">
            <div className="mini-bars">
              {[22, 38, 31, 52, 44, 67, 61, 84, 70, 96, 82, 106].map((h, i) => (
                <i style={{ height: h }} key={i} />
              ))}
            </div>
            <span className="eyebrow">RESEARCH / ANALYTICS</span>
            <h3>
              {t("Каждая цифра — с объяснением", "Every number, explained")}
            </h3>
            <p>
              {t(
                "Собственный график капитала, пассивный ориентир, журнал сделок и открытая методология расчётов.",
                "Equity, a passive benchmark, trade history and transparent calculations.",
              )}
            </p>
            <small>
              {t(
                "Декоративная визуализация, не результат стратегии",
                "Decorative visualization, not strategy performance",
              )}
            </small>
          </div>
          <div className="feature-tile">
            <Sparkles size={25} />
            <h3>{t("Понимать, а не угадывать", "Understand, not guess")}</h3>
            <p>
              {t(
                "Офлайн-разбор по измеренным показателям уже доступен. AI-провайдер подключается отдельно.",
                "Offline explanations based on measured metrics are available now. AI is a separate integration.",
              )}
            </p>
            <Badge>{t("Офлайн-режим", "Offline mode")}</Badge>
          </div>
          <div className="feature-tile">
            <Users size={25} />
            <h3>{t("Делитесь логикой", "Share your logic")}</h3>
            <p>
              {t(
                "Публикуйте конкретную версию с её реальным тестом. Изучайте и копируйте открытые исследования.",
                "Publish an exact version with its actual test. Explore and fork public research.",
              )}
            </p>
            <Badge>{t("Без обещаний доходности", "No return promises")}</Badge>
          </div>
        </div>
      </section>
      <section className="landing-access" id="pricing">
        <div>
          <div className="eyebrow">
            03 / {t("НАЧНИТЕ С ИССЛЕДОВАНИЯ", "START WITH RESEARCH")}
          </div>
          <h2>
            {t("Меньше догадок.", "Less guessing.")}
            <br />
            {t("Больше понимания.", "More understanding.")}
          </h2>
          <p>
            {t(
              "Локальная версия — бесплатно. Без подписки, банковской карты и доступа к биржевому счёту.",
              "The local version is free. No subscription, payment card or exchange account connection.",
            )}
          </p>
        </div>
        <div className="access-card">
          <div>
            <span>{t("ЛОКАЛЬНАЯ ЛАБОРАТОРИЯ", "LOCAL WORKSPACE")}</span>
            <Badge tone="mint">{t("Доступно сейчас", "Available now")}</Badge>
          </div>
          <h3>
            {t("Бесплатно", "Free")}
            <small> / local</small>
          </h3>
          <ul>
            {[
              t(
                "Визуальный конструктор и версии",
                "Visual builder and versions",
              ),
              t(
                "Исторические тесты и аналитика",
                "Historical tests and analytics",
              ),
              t("Офлайн-разбор и публикация", "Offline reports and publishing"),
            ].map((s) => (
              <li key={s}>
                <Check size={16} />
                {s}
              </li>
            ))}
          </ul>
          <button className="btn primary full" onClick={demo} disabled={busy}>
            {t("Открыть демо", "Open demo")}
            <ArrowRight size={17} />
          </button>
          <p>
            {t(
              "Облачные тарифы и платные услуги ещё не запущены.",
              "Cloud plans and paid services have not launched.",
            )}
          </p>
        </div>
      </section>
      <footer className="landing-footer">
        <Brand />
        <p>
          {t(
            "Исследуйте идеи. Сохраняйте критическое мышление.",
            "Explore ideas. Keep a critical mind.",
          )}
        </p>
        <span>LOCAL FIRST · RESEARCH FIRST</span>
      </footer>
    </div>
  );
}

export function AuthPage() {
  const { t, user, authenticate } = useApp();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login"),
    [form, setForm] = useState({ email: "", password: "", name: "" }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submit = async (demo = false) => {
    setError("");
    setBusy(true);
    try {
      await authenticate(
        demo ? "/auth/demo" : `/auth/${mode}`,
        demo
          ? {}
          : mode === "login"
            ? { email: form.email, password: form.password }
            : form,
      );
      navigate(mode === "register" || demo ? "/onboarding" : "/dashboard");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth-page">
      <div className="auth-story">
        <Brand />
        <div>
          <div className="eyebrow">IDEA → LOGIC → EVIDENCE</div>
          <h1>
            {t("Хорошая идея", "A good idea")}
            <br />
            {t("начинается", "starts with")}
            <br />
            <span>{t("с вопроса.", "a question.")}</span>
          </h1>
          <p>
            {t(
              "А убедительный ответ — с прозрачных данных и честной проверки.",
              "A convincing answer starts with transparent data and an honest test.",
            )}
          </p>
          <div className="auth-statement">
            <ShieldCheck size={20} />
            {t(
              "Ваши стратегии приватны, пока вы сами их не опубликуете.",
              "Your strategies stay private until you choose to publish them.",
            )}
          </div>
        </div>
        <span className="mono">KEDR / STRATEGY WORKSPACE</span>
      </div>
      <div className="auth-form-wrap">
        <div className="auth-tools">
          <LocaleToggle />
          <ThemeToggle />
        </div>
        <form
          className="auth-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <div className="eyebrow">
            {t("ЛИЧНОЕ ПРОСТРАНСТВО", "YOUR WORKSPACE")}
          </div>
          <h2>
            {mode === "login"
              ? t("С возвращением", "Welcome back")
              : t("Начнём исследование", "Start your research")}
          </h2>
          <p>
            {t(
              "Создавайте, проверяйте и сохраняйте свои идеи.",
              "Create, test and preserve your ideas.",
            )}
          </p>
          <div className="segmented">
            <button
              type="button"
              className={mode === "login" ? "active" : ""}
              onClick={() => setMode("login")}
            >
              {t("Вход", "Log in")}
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => setMode("register")}
            >
              {t("Регистрация", "Register")}
            </button>
          </div>
          {mode === "register" && (
            <label>
              {t("Имя", "Name")}
              <input
                required
                maxLength={80}
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                autoComplete="name"
                placeholder={t(
                  "Как к вам обращаться?",
                  "What should we call you?",
                )}
              />
            </label>
          )}
          <label>
            Email
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              autoComplete="email"
              placeholder="you@example.com"
            />
          </label>
          <label>
            {t("Пароль", "Password")}
            <input
              type="password"
              required
              minLength={10}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              placeholder={t("Не менее 10 символов", "At least 10 characters")}
            />
          </label>
          {error && (
            <div className="inline-error" role="alert">
              {error}
            </div>
          )}
          <button type="submit" disabled={busy} className="btn primary full">
            {busy
              ? t("Подключаем…", "Connecting…")
              : mode === "login"
                ? t("Войти в пространство", "Enter your workspace")
                : t("Создать аккаунт", "Create account")}
            <ArrowRight size={17} />
          </button>
          <div className="or">
            <span />
            {t("или начните без регистрации", "or explore without registering")}
            <span />
          </div>
          <button
            data-testid="demo-login"
            type="button"
            className="btn secondary full"
            disabled={busy}
            onClick={() => void submit(true)}
          >
            <FlaskConical size={17} />
            {t("Открыть демо-сессию", "Open a demo session")}
          </button>
          <p className="fine-print">
            {t(
              "Отдельный локальный профиль. Доступ к бирже не требуется. Реальная торговля отключена.",
              "An isolated local profile. No exchange access needed. Real trading is disabled.",
            )}
          </p>
          {user && (
            <Link className="text-button" to="/dashboard">
              {t(
                "Вернуться в открытый профиль",
                "Return to your current profile",
              )}
              <ArrowRight size={15} />
            </Link>
          )}
        </form>
      </div>
    </div>
  );
}

export function Onboarding() {
  const { t, updateProfile, notify, user } = useApp();
  const [level, setLevel] = useState(user?.level || "beginner"),
    [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  return (
    <div className="onboarding">
      <div className="eyebrow">WELCOME TO KEDR</div>
      <h1>{t("Ваш ритм исследования", "Your research, your pace")}</h1>
      <p>
        {t(
          "Выберите комфортный уровень. Сами возможности доступны всем, а уровень можно изменить позже.",
          "Choose a comfortable starting point. Everyone gets the same capabilities; you can change this later.",
        )}
      </p>
      <div className="level-grid">
        {[
          [
            "beginner",
            BookOpen,
            t("Начинаю", "Getting started"),
            t(
              "Хочу понять правила и проверить первую идею с подсказками.",
              "I want to understand the rules and test my first idea with guidance.",
            ),
          ],
          [
            "intermediate",
            Network,
            t("Практикую", "Building experience"),
            t(
              "Знаком с индикаторами. Хочу сравнивать идеи и контролировать риск.",
              "I know indicators and want to compare ideas and manage risk.",
            ),
          ],
          [
            "advanced",
            Code2,
            t("Исследую", "Researching"),
            t(
              "Нужны детали исполнения, происхождение данных и воспроизводимость.",
              "I need execution details, provenance and reproducibility.",
            ),
          ],
        ].map(([id, Icon, title, text]) => {
          const I = Icon as typeof Network;
          return (
            <button
              className={`level-card ${level === id ? "selected" : ""}`}
              key={String(id)}
              onClick={() => setLevel(String(id))}
            >
              <div>
                <I size={26} />
                <span className="radio-dot">
                  {level === id && <Check size={12} />}
                </span>
              </div>
              <h3>{String(title)}</h3>
              <p>{String(text)}</p>
            </button>
          );
        })}
      </div>
      <Notice>
        {t(
          "Всё начинается с шаблона. Это учебный пример, а не рекомендация покупать или продавать.",
          "Start with a template. It is an educational example, not a recommendation to buy or sell.",
        )}
      </Notice>
      <button
        className="btn primary large"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await updateProfile({ level });
            navigate("/new");
          } catch (e: any) {
            notify(e.message, true);
          } finally {
            setBusy(false);
          }
        }}
      >
        {t("Выбрать первую стратегию", "Choose your first strategy")}
        <ArrowRight size={17} />
      </button>
      <Link to="/dashboard" className="text-button">
        {t("Сначала осмотреться", "Explore the workspace first")}
      </Link>
    </div>
  );
}

export function Dashboard() {
  const { t, user, format, date } = useApp();
  const result = useLoad(() =>
    Promise.all([
      api<Strategy[]>("/strategies"),
      api<Run[]>("/backtests"),
      api<Dataset[]>("/datasets"),
      api("/audit"),
    ]),
  );
  if (result.loading) return <Spinner />;
  if (result.error)
    return <ErrorPanel message={result.error} retry={result.reload} />;
  const [strategies, runs, datasets, audit] = result.data!;
  const activities = Array.isArray(audit) ? audit : audit.events || [];
  return (
    <>
      <PageHead
        eyebrow={t("ЛАБОРАТОРИЯ / ОБЗОР", "WORKSPACE / OVERVIEW")}
        title={`${t("Добро пожаловать", "Welcome")}, ${user?.name?.split(" ")[0] || t("исследователь", "researcher")}`}
        description={t(
          "Здесь идеи становятся правилами, а результаты — вопросами для следующего исследования.",
          "Turn ideas into rules, and results into questions for your next research.",
        )}
        actions={
          <Link className="btn primary" to="/new">
            <Plus size={17} />
            {t("Новая стратегия", "New strategy")}
          </Link>
        }
      />
      <div className="welcome-banner">
        <div className="banner-line" />
        <div>
          <Badge tone="mint">{t("СЛЕДУЮЩИЙ ШАГ", "NEXT STEP")}</Badge>
          <h2>
            {strategies.length
              ? t(
                  "Одна идея. Одна точная проверка.",
                  "One idea. One precise test.",
                )
              : t(
                  "У вашей первой идеи есть рабочее пространство.",
                  "Your first idea has a workspace.",
                )}
          </h2>
          <p>
            {t(
              "Начните с простого правила. Сравните с пассивным владением. Обратите внимание на издержки и просадку.",
              "Start with a simple rule. Compare it with passive holding. Pay attention to costs and drawdown.",
            )}
          </p>
          <Link
            to={strategies.length ? `/builder/${strategies[0].id}` : "/new"}
            className="text-button"
          >
            {strategies.length
              ? t("Продолжить работу", "Continue working")
              : t("Выбрать учебный шаблон", "Choose a starter template")}
            <ArrowRight size={16} />
          </Link>
        </div>
        <div className="banner-symbol">
          <GitBranch size={75} strokeWidth={0.75} />
          <span>BUILD → TEST → LEARN</span>
        </div>
      </div>
      <div className="summary-grid">
        <Metric
          label={t("Мои стратегии", "My strategies")}
          value={String(strategies.length)}
          sub={t("Приватные рабочие проекты", "Private workspace projects")}
        />
        <Metric
          label={t("Сохранённые тесты", "Saved tests")}
          value={String(runs.length)}
          sub={t("История, которую можно открыть", "A history you can reopen")}
        />
        <Metric
          label={t("Доступные источники", "Available sources")}
          value={String(datasets.length)}
          sub={t("Исторические архивы и демо", "Historical archives and demo")}
        />
        <div className="metric status-metric">
          <span>{t("Исполнение на бирже", "Exchange execution")}</span>
          <strong>
            <LockKeyhole size={21} />
            {t("Отключено", "Disabled")}
          </strong>
          <small>
            {t(
              "Средства и счета не подключены",
              "No funds or accounts connected",
            )}
          </small>
        </div>
      </div>
      <div className="dashboard-columns">
        <section className="panel">
          <div className="panel-head">
            <h2>
              {t("Мои стратегии", "My strategies")}
              <span>{strategies.length}</span>
            </h2>
            <Link to="/new" className="text-button">
              {t("Создать", "Create")}
              <Plus size={15} />
            </Link>
          </div>
          {!strategies.length ? (
            <Empty
              icon={Network}
              title={t("Начнём с понятной идеи", "Start with a clear idea")}
              text={t(
                "Выберите шаблон и измените условие. Все правила останутся у вас.",
                "Choose a template and change a condition. Every rule stays yours.",
              )}
              action={t("Открыть шаблоны", "Explore templates")}
              to="/new"
            />
          ) : (
            <div className="strategy-list">
              {strategies.map((s) => (
                <Link
                  to={`/builder/${s.id}`}
                  key={s.id}
                  className="strategy-row"
                >
                  <span className="strategy-icon">
                    <GitBranch size={21} />
                  </span>
                  <div>
                    <h3>{s.name}</h3>
                    <p>
                      {s.spec.symbol} <span>·</span> {s.spec.timeframe}{" "}
                      <span>·</span> {s.spec.nodes.length} {t("узлов", "nodes")}
                    </p>
                  </div>
                  <div className="row-meta">
                    <Badge>v{s.version_number || 1}</Badge>
                    <small>{date(s.updated_at)}</small>
                  </div>
                  <ChevronRight size={16} />
                </Link>
              ))}
            </div>
          )}
        </section>
        <section className="panel recent-panel">
          <div className="panel-head">
            <h2>{t("Последние проверки", "Recent tests")}</h2>
            <Activity size={17} />
          </div>
          {!runs.length ? (
            <Empty
              icon={FlaskConical}
              title={t(
                "Результаты появятся после теста",
                "Your results will appear here",
              )}
              text={t(
                "Мы не заполняем этот экран примерной доходностью.",
                "We do not fill this screen with invented returns.",
              )}
            />
          ) : (
            <div className="run-list">
              {runs.slice(0, 5).map((r) => (
                <Link to={`/backtests/${r.id}`} key={r.id}>
                  <span className="run-icon">
                    <Activity size={17} />
                  </span>
                  <div>
                    <b>
                      {r.strategy_name ||
                        strategies.find((s) => s.id === r.strategy_id)?.name ||
                        t("Исторический тест", "Historical test")}
                    </b>
                    <small>
                      {date(r.created_at)} · {r.dataset?.symbol || "BTCUSDT"}
                    </small>
                  </div>
                  <strong
                    className={
                      (r.metrics?.net_return_pct || 0) < 0
                        ? "negative"
                        : "positive"
                    }
                  >
                    {format(r.metrics?.net_return_pct)}%
                  </strong>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
      <div className="dashboard-columns lower">
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Источники рынка", "Market data sources")}</h2>
            <span className="mono">DATA / NOT LIVE</span>
          </div>
          <div className="dataset-list">
            {datasets.map((d) => (
              <div key={d.id}>
                <span
                  className={`coin-icon ${d.symbol.startsWith("ETH") ? "eth" : d.symbol.startsWith("SOL") ? "sol" : ""}`}
                >
                  {d.symbol.startsWith("BTC")
                    ? "₿"
                    : d.symbol.startsWith("ETH")
                      ? "Ξ"
                      : "◎"}
                </span>
                <div>
                  <b>
                    {d.symbol} <small>{d.timeframe}</small>
                  </b>
                  <span>
                    {d.status === "unavailable" ? t("Не установлен", "Not installed") : `${date(d.start)} — ${date(d.end)}`}
                  </span>
                  {d.status === "unavailable" && <small>{d.error || t("Архив недоступен", "Archive unavailable")}</small>}
                </div>
                <SourceBadge type={d.source_type} />
              </div>
            ))}
          </div>
          <p className="panel-footnote">
            {t(
              "Текущие котировки не подключены. Архивные данные не являются текущей ценой.",
              "Live quotes are disconnected. Archived prices are not current prices.",
            )}
          </p>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>{t("Журнал исследования", "Research activity")}</h2>
            <Clock3 size={17} />
          </div>
          {activities.length ? (
            <div className="activity-list">
              {activities.slice(0, 5).map((a: any, i: number) => (
                <div key={a.id || i}>
                  <span className="activity-line-dot" />
                  <div>
                    <b>{a.action || a.event || t("Событие", "Event")}</b>
                    <span>{a.created_at ? date(a.created_at, true) : ""}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              icon={BookOpen}
              title={t("Чистая история", "A fresh history")}
              text={t(
                "Сохранения, тесты и публикации появятся здесь.",
                "Saves, tests and publications will appear here.",
              )}
            />
          )}
        </section>
      </div>
    </>
  );
}

export function NewStrategy() {
  const { t, locale, notify } = useApp();
  const { data, loading, error, reload } = useLoad(() =>
    api<Template[]>("/templates"),
  );
  const [busy, setBusy] = useState("");
  const navigate = useNavigate();
  const createBlank = async (mode="visual") => {setBusy("blank");try{const draft=await post<Strategy>("/strategies",{name:t("Новая стратегия","Untitled strategy"),description:"",tags:["scratch"],spec:{schema_version:2,symbol:"BTCUSDT",timeframe:"4h",nodes:[],edges:[],risk:{max_exposure:1,stop_loss_pct:null,take_profit_pct:null}}});navigate(`/builder/${draft.id}${mode==="ai"?"?mode=ai":mode==="guided"?"?mode=guided":""}`);}catch(e:any){notify(e.message,true);}finally{setBusy("");}};
  const create = async (template: Template) => {
    setBusy(template.id);
    try {
      const s = await post<Strategy>("/strategies", {
        name: template.name[locale],
        description: template.description[locale],
        tags: ["template"],
        spec: template.spec,
      });
      navigate(`/builder/${s.id}`);
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <PageHead
        eyebrow={t("НОВОЕ ИССЛЕДОВАНИЕ", "NEW RESEARCH")}
        title={t("Начните с понятного правила", "Start with a clear rule")}
        description={t(
          "Готовая логика для знакомства с конструктором. Каждый параметр можно изменить.",
          "Working logic to get you started. Every parameter can be changed.",
        )}
      />
      <div className="creation-modes"><button data-testid="create-blank" className="creation-mode primary-mode" disabled={!!busy} onClick={()=>void createBlank()}><Network size={25}/><span className="eyebrow">01 / EMPTY CANVAS</span><h2>{t("Создать с нуля","Create from scratch")}</h2><p>{t("Ни одного готового узла. Соберите собственную логику из типизированных блоков.","No preselected nodes. Construct your own logic from typed building blocks.")}</p><span className="text-button">{t("Открыть чистый холст","Open blank canvas")}<ArrowUpRight size={16}/></span></button><button data-testid="create-guided" className="creation-mode" disabled={!!busy} onClick={()=>void createBlank("guided")}><GitBranch size={25}/><span className="eyebrow">02 / GUIDED RULES</span><h2>{t("Собрать правило","Build a rule")}</h2><p>{t("Когда это произойдёт… войти с такими рамками риска. Мастер создаст ту же схему.","When this happens… enter with these risk limits. The wizard builds the same specification.")}</p><span className="text-button">{t("Открыть мастер","Open rule wizard")}<ArrowUpRight size={16}/></span></button><button data-testid="create-ai" className="creation-mode" disabled={!!busy} onClick={()=>void createBlank("ai")}><Sparkles size={25}/><span className="eyebrow">03 / CONTEXTUAL COPILOT</span><h2>{t("Обсудить с помощником","Discuss with copilot")}</h2><p>{t("Разговор о правилах. AI-правки доступны только при подключённом провайдере и вашем одобрении.","Discuss rules. AI edits require a configured provider and your explicit approval.")}</p><span className="text-button">{t("Открыть помощника","Open copilot")}<ArrowUpRight size={16}/></span></button></div>
      <Steps />
      <div className="template-intro">
        <span>
          <Network size={24} />
        </span>
        <p>
          {t(
            "Шаблон — это отправная точка, а не рекомендация. Историческая доходность ещё не измерена для вашей конфигурации.",
            "A template is a starting point, not a recommendation. Performance has not been measured for your configuration.",
          )}
        </p>
        <Badge tone="ice">
          {t("Без программирования", "No code required")}
        </Badge>
      </div>
      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorPanel message={error} retry={reload} />
      ) : (
        <div className="template-grid">
          {data?.map((template, i) => (
            <button
              data-testid={`template-${template.id}`}
              className="template-card"
              key={template.id}
              disabled={!!busy}
              onClick={() => void create(template)}
            >
              <div className="template-card-top">
                <span className={`template-icon tone-${i % 3}`}>
                  {i === 0 ? (
                    <GitBranch size={27} />
                  ) : i === 1 ? (
                    <Activity size={27} />
                  ) : i === 2 ? (
                    <TrendingUp size={27} />
                  ) : i === 3 ? (
                    <CircleDollarSign size={27} />
                  ) : (
                    <ShieldCheck size={27} />
                  )}
                </span>
                <span className="mono">0{i + 1}</span>
              </div>
              <h2>{template.name[locale]}</h2>
              <p>{template.description[locale]}</p>
              <div className="template-graph" aria-hidden="true">
                <span>DATA</span>
                <i />
                <span>{i < 3 ? "SIGNAL" : "RULE"}</span>
                <i />
                <span>ACTION</span>
              </div>
              <div className="template-card-foot">
                <span>
                  {template.spec.nodes.length} {t("узлов", "nodes")} ·{" "}
                  {template.spec.timeframe}
                </span>
                <span>
                  {busy === template.id
                    ? t("Создаём…", "Creating…")
                    : t("Открыть шаблон", "Open template")}
                  <ArrowUpRight size={16} />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
      <Notice>
        {t(
          "Сначала сохраните правила, затем выберите набор данных и издержки. Результаты привязаны к неизменяемой версии стратегии.",
          "Save the rules, then choose data and costs. Results are linked to an immutable strategy version.",
        )}
      </Notice>
    </>
  );
}
