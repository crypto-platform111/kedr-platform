import { lazy, Suspense, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  Check,
  ChevronDown,
  CircleHelp,
  Compass,
  FlaskConical,
  GitBranch,
  Globe2,
  Layers3,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Network,
  Plus,
  Radio,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Terminal,
  Trees,
  Users,
  X,
} from "lucide-react";
import { brand } from "./api";
import { useApp } from "./context";
import { Badge, Modal, Spinner } from "./components";
import {
  AuthPage,
  Dashboard,
  LandingPage,
  NewStrategy,
  Onboarding,
} from "./home";
const Builder = lazy(() => import("./builder"));
const Results = lazy(() => import("./results"));
const MarketTerminal = lazy(() => import("./charting"));
const MLResearch = lazy(() => import("./mlResearch"));
const ComparisonWorkspace = lazy(() => import("./researchWorkspace"));
import { CommandPalette } from "./researchWorkspace";
import {
  Analyst,
  Bots,
  Community,
  Intelligence,
  Integrations,
  MLStudio,
  Settings,
} from "./extensions";

export function Brand({ compact = false }: { compact?: boolean }) {
  const { locale, t } = useApp();
  return (
    <Link
      className="brand"
      to="/"
      aria-label={t("КЕДР — главная", "KEDR — home")}
    >
      <span className="brand-mark">
        <Trees size={23} strokeWidth={1.6} />
      </span>
      <span>
        <strong>{brand.name[locale]}</strong>
        {!compact && <small>{brand.tagline[locale]}</small>}
      </span>
    </Link>
  );
}
export function LocaleToggle() {
  const { locale, setLocale, t } = useApp();
  return (
    <button
      data-testid="locale-switch"
      className="locale-btn"
      onClick={() => setLocale(locale === "ru" ? "en" : "ru")}
      aria-label={t("Switch to English", "Переключить на русский")}
    >
      <Globe2 size={14} />
      {locale.toUpperCase()}
    </button>
  );
}
export function ThemeToggle() {
  const { theme, setTheme, t } = useApp();
  return (
    <button
      className="icon-btn"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      aria-label={t("Переключить тему", "Switch theme")}
    >
      {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
    </button>
  );
}
function Shell() {
  const { user, ready, t, logout } = useApp();
  const [mobile, setMobile] = useState(false),
    [glossary, setGlossary] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  if (!ready) return <Spinner />;
  if (!user)
    return <Navigate to="/auth" replace state={{ from: location.pathname }} />;
  const groups = [
    {
      label: t("РАБОЧЕЕ ПРОСТРАНСТВО", "WORKSPACE"),
      links: [
        ["/dashboard", LayoutDashboard, t("Обзор", "Overview")],
        ["/new", Network, t("Конструктор стратегий", "Strategy designer")],
        ["/analyst", Sparkles, t("Исследователь", "Research analyst")],
        ["/ml", FlaskConical, "ML Studio"],
        ["/compare", Layers3, t("Сравнение тестов","Compare runs")],
      ],
    },
    {
      label: t("РЫНОК И СООБЩЕСТВО", "MARKET & COMMUNITY"),
      links: [
        ["/market", Activity, t("Рыночный терминал","Market terminal")],
        [
          "/intelligence",
          AudioLines,
          t("Криптоинтеллект", "Coin intelligence"),
        ],
        ["/community", Users, t("Библиотека сообщества", "Community library")],
        ["/bots", Radio, t("Мои боты", "My bots")],
      ],
    },
  ];
  return (
    <div className="app-shell">
      <button
        className={`sidebar-shade ${mobile ? "visible" : ""}`}
        aria-label={t("Закрыть меню", "Close navigation")}
        onClick={() => setMobile(false)}
      />
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <div className="side-brand">
          <Brand />
          <button
            className="icon-btn mobile-close"
            onClick={() => setMobile(false)}
            aria-label={t("Закрыть", "Close")}
          >
            <X size={19} />
          </button>
        </div>
        <div className="workspace-pill">
          <span className="workspace-avatar">K</span>
          <div>
            <b>{t("Личное пространство", "Personal workspace")}</b>
            <span>
              {user.is_demo
                ? t("Локальная демо-сессия", "Local demo session")
                : t("Индивидуальный аккаунт", "Personal account")}
            </span>
          </div>
          <ChevronDown size={14} />
        </div>
        <nav>
          {groups.map((group) => (
            <div className="nav-group" key={group.label}>
              <div className="nav-label">{group.label}</div>
              {group.links.map(([href, Icon, label]) => (
                <NavLink
                  key={String(href)}
                  to={String(href)}
                  onClick={() => setMobile(false)}
                  className={({ isActive }) =>
                    `nav-link ${isActive || (href === "/new" && location.pathname.startsWith("/builder")) ? "active" : ""}`
                  }
                >
                  {(() => {
                    const I = Icon as typeof Network;
                    return <I size={18} strokeWidth={1.6} />;
                  })()}
                  <span>{String(label)}</span>
                  {href === "/ml" && <small>β</small>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="research-card">
            <div>
              <ShieldCheck size={17} />
              <b>{t("Сначала исследование", "Research comes first")}</b>
            </div>
            <p>
              {t(
                "Каждая идея заслуживает честной проверки.",
                "Every idea deserves an honest test.",
              )}
            </p>
            <button onClick={() => setGlossary(true)}>
              {t("Краткий словарь", "Quick glossary")}
              <ArrowUpRight size={14} />
            </button>
          </div>
          <NavLink
            to="/integrations"
            className="nav-link"
            onClick={() => setMobile(false)}
          >
            <Layers3 size={17} />
            {t("Интеграции", "Integrations")}
            <span className="status-dot small" />
          </NavLink>
          <NavLink
            to="/settings"
            className="nav-link"
            onClick={() => setMobile(false)}
          >
            <Settings2 size={17} />
            {t("Настройки", "Settings")}
          </NavLink>
          <div className="profile">
            <span className="avatar">
              {(user.name || "K").slice(0, 1).toUpperCase()}
            </span>
            <div>
              <b>{user.name}</b>
              <span>
                {user.is_demo ? t("Демо-профиль", "Demo profile") : user.email}
              </span>
            </div>
            <button
              className="icon-btn"
              aria-label={t("Выйти", "Log out")}
              onClick={async () => {
                await logout();
                navigate("/");
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              data-testid="mobile-menu"
              className="icon-btn mobile-menu"
              aria-label={t("Открыть меню", "Open navigation")}
              onClick={() => setMobile(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb">
              {t("Рабочее пространство", "Workspace")}
              <span>/</span>
              <b>
                {location.pathname.startsWith("/builder")
                  ? t("Редактор стратегии", "Strategy editor")
                  : location.pathname.startsWith("/backtests")
                    ? t("Результат тестирования", "Backtest result")
                    : t("Исследования", "Research")}
              </b>
            </span>
          </div>
          <div className="topbar-actions">
            <CommandPalette/>
            <span className="local-status">
              <span className="status-dot" />
              {t("Локальная среда", "Local environment")}
            </span>
            <LocaleToggle />
            <ThemeToggle />
            <button
              className="icon-btn"
              aria-label={t("Открыть словарь", "Open glossary")}
              onClick={() => setGlossary(true)}
            >
              <CircleHelp size={17} />
            </button>
          </div>
        </header>
        <main className="page-content">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>
            © {new Date().getFullYear()} {brand.name.en}{" "}
            <span className="muted">/</span>{" "}
            {t("Среда исследования стратегий", "Strategy research environment")}
          </span>
          <span>
            <span className="status-dot small" />
            {t("Торговля на бирже отключена", "Exchange execution disabled")}
            <code>v0.2</code>
          </span>
        </footer>
      </div>
      {glossary && (
        <Modal
          title={t(
            "Исследовать — значит понимать",
            "Research means understanding",
          )}
          onClose={() => setGlossary(false)}
        >
          <div className="glossary">
            {[
              [
                t("Бэктест", "Backtest"),
                t(
                  "Проверка правил на исторических ценах с заданными издержками. Это симуляция, а не результат реальной торговли.",
                  "A simulation of rules on historical prices with stated costs, not actual trading performance.",
                ),
              ],
              [
                t("Просадка", "Drawdown"),
                t(
                  "Падение стоимости от достигнутого максимума. Показывает, какой временный убыток пришлось бы пережить.",
                  "The fall in equity from a previous peak. It shows the temporary loss experienced along the way.",
                ),
              ],
              [
                "Sharpe",
                t(
                  "Средняя доходность относительно изменчивости результата. При малом числе наблюдений показатель ненадёжен.",
                  "Average return relative to variability. It is unreliable with a small sample.",
                ),
              ],
              [
                t("Независимая проверка", "Independent evaluation"),
                t(
                  "Проверка на данных, которые не использовались при выборе правил и параметров. Здесь исторические тесты не считаются независимым подтверждением.",
                  "Evaluation on data never used to choose rules or parameters. Historical tests here are not independent confirmation.",
                ),
              ],
            ].map(([term, body]) => (
              <div key={term}>
                <h3>{term}</h3>
                <p>{body}</p>
              </div>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/auth" element={<AuthPage />} />
        <Route element={<Shell />}>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/new" element={<NewStrategy />} />
          <Route path="/builder/:id" element={<Builder />} />
          <Route path="/backtests/:id" element={<Results />} />
          <Route path="/analyst" element={<Analyst />} />
          <Route path="/analyst/:id" element={<Analyst />} />
          <Route path="/ml" element={<MLResearch />} />
          <Route path="/market" element={<MarketTerminal />} />
          <Route path="/compare" element={<ComparisonWorkspace />} />
          <Route path="/intelligence" element={<Intelligence />} />
          <Route path="/community" element={<Community />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
