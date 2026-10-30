import { useEffect, useState } from "react";
import {
  Bot,
  CornerDownLeft,
  FileCheck2,
  History,
  Send,
  ShieldCheck,
  Sparkles,
  Undo2,
  X,
} from "lucide-react";
import { api, post, type Spec } from "./api";
import { Badge, Notice, Spinner, useLoad } from "./components";
import { useApp } from "./context";

type Message = {
  id: string;
  role: string;
  content: string;
  mode: string;
  evidence?: { path: string; value: unknown }[];
  created_at: string;
};
type Proposal = {
  id: string;
  status: string;
  before_spec_hash: string;
  spec: Spec;
  diff: Record<string, unknown>;
  validation: { valid: boolean; errors: unknown[] };
  created_at: string;
};
type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  proposals: Proposal[];
};
export default function Copilot({
  strategyId,
  runId,
  tradeIndex,
  onApplied,
  onClose,
}: {
  strategyId: string;
  runId?: string;
  tradeIndex?: number;
  onApplied?: (spec: Spec) => void;
  onClose?: () => void;
}) {
  const { t, locale, notify } = useApp();
  const status = useLoad(() =>
    api<{
      status: string;
      configured: boolean;
      provider: string;
      model: string;
      limits: Record<string, unknown>;
      setup: string | Record<string, unknown>;
    }>("/copilot/status"),
  );
  const [conversationId, setConversationId] = useState(""),
    [conversation, setConversation] = useState<Conversation | null>(null),
    [history, setHistory] = useState<{ id: string; title: string }[]>([]),
    [input, setInput] = useState(""),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [historyOpen, setHistoryOpen] = useState(false);
  useEffect(() => {
    let active = true;
    api<{ id: string; title: string }[]>(
      `/strategies/${strategyId}/conversations`,
    )
      .then((v) => {
        if (active) setHistory(v);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [strategyId]);
  const refresh = async (id: string) => {
    setConversation(await api<Conversation>(`/copilot/conversations/${id}`));
  };
  const open = async (id: string) => {
    setConversationId(id);
    setBusy(true);
    setError("");
    try {
      await refresh(id);
      setHistoryOpen(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const send = async () => {
    if (!input.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      let id = conversationId;
      if (!id) {
        const created = await post<{ id: string }>(
          `/strategies/${strategyId}/conversations`,
          { title: input.slice(0, 80), locale },
        );
        id = created.id;
        setConversationId(id);
        setHistory((v) => [{ id, title: input.slice(0, 80) }, ...v]);
      }
      await post(`/copilot/conversations/${id}/messages`, {
        message: input,
        consent_external: consent,
        ...(runId ? { run_id: runId } : {}),
        ...(tradeIndex != null ? { trade_index: tradeIndex } : {}),
      });
      setInput("");
      await refresh(id);
    } catch (e: any) {
      setError(e.message);
      if (conversationId) await refresh(conversationId).catch(() => {});
    } finally {
      setBusy(false);
    }
  };
  const approve = async (proposal: Proposal, rollback = false) => {
    setBusy(true);
    setError("");
    try {
      const strategy = await api<{ spec: Spec; spec_hash: string }>(
        `/strategies/${strategyId}`,
      );
      const expected = strategy.spec_hash;
      const next = await post<{ spec: Spec }>(
        `/copilot/proposals/${proposal.id}/${rollback ? "rollback" : "approve"}`,
        { expected_spec_hash: expected },
      );
      onApplied?.(next.spec);
      await refresh(conversationId);
      notify(
        rollback
          ? t(
              "Изменение откачено новой версией",
              "Change rolled back as a new version",
            )
          : t(
              "Предложение применено после вашего подтверждения",
              "Proposal applied after your approval",
            ),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const configured = status.data?.configured === true;
  const suggestions = [
    t("Объясни правила этой стратегии", "Explain this strategy’s rules"),
    t(
      "Какие данные нужны для проверки?",
      "What data are required to test this?",
    ),
    ...(runId
      ? [
          t(
            "Объясни измеренные результаты и ограничения",
            "Explain measured results and limitations",
          ),
        ]
      : [t("Создай стратегию EMA и RSI", "Create an EMA and RSI strategy")]),
  ];
  return (
    <section className="copilot-panel" data-testid="copilot-panel">
      <div className="copilot-head">
        <div>
          <span className="assistant-mark">
            <Sparkles size={19} />
          </span>
          <div>
            <b>{t("Исследовать вместе", "Research together")}</b>
            <small>
              {configured
                ? `${status.data?.provider} · ${status.data?.model}`
                : t(
                    "Детерминированный офлайн-разбор",
                    "Deterministic offline explanation",
                  )}
            </small>
          </div>
        </div>
        <div>
          <button
            className="icon-btn"
            aria-label={t("История разговоров", "Conversation history")}
            onClick={() => setHistoryOpen(!historyOpen)}
          >
            <History size={16} />
          </button>
          {onClose && (
            <button
              className="icon-btn"
              aria-label={t("Закрыть помощника", "Close assistant")}
              onClick={onClose}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>
      {historyOpen && (
        <div className="copilot-history">
          <button
            className="text-button"
            onClick={() => {
              setConversationId("");
              setConversation(null);
              setHistoryOpen(false);
            }}
          >
            {t("Новый разговор", "New conversation")}
          </button>
          {history.map((c) => (
            <button key={c.id} onClick={() => void open(c.id)}>
              {c.title}
            </button>
          ))}
        </div>
      )}
      {!configured && (
        <div className="copilot-availability">
          <Bot size={18} />
          <div>
            <b>
              {t(
                "Генеративный AI не подключён",
                "Generative AI is disconnected",
              )}
            </b>
            <p>
              {t(
                "Офлайн-помощник объясняет сохранённые правила и измеренные результаты. Он не генерирует правки и не притворяется внешней моделью.",
                "The offline helper explains saved rules and measured results. It does not generate edits or impersonate an external model.",
              )}
            </p>
            <details>
              <summary>
                {t("Как подключить провайдера", "Provider setup")}
              </summary>
              <pre>
                {typeof status.data?.setup === "string"
                  ? status.data.setup
                  : JSON.stringify(
                      status.data?.setup || {
                        KEDR_AI_PROVIDER: "openai",
                        KEDR_AI_MODEL: "configure server-side",
                        KEDR_AI_API_KEY: "server secret",
                      },
                      null,
                      2,
                    )}
              </pre>
            </details>
          </div>
        </div>
      )}
      <div className="copilot-messages" aria-live="polite">
        {!conversation?.messages?.length ? (
          <div className="copilot-welcome">
            <Sparkles size={31} strokeWidth={1.2} />
            <h3>
              {t(
                "От идеи — к проверяемым правилам",
                "From an idea to testable rules",
              )}
            </h3>
            <p>
              {t(
                "Обсудите гипотезу, входы, издержки и слабые места. Изменения требуют отдельного одобрения.",
                "Discuss the hypothesis, inputs, costs and weaknesses. Changes require separate approval.",
              )}
            </p>
            {suggestions.map((s) => (
              <button key={s} onClick={() => setInput(s)}>
                {s}
                <CornerDownLeft size={13} />
              </button>
            ))}
          </div>
        ) : (
          conversation.messages.map((m) => (
            <article key={m.id} className={`conversation-message ${m.role}`}>
              <div>
                <b>
                  {m.role === "user"
                    ? t("Вы", "You")
                    : m.mode === "external_ai"
                      ? t("AI-провайдер", "AI provider")
                      : t("Офлайн-правила", "Offline rules")}
                </b>
                <Badge>{m.mode}</Badge>
              </div>
              <p>{m.content}</p>
              {!!m.evidence?.length && (
                <details>
                  <summary>
                    {t(
                      "Ссылки на измеренные значения",
                      "Measured evidence references",
                    )}
                  </summary>
                  {m.evidence.map((e, i) => (
                    <div className="evidence-reference" key={i}>
                      <code>{e.path}</code>
                      <span>
                        {typeof e.value === "object"
                          ? JSON.stringify(e.value)
                          : String(e.value)}
                      </span>
                    </div>
                  ))}
                </details>
              )}
            </article>
          ))
        )}
        {conversation?.proposals?.map((p) => (
          <article
            key={p.id}
            className="proposal-card"
            data-testid="ai-proposal"
          >
            <div className="panel-head">
              <h3>
                <FileCheck2 size={16} />
                {t("Предложение изменений", "Proposed changes")}
              </h3>
              <Badge tone={p.validation?.valid ? "mint" : "amber"}>
                {p.status}
              </Badge>
            </div>
            <p>
              {t(
                "Сначала проверьте разницу. Применение создаст сохранённую версию; автоматической торговли нет.",
                "Review the diff first. Approval creates a saved version; no trading is activated.",
              )}
            </p>
            <pre className="json-block">{JSON.stringify(p.diff, null, 2)}</pre>
            <details>
              <summary>
                {t(
                  "Полная предложенная схема",
                  "Complete proposed specification",
                )}
              </summary>
              <pre className="json-block">
                {JSON.stringify(p.spec, null, 2)}
              </pre>
            </details>
            {!p.validation?.valid && (
              <Notice>{JSON.stringify(p.validation?.errors)}</Notice>
            )}
            {p.status === "pending" && (
              <button
                className="btn primary full"
                data-testid="approve-ai-proposal"
                disabled={busy || !p.validation?.valid}
                onClick={() => void approve(p)}
              >
                <FileCheck2 size={14} />
                {t("Одобрить и применить", "Approve and apply")}
              </button>
            )}
            {p.status === "approved" && (
              <button
                className="btn secondary full"
                disabled={busy}
                onClick={() => void approve(p, true)}
              >
                <Undo2 size={14} />
                {t("Откатить новой версией", "Rollback as a new version")}
              </button>
            )}
          </article>
        ))}
        {busy && (
          <Spinner
            label={t(
              "Обрабатываем ограниченный запрос…",
              "Processing bounded request…",
            )}
          />
        )}
      </div>
      <div className="copilot-compose">
        {configured && (
          <label className="checkbox-label consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            {t(
              "Разрешаю отправить контекст этой стратегии внешнему AI. Ключи и другие стратегии не включаются.",
              "I consent to send this strategy context to external AI. Keys and other strategies are excluded.",
            )}
          </label>
        )}
        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
        <textarea
          data-testid="copilot-message"
          aria-label={t("Сообщение помощнику", "Message the assistant")}
          placeholder={t(
            "Обсудить идею или задать вопрос…",
            "Discuss an idea or ask a question…",
          )}
          maxLength={4000}
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div>
          <small>
            <ShieldCheck size={11} />
            {t(
              "Только разрешённый контекст · Ctrl + Enter",
              "Authorized context only · Ctrl + Enter",
            )}
          </small>
          <button
            className="btn primary"
            data-testid="send-copilot"
            disabled={!input.trim() || busy || (configured && !consent)}
            onClick={() => void send()}
          >
            <Send size={14} />
            {t("Отправить", "Send")}
          </button>
        </div>
      </div>
    </section>
  );
}
