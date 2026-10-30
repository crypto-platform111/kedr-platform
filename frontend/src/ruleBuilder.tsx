import { useMemo, useState } from "react";
import {
  ArrowRight,
  Check,
  FileCheck2,
  GitBranch,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { type CatalogNode, type Spec, type SpecNode } from "./api";
import { Badge, Modal, Notice } from "./components";
import { useApp } from "./context";

export function summarizeSpec(
  spec: Spec,
  catalog: CatalogNode[],
  locale: "ru" | "en",
): string[] {
  const byId = new Map(spec.nodes.map((n) => [n.id, n]));
  const defs = new Map(catalog.map((n) => [n.type, n]));
  const ru = locale === "ru";
  const describe = (id: string, seen = new Set<string>()): string => {
    if (seen.has(id)) return "…";
    seen.add(id);
    const n = byId.get(id);
    if (!n) return "?";
    const input = (port = "input") => {
      const e = spec.edges.find(
        (e) => e.target === id && (e.targetHandle || "input") === port,
      );
      return e
        ? describe(e.source, new Set(seen))
        : ru
          ? "[не подключено]"
          : "[not connected]";
    };
    const name = defs.get(n.type)?.name[locale] || n.type;
    if (n.type === "price") return String(n.params.field || "close");
    if (n.type === "constant") return String(n.params.value);
    if (["volume", "trade_count", "calendar"].includes(n.type))
      return `${name}${n.params.field ? ` (${n.params.field})` : ""}`;
    if (
      [
        "gt",
        "lt",
        "gte",
        "lte",
        "eq",
        "approximately_equal",
        "cross_above",
        "cross_below",
      ].includes(n.type)
    ) {
      const operator: Record<string, string> = {
        gt: ">",
        lt: "<",
        gte: "≥",
        lte: "≤",
        eq: "=",
        approximately_equal: "≈",
        cross_above: ru ? "пересекает вверх" : "crosses above",
        cross_below: ru ? "пересекает вниз" : "crosses below",
      };
      return `${input("a")} ${operator[n.type]} ${input("b")}`;
    }
    if (n.type === "and" || n.type === "or")
      return `(${input("a")}) ${n.type === "and" ? (ru ? "И" : "AND") : ru ? "ИЛИ" : "OR"} (${input("b")})`;
    if (n.type === "not") return `${ru ? "НЕ" : "NOT"} (${input()})`;
    if (n.type === "enter_long" || n.type === "exit_long")
      return `${ru ? (n.type === "enter_long" ? "Войти в long, когда" : "Выйти в cash, когда") : n.type === "enter_long" ? "Enter long when" : "Exit to cash when"} ${input()}`;
    if (n.type === "hold_cash") return ru ? "Остаться в деньгах" : "Hold cash";
    return `${name}${n.params.period ? `(${n.params.period})` : ""}${Object.keys(defs.get(n.type)?.inputs || {}).length ? ` [${input()}]` : ""}`;
  };
  const result = spec.nodes
    .filter((n) => ["enter_long", "exit_long", "hold_cash"].includes(n.type))
    .map((n) => describe(n.id));
  if (!result.length)
    result.push(
      ru
        ? "Действие пока не задано. Черновик можно сохранить, но тест требует завершённых правил."
        : "No action yet. The draft can be saved; a backtest requires complete rules.",
    );
  result.push(
    `${ru ? "Доля при входе" : "Entry allocation"}: ${Number(spec.risk.max_exposure) * 100}%${spec.risk.stop_loss_pct ? ` · stop ${spec.risk.stop_loss_pct}%` : ""}${spec.risk.take_profit_pct ? ` · take ${spec.risk.take_profit_pct}%` : ""}`,
  );
  return result;
}
export function RuleSummary({
  spec,
  catalog,
}: {
  spec: Spec;
  catalog: CatalogNode[];
}) {
  const { t, locale } = useApp();
  const rules = useMemo(
    () => summarizeSpec(spec, catalog, locale),
    [spec, catalog, locale],
  );
  return (
    <details className="rule-summary" open>
      <summary>
        <FileCheck2 size={15} />
        {t("Правила человеческим языком", "Rules in plain language")}
        <Badge>SCHEMA {spec.schema_version}</Badge>
      </summary>
      <ol>
        {rules.map((r, i) => (
          <li key={i}>{r}</li>
        ))}
      </ol>
    </details>
  );
}
export function GuidedRuleBuilder({
  spec,
  onApply,
  onClose,
}: {
  spec: Spec;
  onApply: (s: Spec) => void;
  onClose: () => void;
}) {
  const { t } = useApp();
  const [kind, setKind] = useState("cross"),
    [average, setAverage] = useState("ema"),
    [fast, setFast] = useState(20),
    [slow, setSlow] = useState(60),
    [rsi, setRsi] = useState(false),
    [rsiThreshold, setRsiThreshold] = useState(70),
    [stop, setStop] = useState<number | "">(5),
    [take, setTake] = useState<number | "">(""),
    [fraction, setFraction] = useState(1),
    [review, setReview] = useState(false);
  const next = useMemo(() => {
    const nodes: SpecNode[] = [];
    const edges: Spec["edges"] = [];
    const add = (
      id: string,
      type: string,
      params: Record<string, unknown>,
      x: number,
      y: number,
    ) => nodes.push({ id, type, params, position: { x, y } });
    const link = (source: string, target: string, targetHandle = "input") =>
      edges.push({
        id: `${source}_${target}_${targetHandle}`,
        source,
        target,
        sourceHandle: "out",
        targetHandle,
      });
    add("price", "price", { field: "close" }, 40, 180);
    add("fast", average, { period: fast }, 250, 80);
    add("slow", average, { period: slow }, 250, 280);
    link("price", "fast");
    link("price", "slow");
    add(
      "entry_condition",
      kind === "cross" ? "cross_above" : "gt",
      {},
      480,
      100,
    );
    add(
      "exit_condition",
      kind === "cross" ? "cross_below" : "lt",
      {},
      480,
      300,
    );
    for (const condition of ["entry_condition", "exit_condition"]) {
      link("fast", condition, "a");
      link("slow", condition, "b");
    }
    let entry = "entry_condition";
    if (rsi) {
      add("rsi", "rsi", { period: 14 }, 250, 490);
      add("rsi_limit", "constant", { value: rsiThreshold }, 450, 600);
      add("rsi_filter", "lt", {}, 480, 480);
      link("price", "rsi");
      link("rsi", "rsi_filter", "a");
      link("rsi_limit", "rsi_filter", "b");
      add("combined", "and", {}, 700, 130);
      link("entry_condition", "combined", "a");
      link("rsi_filter", "combined", "b");
      entry = "combined";
    }
    add("entry", "enter_long", {}, rsi ? 920 : 730, 100);
    add("exit", "exit_long", {}, 730, 300);
    link(entry, "entry");
    link("exit_condition", "exit");
    return {
      ...spec,
      schema_version: 2 as const,
      nodes,
      edges,
      risk: {
        max_exposure: fraction,
        stop_loss_pct: stop === "" ? null : stop,
        take_profit_pct: take === "" ? null : take,
      },
    };
  }, [
    spec,
    kind,
    average,
    fast,
    slow,
    rsi,
    rsiThreshold,
    stop,
    take,
    fraction,
  ]);
  const invalid = fast >= slow || fast < 2 || slow > 500;
  return (
    <Modal
      title={t("Соберите правило без кода", "Build a rule without code")}
      onClose={onClose}
      wide
    >
      <div className="wizard-heading">
        <span className="assistant-mark">
          <GitBranch size={23} />
        </span>
        <div>
          <p>
            {t(
              "Мастер создаёт ту же схему, что и визуальный редактор. Здесь нет отдельного скрытого алгоритма.",
              "The wizard creates the same specification as the visual editor. There is no separate hidden algorithm.",
            )}
          </p>
          <Badge tone="ice">SCHEMA 2 · LONG / CASH</Badge>
        </div>
      </div>
      <div className="rule-wizard-grid">
        <section>
          <div className="wizard-step">
            <span>01</span>
            <h3>{t("Когда это происходит…", "When this happens…")}</h3>
          </div>
          <label>
            {t("Сигнал тренда", "Trend signal")}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="cross">
                {t(
                  "Быстрая средняя пересекает медленную вверх",
                  "Fast average crosses above the slow average",
                )}
              </option>
              <option value="above">
                {t(
                  "Быстрая средняя выше медленной",
                  "Fast average is above the slow average",
                )}
              </option>
            </select>
          </label>
          <div className="form-row">
            <label>
              {t("Тип средней", "Average type")}
              <select
                value={average}
                onChange={(e) => setAverage(e.target.value)}
              >
                <option value="ema">EMA</option>
                <option value="sma">SMA</option>
                <option value="wma">WMA</option>
              </select>
            </label>
            <label>
              {t("Быстрая, свечей", "Fast, bars")}
              <input
                data-testid="wizard-fast"
                type="number"
                min={2}
                max={499}
                value={fast}
                onChange={(e) => setFast(+e.target.value)}
              />
            </label>
            <label>
              {t("Медленная, свечей", "Slow, bars")}
              <input
                data-testid="wizard-slow"
                type="number"
                min={3}
                max={500}
                value={slow}
                onChange={(e) => setSlow(+e.target.value)}
              />
            </label>
          </div>
          <div className="wizard-step">
            <span>02</span>
            <h3>
              {t("И выполнены условия…", "And conditions are satisfied…")}
            </h3>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={rsi}
              onChange={(e) => setRsi(e.target.checked)}
            />
            {t("Добавить фильтр RSI(14)", "Add RSI(14) filter")}
          </label>
          {rsi && (
            <label>
              {t("RSI меньше", "RSI below")}
              <input
                type="number"
                min={1}
                max={99}
                value={rsiThreshold}
                onChange={(e) => setRsiThreshold(+e.target.value)}
              />
            </label>
          )}
          <p className="fine-print">
            {t(
              "Фильтр не является рекомендацией. Значения определяются до проверки результатов.",
              "The filter is not a recommendation. Set its values before examining results.",
            )}
          </p>
        </section>
        <section>
          <div className="wizard-step">
            <span>03</span>
            <h3>{t("Войти или выйти…", "Enter or exit…")}</h3>
          </div>
          <div className="wizard-action">
            <ArrowRight size={16} />
            {t(
              "Войти в long при сигнале. Выйти при обратном условии. Short не исполняется.",
              "Enter long on the signal. Exit on the reverse condition. Short execution is unavailable.",
            )}
          </div>
          <div className="wizard-step">
            <span>04</span>
            <h3>
              {t("С такими рамками риска…", "With these risk boundaries…")}
            </h3>
          </div>
          <label>
            {t("Доля капитала при входе, 0–1", "Entry capital fraction, 0–1")}
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={fraction}
              onChange={(e) => setFraction(+e.target.value)}
            />
          </label>
          <div className="form-row">
            <label>
              {t("Стоп-лосс, %", "Stop loss, %")}
              <input
                type="number"
                min={0.1}
                max={99}
                value={stop}
                placeholder={t("Не задан", "Not set")}
                onChange={(e) =>
                  setStop(e.target.value === "" ? "" : +e.target.value)
                }
              />
            </label>
            <label>
              {t("Тейк-профит, %", "Take profit, %")}
              <input
                type="number"
                min={0.1}
                max={100}
                value={take}
                placeholder={t("Не задан", "Not set")}
                onChange={(e) =>
                  setTake(e.target.value === "" ? "" : +e.target.value)
                }
              />
            </label>
          </div>
        </section>
      </div>
      {invalid && (
        <div className="inline-error">
          {t(
            "Быстрый период должен быть меньше медленного; диапазон 2–500 свечей.",
            "The fast period must be below the slow period; use 2–500 bars.",
          )}
        </div>
      )}
      <Notice>
        {t(
          "Применение заменит граф черновика этими явными правилами. Старые версии и тесты сохранятся. Для незавершённого или нового графа доступна отмена.",
          "Applying replaces the draft graph with these explicit rules. Saved versions and tests remain unchanged. Undo is available in the editor.",
        )}
      </Notice>
      {review && (
        <pre className="json-block wizard-preview" data-testid="wizard-preview">
          {JSON.stringify(next, null, 2)}
        </pre>
      )}
      <div className="modal-actions">
        <button className="btn secondary" onClick={() => setReview(!review)}>
          <Sparkles size={14} />
          {t("Предпросмотр схемы", "Preview specification")}
        </button>
        <button
          className="btn primary"
          data-testid="wizard-apply"
          disabled={invalid}
          onClick={() => {
            onApply(next);
            onClose();
          }}
        >
          <Check size={15} />
          {t("Применить правила к графу", "Apply rules to graph")}
        </button>
      </div>
    </Modal>
  );
}
