import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api, patch, post, type Locale, type User } from "./api";

type AppContextType = {
  user: User | null;
  ready: boolean;
  locale: Locale;
  theme: string;
  timezone: string;
  t: (ru: string, en: string) => string;
  setLocale: (v: Locale) => void;
  setTheme: (v: string) => void;
  setTimezone: (v: string) => void;
  authenticate: (path: string, body?: unknown) => Promise<User>;
  logout: () => Promise<void>;
  updateProfile: (body: Record<string, unknown>) => Promise<void>;
  format: (value: number | null | undefined, digits?: number) => string;
  date: (value: string, includeTime?: boolean) => string;
  notify: (message: string, error?: boolean) => void;
};
const Context = createContext<AppContextType>(null!);
export const useApp = () => useContext(Context);
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false);
  const [locale, setLocaleState] = useState<Locale>(
    (localStorage.getItem("kedr-locale") as Locale) || "ru",
  );
  const [theme, setThemeState] = useState(
    localStorage.getItem("kedr-theme") || "dark",
  );
  const [timezone, setTimezoneState] = useState(
    localStorage.getItem("kedr-timezone") || "UTC",
  );
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  useEffect(() => {
    api("/auth/me")
      .then((data) => {
        setUser(data.user);
        if (data.user.locale) setLocaleState(data.user.locale);
        if (data.user.theme) setThemeState(data.user.theme);
        if (data.user.timezone) setTimezoneState(data.user.timezone);
      })
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("kedr-theme", theme);
  }, [theme]);
  useEffect(() => {
    document.documentElement.lang = locale;
    localStorage.setItem("kedr-locale", locale);
  }, [locale]);
  useEffect(() => {
    localStorage.setItem("kedr-timezone", timezone);
  }, [timezone]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 4800);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  const savePreference = (body: Record<string, unknown>) => {
    if (user)
      patch("/profile", body)
        .then((data) => setUser(data.user || data))
        .catch(() => {});
  };
  const translate = useCallback(
    (ru: string, en: string) => (locale === "ru" ? ru : en),
    [locale],
  );
  const formatNumber = useCallback(
    (v: number | null | undefined, digits = 2) =>
      v == null || !Number.isFinite(v)
        ? "—"
        : new Intl.NumberFormat(locale === "ru" ? "ru-RU" : "en-US", {
            maximumFractionDigits: digits,
            minimumFractionDigits: digits,
          }).format(v),
    [locale],
  );
  const formatDate = useCallback(
    (v: string, includeTime = false) => {
      try {
        return new Intl.DateTimeFormat(locale === "ru" ? "ru-RU" : "en-GB", {
          timeZone: timezone,
          day: "2-digit",
          month: "short",
          year: "numeric",
          ...(includeTime ? { hour: "2-digit", minute: "2-digit" } : {}),
        }).format(new Date(v));
      } catch {
        return v;
      }
    },
    [locale, timezone],
  );
  const notify = useCallback(
    (message: string, error = false) => setToast({ message, error }),
    [],
  );
  const value: AppContextType = {
    user,
    ready,
    locale,
    theme,
    timezone,
    t: translate,
    setLocale: (v) => {
      setLocaleState(v);
      savePreference({ locale: v });
    },
    setTheme: (v) => {
      setThemeState(v);
      savePreference({ theme: v });
    },
    setTimezone: (v) => {
      setTimezoneState(v);
      savePreference({ timezone: v });
    },
    authenticate: async (path, body = {}) => {
      const data = await post(path, body);
      let profile = data.user;
      if (path.endsWith("/login")) {
        setLocaleState(profile.locale || "ru");
        setThemeState(profile.theme || "dark");
        setTimezoneState(profile.timezone || "UTC");
      } else {
        profile = await patch("/profile", { locale, theme, timezone });
      }
      setUser(profile);
      return profile;
    },
    logout: async () => {
      await post("/auth/logout");
      setUser(null);
    },
    updateProfile: async (body) => {
      const data = await patch("/profile", body);
      setUser(data.user || data);
    },
    format: formatNumber,
    date: formatDate,
    notify,
  };
  return (
    <Context.Provider value={value}>
      {children}
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          <span className="status-dot" />
          {toast.message}
          <button onClick={() => setToast(null)} aria-label="Close">
            ×
          </button>
        </div>
      )}
    </Context.Provider>
  );
}
