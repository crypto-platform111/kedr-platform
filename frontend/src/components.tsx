import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronRight,
  CircleHelp,
  LoaderCircle,
  X,
} from "lucide-react";
import { useApp } from "./context";

export function useLoad<T>(loader: () => Promise<T>, key: unknown = "") {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [revision, setRevision] = useState(0);
  const loaderRef = useRef(loader);
  const dependencyKey = JSON.stringify(key);
  useEffect(() => {
    loaderRef.current = loader;
  }, [loader]);
  // A fetch-key change intentionally resets the async resource's loading/error state.
  // The explicit serialized key, not an inline loader's identity, defines resource identity.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    loaderRef
      .current()
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [dependencyKey, revision]);
  /* eslint-enable react-hooks/set-state-in-effect */
  return {
    data,
    error,
    loading,
    reload: () => setRevision((v) => v + 1),
    setData,
  };
}
export function Spinner({ label }: { label?: string }) {
  const { t } = useApp();
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={23} />
      <span>
        {label || t("Загружаем рабочее пространство…", "Loading workspace…")}
      </span>
    </div>
  );
}
export function ErrorPanel({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  const { t } = useApp();
  return (
    <div className="error-panel" role="alert">
      <AlertTriangle size={22} />
      <div>
        <strong>
          {t(
            "Не удалось завершить запрос",
            "The request could not be completed",
          )}
        </strong>
        <p>{message}</p>
      </div>
      {retry && (
        <button className="btn secondary" onClick={retry}>
          {t("Повторить", "Try again")}
        </button>
      )}
    </div>
  );
}
export function Empty({
  icon: Icon = CircleHelp,
  title,
  text,
  action,
  to,
}: {
  icon?: React.ElementType;
  title: string;
  text: string;
  action?: string;
  to?: string;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={29} strokeWidth={1.5} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && to && (
        <Link className="btn primary" to={to}>
          {action}
          <ArrowRight size={16} />
        </Link>
      )}
    </div>
  );
}
export function Badge({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function SourceBadge({ type }: { type?: string }) {
  const { t } = useApp();
  return (
    <Badge
      tone={
        type === "verified_historical"
          ? "ice"
          : type === "synthetic_demo"
            ? "amber"
            : ""
      }
    >
      {type === "verified_historical"
        ? t("Исторический архив", "Historical archive")
        : type === "synthetic_demo"
          ? t("Синтетическое демо", "Synthetic demo")
          : t("Источник не определён", "Source not established")}
    </Badge>
  );
}
export function PageHead({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="head-actions">{actions}</div>}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const { t } = useApp();
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () =>
      Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]',
        ) || [],
      ).filter((el) => el.getClientRects().length > 0);
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      }
      if (e.key === "Tab") {
        const elements = focusable();
        const first = elements[0],
          last = elements[elements.length - 1];
        if (!first) {
          e.preventDefault();
          dialog.current?.focus();
        } else if (
          e.shiftKey &&
          (document.activeElement === first ||
            !dialog.current?.contains(document.activeElement))
        ) {
          e.preventDefault();
          last.focus();
        } else if (
          !e.shiftKey &&
          (document.activeElement === last ||
            !dialog.current?.contains(document.activeElement))
        ) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", f);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    focusable()[0]?.focus();
    return () => {
      document.removeEventListener("keydown", f);
      document.body.style.overflow = old;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialog}
        tabIndex={-1}
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button
            className="icon-btn"
            onClick={onClose}
            aria-label={t("Закрыть", "Close")}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
export function Notice({
  children,
  tone = "",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      <CircleHelp size={17} />
      <div>{children}</div>
    </div>
  );
}
export function Metric({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong
        className={
          positive === undefined ? "" : positive ? "positive" : "negative"
        }
      >
        {value}
      </strong>
      {sub && <small>{sub}</small>}
    </div>
  );
}
export function Steps({ active = 1 }: { active?: number }) {
  const { t } = useApp();
  return (
    <div className="steps">
      {[
        [
          t("Идея", "Idea"),
          t("Шаблон или своя логика", "A template or your own logic"),
        ],
        [t("Проверка", "Test"), t("История и издержки", "History and costs")],
        [
          t("Исследование", "Research"),
          t("Результат и ограничения", "Results and limitations"),
        ],
      ].map(([title, description], i) => (
        <React.Fragment key={title}>
          <div className={i + 1 <= active ? "active" : ""}>
            <b>{i + 1 < active ? <Check size={14} /> : `0${i + 1}`}</b>
            <span>
              <strong>{title}</strong>
              <small>{description}</small>
            </span>
          </div>
          {i < 2 && <ChevronRight size={15} />}
        </React.Fragment>
      ))}
    </div>
  );
}
