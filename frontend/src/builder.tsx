import { datasetIsAvailable, preferredDataset } from "./datasetSelection";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Copy,
  Database,
  FileJson,
  GitBranch,
  History,
  Info,
  Layers3,
  LockKeyhole,
  Maximize2,
  Network,
  Play,
  Plus,
  Redo2,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  Undo2,
  Waves,
  X,
} from "lucide-react";
import {
  api,
  post,
  put,
  type Dataset,
  type Spec,
  type SpecNode,
  type Strategy,
} from "./api";
import {
  Badge,
  ErrorPanel,
  Modal,
  Notice,
  SourceBadge,
  Spinner,
  useLoad,
} from "./components";
import { useApp } from "./context";
import { validationCopy } from "./researchCopy";
import { RuleSummary, GuidedRuleBuilder } from "./ruleBuilder";
import Copilot from "./copilot";

type CatalogNode = {
  type: string;
  category: string;
  output: string;
  inputs: Record<string, string>;
  name: { ru: string; en: string };
  params: Record<string, unknown>;
  available: boolean;
  status?: "executable" | "provider_required" | "preview" | "unsupported";
  availability_message?: {ru:string;en:string};
};
type GraphData = Record<string, unknown> & {
  item: SpecNode;
  definition?: CatalogNode;
  label: string;
  selected?: boolean;
  errors?: boolean;
};
const icons: Record<string, typeof Activity> = {
  price: Activity,
  volume: Database,
  sma: Waves,
  ema: Waves,
  gt: GitBranch,
  lt: GitBranch,
  and: GitBranch,
  or: GitBranch,
  enter_long: ArrowRight,
  exit_long: ArrowLeft,
  hold_cash: ShieldCheck,
  news_sentiment: Sparkles,
  ml_prediction: Sparkles,
};
const GraphNode = memo(({ data, selected }: NodeProps<Node<GraphData>>) => {
  const { t } = useApp();
  const Icon = icons[data.item.type] || Settings2;
  const ports = Object.keys(data.definition?.inputs || {});
  const unavailable = data.definition?.available === false;
  return (
    <div
      className={`graph-node ${selected ? "is-selected" : ""} ${data.errors ? "has-error" : ""} ${unavailable ? "unavailable" : ""} category-${data.definition?.category || "data"}`}
    >
      <div className="graph-node-heading">
        <span>
          <Icon size={15} />
        </span>
        <strong>{data.label}</strong>
        {unavailable && <LockKeyhole size={12} />}
      </div>
      <div className="graph-node-value">
        {Object.entries(data.item.params).length ? (
          Object.entries(data.item.params)
            .slice(0, 2)
            .map(([k, v]) => (
              <span key={k}>
                <small>{k}</small>
                <code>{String(v)}</code>
              </span>
            ))
        ) : (
          <span className="muted">
            {data.item.type === "price"
              ? "close"
              : data.definition?.output || t("Действие", "Action")}
          </span>
        )}
      </div>
      {ports.map((port, i) => (
        <Handle
          key={port}
          id={port}
          type="target"
          position={Position.Left}
          style={{ top: `${((i + 1) / (ports.length + 1)) * 100}%` }}
        >
          <span className="port-name">{port}</span>
        </Handle>
      ))}
      {data.definition?.output !== "action" && (
        <Handle type="source" id="out" position={Position.Right} />
      )}
    </div>
  );
});
const nodeTypes = { strategy: GraphNode };
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const categoryLabels: Record<string, [string, string]> = {
  market: ["Рыночные данные", "Market data"],
  data: ["Рыночные данные", "Market data"],
  indicators: ["Индикаторы", "Indicators"],
  indicator: ["Индикаторы", "Indicators"],
  logic: ["Логика", "Logic"],
  actions: ["Действия", "Actions"],
  action: ["Действия", "Actions"],
  risk: ["Управление риском", "Risk management"],
  future: ["Будущие интеграции", "Future integrations"],
  advanced: ["Будущие интеграции", "Future integrations"],
  microstructure: ["Микроструктура", "Microstructure"],
  derivatives: ["Деривативы", "Derivatives"],
  intelligence: ["Внешняя информация", "External intelligence"],
};

export default function Builder() {
  const { id = "" } = useParams();
  const { t, locale, notify, user, date, theme } = useApp();
  const navigate = useNavigate();
  const loaded = useLoad(
    () =>
      Promise.all([
        api<Strategy>(`/strategies/${id}`),
        api<CatalogNode[]>("/nodes"),
        api<Dataset[]>("/datasets"),
      ]),
    id,
  );
  const [spec, setSpec] = useState<Spec | null>(null),
    [name, setName] = useState(""),
    [selected, setSelected] = useState(""),
    [query, setQuery] = useState("");
  const [past, setPast] = useState<Spec[]>([]),
    [future, setFuture] = useState<Spec[]>([]),
    [saving, setSaving] = useState(false),
    [saveStatus, setSaveStatus] = useState("saved");
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: { node_id?: string; message: string; code: string }[];
    warnings: string[];
  } | null>(null);
  const [showRun, setShowRun] = useState(false),
    [showVersions, setShowVersions] = useState(false),
    [showJSON, setShowJSON] = useState(false),
    [showRisk, setShowRisk] = useState(false),
    [expert, setExpert] = useState(user?.level === "advanced");
  const [guidedOpen, setGuidedOpen] = useState(new URLSearchParams(window.location.search).get("mode")==="guided"), [copilotOpen, setCopilotOpen] = useState(new URLSearchParams(window.location.search).get("mode")==="ai");
  const canvasElement = useRef<HTMLDivElement>(null);
  const [versions, setVersions] = useState<any[]>([]),
    [versionBusy, setVersionBusy] = useState(false),
    [libraryOpen, setLibraryOpen] = useState(false);
  const flowInstance = useRef<{
    screenToFlowPosition: (point: { x: number; y: number }) => {
      x: number;
      y: number;
    };
  } | null>(null);
  const saved = useRef(""),
    latestSpec = useRef<Spec | null>(null);
  useEffect(() => {
    latestSpec.current = spec;
  }, [spec]);
  const catalog = useMemo(() => loaded.data?.[1] || [], [loaded.data]);
  const catalogMap = useMemo(
    () => Object.fromEntries(catalog.map((n) => [n.type, n])),
    [catalog],
  );
  // Hydrate the editable working copy once an async server strategy arrives.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (loaded.data) {
      const strategy = loaded.data[0];
      setSpec(clone(strategy.spec));
      setName(strategy.name);
      saved.current = JSON.stringify({
        spec: strategy.spec,
        name: strategy.name,
      });
      setPast([]);
      setFuture([]);
      setSelected("");
    }
  }, [loaded.data]);
  /* eslint-enable react-hooks/set-state-in-effect */
  const persist = useCallback(
    async (quiet = false) => {
      if (!latestSpec.current) return;
      setSaving(true);
      setSaveStatus("saving");
      const payload = { spec: latestSpec.current, name };
      try {
        await put(`/strategies/${id}`, payload);
        saved.current = JSON.stringify(payload);
        setSaveStatus("saved");
        if (!quiet) notify(t("Черновик сохранён", "Draft saved"));
      } catch (e: any) {
        setSaveStatus("error");
        if (!quiet) notify(e.message, true);
      } finally {
        setSaving(false);
      }
    },
    [id, name, t, notify],
  );
  // The autosave timer synchronizes the local draft with a server document.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!spec || JSON.stringify({ spec, name }) === saved.current) return;
    setSaveStatus("unsaved");
    const timer = setTimeout(() => void persist(true), 1300);
    return () => clearTimeout(timer);
  }, [spec, name, persist]);
  /* eslint-enable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!spec) return;
    let active = true;
    const timer = setTimeout(
      () =>
        post("/validate", { spec })
          .then((v) => {
            if (active) setValidation(v);
          })
          .catch((e) => {
            if (active)
              setValidation({
                valid: false,
                errors: [{ message: e.message, code: "REQUEST_FAILED" }],
                warnings: [],
              });
          }),
      400,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [spec]);
  const commit = (next: Spec) => {
    if (!spec) return;
    setPast((v) => [...v.slice(-39), clone(spec)]);
    setFuture([]);
    setSpec(next);
  };
  const undo = () => {
    if (!past.length || !spec) return;
    setFuture((v) => [clone(spec), ...v]);
    setSpec(past[past.length - 1]);
    setPast((v) => v.slice(0, -1));
  };
  const redo = () => {
    if (!future.length || !spec) return;
    setPast((v) => [...v, clone(spec)]);
    setSpec(future[0]);
    setFuture((v) => v.slice(1));
  };
  const addNode = (
    definition: CatalogNode,
    position?: { x: number; y: number },
  ) => {
    if (!spec) return;
    const node: SpecNode = {
      id: `${definition.type}_${crypto.randomUUID().slice(0, 12)}`,
      type: definition.type,
      params: clone(definition.params || {}),
      position: position || {
        x: 70 + (spec.nodes.length % 4) * 200,
        y: 60 + Math.floor(spec.nodes.length / 4) * 125,
      },
    };
    commit({ ...spec, nodes: [...spec.nodes, node] });
    setSelected(node.id);
    setLibraryOpen(false);
  };
  const canConnect = (connection: Connection | Edge) => {
    if (!spec || connection.source === connection.target) return false;
    const source = spec.nodes.find((n) => n.id === connection.source),
      target = spec.nodes.find((n) => n.id === connection.target);
    if (!source || !target) return false;
    const output = catalogMap[source.type]?.output,
      input = catalogMap[target.type]?.inputs?.[
        connection.targetHandle || "input"
      ]?.replace("?", "");
    if (
      !output ||
      !input ||
      (output !== input &&
        input !== "any" &&
        !(input === "number" && output === "series"))
    )
      return false;
    if (
      spec.edges.some(
        (e) =>
          e.target === connection.target &&
          e.targetHandle === connection.targetHandle,
      )
    )
      return false;
    const visited = new Set<string>();
    const reachesSource = (node: string): boolean => {
      if (node === connection.source) return true;
      if (visited.has(node)) return false;
      visited.add(node);
      return spec.edges
        .filter((e) => e.source === node)
        .some((e) => reachesSource(e.target));
    };
    return !reachesSource(connection.target);
  };
  const nodes: Node<GraphData>[] = useMemo(
    () =>
      spec?.nodes.map((n) => ({
        id: n.id,
        type: "strategy",
        position: n.position,
        selected: selected === n.id,
        data: {
          item: n,
          definition: catalogMap[n.type],
          label: catalogMap[n.type]?.name[locale] || n.type,
          errors: validation?.errors.some((e) => e.node_id === n.id),
        },
      })) || [],
    [spec, selected, catalogMap, locale, validation],
  );
  const edges: Edge[] = useMemo(
    () =>
      spec?.edges.map((e) => ({
        ...e,
        sourceHandle: e.sourceHandle || "out",
        targetHandle: e.targetHandle || "input",
        type: "smoothstep",
        animated: false,
        style: { stroke: "var(--mint)", strokeWidth: 1.7 },
      })) || [],
    [spec],
  );
  const node = spec?.nodes.find((n) => n.id === selected);
  const definition = node ? catalogMap[node.type] : undefined;
  const updateParam = (key: string, value: unknown) => {
    if (spec && node)
      commit({
        ...spec,
        nodes: spec.nodes.map((n) =>
          n.id === node.id
            ? { ...n, params: { ...n.params, [key]: value } }
            : n,
        ),
      });
  };
  const loadVersions = async () => {
    setShowVersions(true);
    try {
      setVersions(await api(`/strategies/${id}/versions`));
    } catch (e: any) {
      notify(e.message, true);
    }
  };
  const saveVersion = async () => {
    setVersionBusy(true);
    try {
      await persist(true);
      const version = await post(`/strategies/${id}/versions`);
      notify(
        `${t("Сохранена версия", "Saved version")} ${version.number || version.version_number || ""}`,
      );
      if (showVersions) setVersions(await api(`/strategies/${id}/versions`));
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setVersionBusy(false);
    }
  };
  if (loaded.loading || !spec)
    return loaded.error ? (
      <ErrorPanel message={loaded.error} retry={loaded.reload} />
    ) : (
      <Spinner />
    );
  const filtered = catalog.filter((n) =>
    `${n.name.ru} ${n.name.en} ${n.type} ${n.category}`.toLowerCase().includes(query.toLowerCase()),
  );
  const categories = [...new Set(filtered.map((n) => n.category))];
  return (
    <div className={`builder-page ${copilotOpen ? "with-copilot" : ""}`} data-testid="strategy-workspace">
      <div className="builder-title">
        <div>
          <Link
            to="/dashboard"
            className="icon-btn"
            aria-label={t("Назад к стратегиям", "Back to strategies")}
          >
            <ArrowLeft size={18} />
          </Link>
          <div>
            <div className="eyebrow">
              {t("СТРАТЕГИЯ / ПРИВАТНЫЙ ЧЕРНОВИК", "STRATEGY / PRIVATE DRAFT")}
            </div>
            <input
              data-testid="strategy-name"
              className="strategy-name"
              value={name}
              maxLength={120}
              aria-label={t("Название стратегии", "Strategy name")}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        </div>
        <div className="builder-title-actions">
          <span
            className={`save-status ${saveStatus === "error" ? "negative" : ""}`}
          >
            {saveStatus === "saved" ? (
              <CheckCheck size={14} />
            ) : (
              <span className="status-dot" />
            )}
            {saveStatus === "saved"
              ? t("Сохранено", "Saved")
              : saveStatus === "saving"
                ? t("Сохраняем…", "Saving…")
                : saveStatus === "error"
                  ? t("Ошибка сохранения", "Save failed")
                  : t("Есть изменения", "Unsaved changes")}
          </span>
          <button
            data-testid="save-strategy"
            className="btn secondary"
            disabled={saving}
            onClick={() => void persist()}
          >
            <Save size={15} />
            {t("Сохранить", "Save")}
          </button>
          <button
            data-testid="run-backtest"
            className="btn primary"
            onClick={() => setShowRun(true)}
          >
            <Play size={15} />
            {t("Проверить на истории", "Run backtest")}
          </button>
        </div>
      </div>
      <div className="builder-toolbar">
        <div className="builder-market">
          <span className="coin-mini">₿</span>
          <select
            aria-label={t("Рынок стратегии", "Strategy market")}
            value={spec.symbol}
            onChange={(e) =>
              commit({
                ...spec,
                symbol: e.target.value,
                nodes: spec.nodes.map((n) =>
                  n.type === "market"
                    ? { ...n, params: { ...n.params, symbol: e.target.value } }
                    : n,
                ),
              })
            }
          >
            <option>BTCUSDT</option>
            <option>ETHUSDT</option>
            <option>SOLUSDT</option>
          </select>
          <span className="toolbar-divider" />
          <select data-testid="strategy-timeframe" aria-label={t("Интервал стратегии","Strategy timeframe")} value={spec.timeframe} disabled={spec.schema_version===1} onChange={e=>commit({...spec,timeframe:e.target.value,nodes:spec.nodes.map(n=>n.type==="market"?{...n,params:{...n.params,timeframe:e.target.value}}:n)})}>{(spec.schema_version===1?["4h"]:["1m","5m","15m","1h","4h","1d"]).map(tf=><option key={tf}>{tf}</option>)}</select>
          <Badge>v{spec.schema_version}</Badge>
          <Badge>{t("Только long / cash", "Long / cash only")}</Badge>
        </div>
        <div className="builder-tools-v2">
          <button className="btn secondary compact" data-testid="guided-builder" onClick={()=>setGuidedOpen(true)}><GitBranch size={14}/>{t("Мастер правил","Rule wizard")}</button>
          <button className={`btn secondary compact ${copilotOpen?"active":""}`} data-testid="open-copilot" onClick={()=>setCopilotOpen(!copilotOpen)}><Sparkles size={14}/>{t("Помощник","Copilot")}</button>
          <Link className="icon-btn" to="/market" aria-label={t("Рыночный терминал","Market terminal")}><Activity size={16}/></Link>
          <button className="icon-btn" aria-label={t("Граф на весь экран","Fullscreen graph")} onClick={async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await canvasElement.current?.requestFullscreen();}}><Maximize2 size={16}/></button>
          <button
            className={`mode-switch ${expert ? "active" : ""}`}
            onClick={() => setExpert(!expert)}
          >
            <Settings2 size={14} />
            {expert
              ? t("Экспертный вид", "Expert view")
              : t("С подсказками", "Guided view")}
          </button>
          <button
            className="icon-btn"
            disabled={!past.length}
            onClick={undo}
            title={t("Отменить", "Undo")}
            aria-label={t("Отменить", "Undo")}
          >
            <Undo2 size={16} />
          </button>
          <button
            className="icon-btn"
            disabled={!future.length}
            onClick={redo}
            title={t("Повторить", "Redo")}
            aria-label={t("Повторить", "Redo")}
          >
            <Redo2 size={16} />
          </button>
          <span className="toolbar-divider" />
          <button
            className="icon-btn"
            onClick={() => void loadVersions()}
            title={t("Версии", "Versions")}
            aria-label={t("Версии", "Versions")}
          >
            <History size={17} />
          </button>
          <button
            className="icon-btn"
            onClick={() => setShowJSON(true)}
            title="JSON"
            aria-label="JSON"
          >
            <FileJson size={17} />
          </button>
        </div>
      </div>
      {spec.schema_version===1&&<div className="schema-compatibility"><Badge>ENGINE 1 / PRESERVED</Badge><span>{t("Старая схема сохраняет прежнюю семантику. Новые узлы требуют явного перехода черновика на v2.","Legacy semantics remain unchanged. New nodes require an explicit draft upgrade to v2.")}</span><button className="text-button" onClick={()=>{if(window.confirm(t("Перевести только черновик на v2? Сохранённые версии и результаты останутся без изменений. Проверьте новые допущения исполнения перед тестом.","Upgrade only this draft to v2? Saved versions and results remain unchanged. Review execution assumptions before testing.")))commit({...spec,schema_version:2});}}>{t("Перевести черновик на v2","Upgrade draft to v2")}</button></div>}
      <div className="builder-workspace">
        <aside className={`node-library ${libraryOpen ? "open" : ""}`}>
          <div className="library-head">
            <h3>{t("Блоки стратегии", "Strategy blocks")}</h3>
            <button
              className="icon-btn mobile-close"
              onClick={() => setLibraryOpen(false)}
              aria-label={t("Закрыть", "Close")}
            >
              <X size={15} />
            </button>
          </div>
          <div className="search-input">
            <Search size={14} />
            <input
              placeholder={t("Найти блок…", "Find a block…")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="node-library-list">
            {categories.map((category) => (
              <div key={category}>
                <h4>
                  {categoryLabels[category]
                    ? t(...categoryLabels[category])
                    : category}
                </h4>
                {filtered
                  .filter((n) => n.category === category)
                  .map((n) => {
                    const Icon = icons[n.type] || Settings2;
                    return (
                      <button
                        key={n.type}
                        draggable
                        data-testid={`add-node-${n.type}`}
                        title={
                          n.available
                            ? t(
                                "Нажмите или перетащите на схему",
                                "Click or drag onto the canvas",
                              )
                            : t(
                                "Провайдер пока не подключён",
                                "Provider is not connected",
                              )
                        }
                        onDragStart={(e) => {
                          e.dataTransfer.setData(
                            "application/kedr-node",
                            n.type,
                          );
                          e.dataTransfer.effectAllowed = "move";
                        }}
                        onClick={() => addNode(n)}
                      >
                        <Icon size={15} />
                        <span>{n.name[locale]}<small className={`catalog-status ${n.available?"executable":"unavailable"}`}>{n.available?t("Исполняется","Executable"):n.status==="preview"?t("Предпросмотр","Configurable preview"):n.status==="unsupported"?t("Не поддерживается","Not supported"):t("Нужен провайдер","Provider required")}</small></span>
                        {n.available ? (
                          <Plus size={12} />
                        ) : (
                          <LockKeyhole size={11} />
                        )}
                      </button>
                    );
                  })}
              </div>
            ))}
          </div>
          <div className="library-footer">
            <Info size={14} />
            {t(
              "Нажмите на блок или перетащите. Соедините порты слева направо.",
              "Click or drag a block. Connect ports from left to right.",
            )}
          </div>
        </aside>
        <div className="flow-wrap" ref={canvasElement}>
          <div className="canvas-topline">
            <span>
              <Network size={14} />
              {t("Логика стратегии", "Strategy logic")}
            </span>
            <span>
              {spec.nodes.length} {t("блоков", "blocks")} · {spec.edges.length}{" "}
              {t("связей", "connections")}
            </span>
          </div>
          <button
            className="btn secondary canvas-add"
            onClick={() => setLibraryOpen(true)}
          >
            <Plus size={15} />
            {t("Добавить блок", "Add block")}
          </button>
          <ReactFlow
            onInit={(instance) => {
              flowInstance.current = instance;
            }}
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.23, maxZoom: 1 }}
            minZoom={0.3}
            maxZoom={1.8}
            colorMode={theme === "dark" ? "dark" : "light"}
            onNodeClick={(_, n) => {
              setSelected(n.id);
              setShowRisk(false);
            }}
            onPaneClick={() => setSelected("")}
            onNodeDragStart={() => {
              setPast((v) => [...v.slice(-39), clone(spec)]);
              setFuture([]);
            }}
            onNodesChange={(changes) => {
              const edits = changes.filter(
                (change) =>
                  change.type === "remove" ||
                  (change.type === "position" &&
                    change.position &&
                    (change.position.x !==
                      spec.nodes.find((n) => n.id === change.id)?.position.x ||
                      change.position.y !==
                        spec.nodes.find((n) => n.id === change.id)?.position
                          .y)),
              );
              if (!edits.length) return;
              if (edits.some((change) => change.type === "remove")) {
                setPast((v) => [...v.slice(-39), clone(spec)]);
                setFuture([]);
              }
              const nextNodes = applyNodeChanges(edits, nodes);
              setSpec((prev) =>
                prev
                  ? {
                      ...prev,
                      nodes: nextNodes.map((n) => ({
                        ...n.data.item,
                        position: n.position,
                      })),
                      edges: prev.edges.filter(
                        (e) =>
                          nextNodes.some((n) => n.id === e.source) &&
                          nextNodes.some((n) => n.id === e.target),
                      ),
                    }
                  : prev,
              );
            }}
            onEdgesChange={(changes) => {
              const edits = changes.filter(
                (change) => change.type === "remove",
              );
              if (!edits.length) return;
              if (edits.some((change) => change.type === "remove")) {
                setPast((v) => [...v.slice(-39), clone(spec)]);
                setFuture([]);
              }
              const next = applyEdgeChanges(edits, edges);
              setSpec((prev) =>
                prev
                  ? {
                      ...prev,
                      edges: next.map((e) => ({
                        id: e.id,
                        source: e.source,
                        target: e.target,
                        sourceHandle: e.sourceHandle,
                        targetHandle: e.targetHandle,
                      })),
                    }
                  : prev,
              );
            }}
            onConnect={(connection) => {
              if (!canConnect(connection)) {
                notify(
                  t(
                    "Эти порты несовместимы или связь создаёт цикл.",
                    "These ports are incompatible or the connection creates a cycle.",
                  ),
                  true,
                );
                return;
              }
              commit({
                ...spec,
                edges: addEdge(connection, edges).map((e) => ({
                  id: e.id,
                  source: e.source,
                  target: e.target,
                  sourceHandle: e.sourceHandle,
                  targetHandle: e.targetHandle,
                })),
              });
            }}
            isValidConnection={canConnect}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
            }}
            onDrop={(e) => {
              e.preventDefault();
              const type = e.dataTransfer.getData("application/kedr-node");
              const def = catalogMap[type];
              if (def)
                addNode(
                  def,
                  flowInstance.current?.screenToFlowPosition({
                    x: e.clientX,
                    y: e.clientY,
                  }),
                );
            }}
            deleteKeyCode={["Backspace", "Delete"]}
          >
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
            <Controls showInteractive={false} />
            {expert && (
              <MiniMap
                pannable
                zoomable
                nodeColor="var(--mint)"
                maskColor="rgba(10,16,18,.75)"
              />
            )}
          </ReactFlow>
          {!spec.nodes.length && <div className="empty-canvas-hint" data-testid="empty-canvas"><Network size={35} strokeWidth={1}/><h3>{t("Чистый холст. Ваша логика.","A blank canvas. Your logic.")}</h3><p>{t("Добавьте цену, индикатор, условие и действие из библиотеки — или начните с мастера правил.","Add price, an indicator, a condition and an action from the library — or begin with the rule wizard.")}</p><button className="btn primary" onClick={()=>setGuidedOpen(true)}><Plus size={14}/>{t("Собрать первое правило","Build the first rule")}</button></div>}
          {!expert && (
            <div className="canvas-guide">
              <span>01</span>
              {t(
                "Выберите блок, чтобы изменить параметры. Условие должно быть связано с действием.",
                "Select a block to edit parameters. Connect a condition to an action.",
              )}
            </div>
          )}
        </div>
        <aside className="node-inspector">
          <div className="inspector-tabs">
            <button
              className={!showRisk ? "active" : ""}
              onClick={() => setShowRisk(false)}
            >
              {t("Параметры", "Parameters")}
            </button>
            <button
              className={showRisk ? "active" : ""}
              onClick={() => setShowRisk(true)}
            >
              {t("Риск", "Risk")}
            </button>
          </div>
          {showRisk ? (
            <div className="inspector-body">
              <div className="inspector-icon">
                <ShieldCheck size={24} />
              </div>
              <h3>{t("Рамки риска", "Risk boundaries")}</h3>
              <p>
                {t(
                  "Ограничения действуют в симуляции. Это не гарантия максимального убытка.",
                  "These limits apply in the simulation. They do not guarantee a loss bound.",
                )}
              </p>
              <label>
                {t("Доля капитала при входе", "Entry capital allocation")}
                <input
                  type="number"
                  min="0"
                  max="1"
                  step=".05"
                  value={spec.risk.max_exposure}
                  onChange={(e) =>
                    commit({
                      ...spec,
                      risk: { ...spec.risk, max_exposure: +e.target.value },
                    })
                  }
                />
                <small>
                  {t(
                    "0–1; 1 означает 100% при входе. Это не постоянная ребалансировка.",
                    "0–1; 1 means 100% at entry, not continuous rebalancing.",
                  )}
                </small>
              </label>
              {(["stop_loss_pct", "take_profit_pct"] as const).map((k) => (
                <label key={k}>
                  {k === "stop_loss_pct"
                    ? t("Стоп-лосс, %", "Stop loss, %")
                    : t("Тейк-профит, %", "Take profit, %")}
                  <input
                    type="number"
                    min=".01"
                    max="100"
                    step=".5"
                    placeholder={t("Не задан", "Not set")}
                    value={spec.risk[k] ?? ""}
                    onChange={(e) =>
                      commit({
                        ...spec,
                        risk: {
                          ...spec.risk,
                          [k]: e.target.value === "" ? null : +e.target.value,
                        },
                      })
                    }
                  />
                </label>
              ))}
              <div className="inspector-tip">
                {t(
                  "Блоки доли могут только уменьшать общее ограничение. Явные стопы и тейки заменяют общие проценты.",
                  "Allocation blocks can only reduce the root cap. Explicit stop/take blocks override root percentages.",
                )}
              </div>
            </div>
          ) : node && definition ? (
            <div className="inspector-body">
              <div className="inspector-type">
                <span>{definition.category}</span>
                <code>{node.type}</code>
              </div>
              <div className="inspector-icon">
                {(() => {
                  const I = icons[node.type] || Settings2;
                  return <I size={24} />;
                })()}
              </div>
              <h3>{definition.name[locale]}</h3>
              <p>
                {t(
                  "Значения рассчитываются только по завершённым свечам.",
                  "Values use completed candles only.",
                )}
              </p>
              {!definition.available&&<Notice>{definition.availability_message?.[locale]||t("Узел настраивается как контракт, но тест будет отклонён без настоящих входов. Ценовые прокси не подставляются.","This node is a configurable contract. A backtest rejects it without genuine inputs; no price proxy is substituted.")}</Notice>}
              {Object.entries(node.params).map(([key, value]) => (
                <label key={key}>
                  {(
                    {
                      period: t("Период, свечей", "Period, bars"),
                      value: t("Пороговое значение", "Threshold value"),
                      fraction: t("Доля капитала", "Capital fraction"),
                      pct: t("Процент", "Percent"),
                      field: t("Поле цены", "Price field"),
                      output: t("Выход", "Output"),
                    } as Record<string, string>
                  )[key] || key}
                  {typeof value === "boolean" ? <input type="checkbox" checked={value} onChange={e=>updateParam(key,e.target.checked)}/> : key === "symbol" || key === "timeframe" ? <select value={String(value)} onChange={e=>updateParam(key,e.target.value)}>{(key==="symbol"?["BTCUSDT","ETHUSDT","SOLUSDT"]:["1m","5m","15m","1h","4h","1d"]).map(v=><option key={v}>{v}</option>)}</select> : key === "field" || key === "output" ? (
                    <select
                      value={String(value)}
                      onChange={(e) => updateParam(key, e.target.value)}
                    >
                      {(key === "field"
                        ? node.type === "calendar" ? ["hour", "weekday", "month", "weekend"] : ["close", "open", "high", "low"]
                        : node.type === "macd"
                          ? ["line", "signal", "histogram"]
                          : node.type === "adx" ? ["adx", "plus_di", "minus_di"] : node.type === "stochastic" ? ["k", "d"] : ["upper", "middle", "lower"]
                      ).map((option) => (
                        <option key={option}>{option}</option>
                      ))}
                    </select>
                  ) : typeof value === "number" ? (
                    <input
                      type="number"
                      step={key === "fraction" ? ".05" : "any"}
                      value={value}
                      onChange={(e) => updateParam(key, Number(e.target.value))}
                    />
                  ) : (
                    <input
                      value={String(value)}
                      onChange={(e) => updateParam(key, e.target.value)}
                    />
                  )}
                </label>
              ))}
              {!Object.keys(node.params).length && (
                <div className="inspector-tip">
                  {t(
                    "У этого блока нет дополнительных параметров. Его поведение задаётся связями.",
                    "This block has no additional parameters. Its behavior is defined by connections.",
                  )}
                </div>
              )}
              <div className="port-schema">
                <span>{t("ТИПИЗИРОВАННЫЕ ПОРТЫ", "TYPED PORTS")}</span>
                {Object.entries(definition.inputs).map(([port, type]) => (
                  <div key={port}>
                    <i />
                    {port}
                    <code>{type}</code>
                  </div>
                ))}
                <div>
                  <i />
                  {t("выход", "output")}
                  <code>{definition.output}</code>
                </div>
              </div>
              <button
                className="btn danger full"
                onClick={() => {
                  commit({
                    ...spec,
                    nodes: spec.nodes.filter((n) => n.id !== node.id),
                    edges: spec.edges.filter(
                      (e) => e.source !== node.id && e.target !== node.id,
                    ),
                  });
                  setSelected("");
                }}
              >
                <Trash2 size={14} />
                {t("Удалить блок", "Delete block")}
              </button>
            </div>
          ) : (
            <div className="inspector-empty">
              <Settings2 size={27} strokeWidth={1.3} />
              <h3>{t("Выберите блок", "Select a block")}</h3>
              <p>
                {t(
                  "Нажмите на элемент схемы, чтобы настроить его. Перетащите границу порта к другому блоку, чтобы соединить.",
                  "Click a canvas block to configure it. Drag from a port to another block to connect.",
                )}
              </p>
              <button
                className="btn secondary"
                onClick={() => setShowRisk(true)}
              >
                <ShieldCheck size={15} />
                {t("Настроить риск", "Configure risk")}
              </button>
            </div>
          )}
        </aside>
      </div>
      {copilotOpen&&<div className="builder-copilot-dock"><Copilot strategyId={id} onClose={()=>setCopilotOpen(false)} onApplied={next=>{commit(next);loaded.reload();}}/></div>}
      <RuleSummary spec={spec} catalog={catalog}/>
      {guidedOpen&&<GuidedRuleBuilder spec={spec} onApply={commit} onClose={()=>setGuidedOpen(false)}/>}
      <div className={`validation-bar ${validation?.valid ? "valid" : ""}`}>
        <div>
          {validation?.valid ? <Check size={16} /> : <Info size={16} />}
          <b>
            {validation?.valid
              ? t("Структура корректна", "Structure is valid")
              : t("Требуется проверка", "Review required")}
          </b>
          <span>
            {validation?.valid
              ? t(
                  "Правила готовы к исторической симуляции.",
                  "Rules are ready for historical simulation.",
                )
              : (validation?.errors?.[0]
                  ? validationCopy(validation.errors[0], locale)
                  : "") ||
                t(
                  "Проверяем связи и параметры…",
                  "Checking connections and parameters…",
                )}
          </span>
        </div>
        <button
          className="text-button"
          onClick={() => void saveVersion()}
          disabled={versionBusy || !validation?.valid}
        >
          <GitBranch size={14} />
          {t("Зафиксировать версию", "Save a version")}
        </button>
      </div>
      {validation?.errors && validation.errors.length > 1 && (
        <div className="validation-errors">
          {validation.errors.slice(1).map((e, i) => (
            <div key={i}>
              {e.node_id && <code>{e.node_id}: </code>}
              {validationCopy(e, locale)}
            </div>
          ))}
        </div>
      )}
      {showRun && (
        <RunDialog
          strategyId={id}
          spec={spec}
          datasets={loaded.data?.[2] || []}
          valid={!!validation?.valid}
          save={async () => {
            await persist(true);
            if (
              saved.current !==
              JSON.stringify({ spec: latestSpec.current, name })
            )
              throw new Error(
                t(
                  "Не удалось сохранить текущие правила. Повторите сохранение.",
                  "Could not save the current rules. Please save again.",
                ),
              );
          }}
          onClose={() => setShowRun(false)}
        />
      )}{" "}
      {showJSON && (
        <Modal
          title={t("Спецификация стратегии", "Strategy specification")}
          onClose={() => setShowJSON(false)}
          wide
        >
          <Notice>
            {t(
              "Типизированная схема данных. Произвольный исполняемый код не поддерживается.",
              "A typed data specification. Arbitrary executable code is not supported.",
            )}
          </Notice>
          <pre className="json-block">{JSON.stringify(spec, null, 2)}</pre>
          <div className="modal-actions">
            <button
              className="btn secondary"
              onClick={async () => {
                await navigator.clipboard.writeText(
                  JSON.stringify(spec, null, 2),
                );
                notify(t("JSON скопирован", "JSON copied"));
              }}
            >
              <Copy size={14} />
              {t("Скопировать", "Copy")}
            </button>
          </div>
        </Modal>
      )}
      {showVersions && (
        <Modal
          title={t("Неизменяемые версии", "Immutable versions")}
          onClose={() => setShowVersions(false)}
        >
          <p className="muted">
            {t(
              "Каждый тест сохраняет точные правила. Последующие правки черновика не меняют старый результат.",
              "Every test preserves the exact rules. Draft edits do not change previous results.",
            )}
          </p>
          <div className="version-list">
            {versions.length ? (
              versions.map((v) => (
                <div key={v.id}>
                  <span className="version-dot">
                    <GitBranch size={16} />
                  </span>
                  <div>
                    <b>
                      {t("Версия", "Version")} {v.number}
                    </b>
                    <span>{date(v.created_at, true)}</span>
                    <code>{(v.spec_hash || "").slice(0, 16)}</code>
                  </div>
                  <Badge tone="mint">{t("Зафиксирована", "Immutable")}</Badge>
                </div>
              ))
            ) : (
              <p className="muted">
                {t(
                  "Пока нет зафиксированных версий.",
                  "No immutable versions yet.",
                )}
              </p>
            )}
          </div>
          <div className="modal-actions">
            <button
              className="btn secondary"
              onClick={async () => {
                try {
                  const copy = await post(`/strategies/${id}/duplicate`);
                  navigate(`/builder/${copy.id}`);
                  setShowVersions(false);
                } catch (e: any) {
                  notify(e.message, true);
                }
              }}
            >
              <Copy size={14} />
              {t("Дублировать стратегию", "Duplicate strategy")}
            </button>
            <button
              className="btn primary"
              disabled={versionBusy}
              onClick={() => void saveVersion()}
            >
              <Plus size={14} />
              {t("Новая версия", "New version")}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function RunDialog({
  strategyId,
  spec,
  datasets,
  valid,
  save,
  onClose,
}: {
  strategyId: string;
  spec: Spec;
  datasets: Dataset[];
  valid: boolean;
  save: () => Promise<void>;
  onClose: () => void;
}) {
  const { t, date, format } = useApp();
  const navigate = useNavigate();
  const matching = datasets.filter(
    (d) => d.symbol === spec.symbol && d.timeframe === spec.timeframe,
  );
  const available = matching.filter(datasetIsAvailable);
  const [datasetId, setDatasetId] = useState(
    preferredDataset(available)?.id || "",
  );
  const dataset = available.find((d) => d.id === datasetId);
  const [config, setConfig] = useState({
    start: dataset?.start.slice(0, 10) || "2022-01-01",
    end: dataset?.end.slice(0, 10) || "2025-12-31",
    initial_cash: 10000,
    fee_bps: 10,
    slippage_bps: 2,
    execution_delay_bars: 1,
    ...(spec.schema_version===2?{execution_mode:"full_bar_embargo",availability_seconds:5}:{}),
  });
  const [job, setJob] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [versions, setVersions] = useState<any[]>([]),
    [versionId, setVersionId] = useState("");
  useEffect(() => {
    api<any[]>(`/strategies/${strategyId}/versions`)
      .then(setVersions)
      .catch(() => {});
  }, [strategyId]);
  useEffect(() => {
    if (!job?.id || job.status === "succeeded" || job.status === "failed")
      return;
    let active = true;
    const timer = setInterval(async () => {
      try {
        const next = await api(`/jobs/${job.id}`);
        if (!active) return;
        setJob(next);
        if (next.status === "succeeded" && next.run_id) {
          navigate(`/backtests/${next.run_id}`);
          onClose();
        } else if (next.status === "failed") {
          setError(
            next.error ||
              t(
                "Ошибка расчёта. Проверьте конфигурацию.",
                "Calculation failed. Check the configuration.",
              ),
          );
          setBusy(false);
        }
      } catch (e: any) {
        if (active) {
          setError(e.message);
          setBusy(false);
        }
      }
    }, 800);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job?.id, job?.status, navigate, onClose, t]);
  const submit = async () => {
    if (!valid || !dataset) return;
    setBusy(true);
    setError("");
    try {
      await save();
      const created = await post("/backtests", {
        strategy_id: strategyId,
        ...(versionId ? { version_id: versionId } : {}),
        dataset_id: dataset.id,
        config,
      });
      setJob(created);
      if (created.status === "succeeded" && created.run_id) {
        navigate(`/backtests/${created.run_id}`);
        onClose();
      }
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t("Историческая проверка", "Historical backtest")}
      onClose={onClose}
      wide
    >
      <div className="run-dialog-grid">
        <div>
          <div className="eyebrow">
            01 / {t("ДАННЫЕ И ПЕРИОД", "DATA & PERIOD")}
          </div>
          <label>
            {t("Набор данных", "Dataset")}
            <select
              data-testid="dataset-select"
              disabled={busy}
              value={datasetId}
              onChange={(e) => {
                setDatasetId(e.target.value);
                const d = available.find((v) => v.id === e.target.value);
                if (d)
                  setConfig({
                    ...config,
                    start: d.start.slice(0, 10),
                    end: d.end.slice(0, 10),
                  });
              }}
            >
              {matching.map((d) => (
                <option key={d.id} value={d.id} disabled={!datasetIsAvailable(d)} title={d.error}>
                  {d.name}{!datasetIsAvailable(d) ? t(" — недоступен", " — unavailable") : d.source_type === "synthetic_demo" ? " — DEMO" : ""}
                </option>
              ))}
            </select>
          </label>
          {dataset && (
            <div className="dataset-detail">
              <SourceBadge type={dataset.source_type} />
              <p>
                {dataset.symbol} · {dataset.timeframe} ·{" "}
                {format(dataset.bars, 0)} {t("свечей", "bars")}
              </p>
              <small>
                {date(dataset.start)} — {date(dataset.end)}
              </small>
              <code>SHA256 {dataset.sha256?.slice(0, 18)}…</code>
            </div>
          )}
          {dataset?.source_type === "synthetic_demo" && (
            <Notice>{t(
              "Выбран синтетический демонстрационный набор: результаты проверяют работу приложения и не являются рыночными данными или свидетельством преимущества.",
              "Synthetic demo selected: results exercise the application and are not market data or evidence of an edge.",
            )}</Notice>
          )}
          {matching.some((d) => !datasetIsAvailable(d)) && (
            <p className="fine-print" data-testid="backtest-unavailable-data">{t("Неустановленные архивы недоступны: ", "Uninstalled archives are unavailable: ")}{matching.filter((d) => !datasetIsAvailable(d)).map((d) => d.error || d.name).join(" · ")}</p>
          )}
          <div className="form-row">
            <label>
              {t("Начало", "Start")}
              <input
                data-testid="backtest-start"
                type="date"
                value={config.start}
                min={dataset?.start.slice(0, 10)}
                max={config.end}
                disabled={busy}
                onChange={(e) =>
                  setConfig({ ...config, start: e.target.value })
                }
              />
            </label>
            <label>
              {t("Конец включительно", "End inclusive")}
              <input
                data-testid="backtest-end"
                type="date"
                value={config.end}
                min={config.start}
                max={dataset?.end.slice(0, 10)}
                disabled={busy}
                onChange={(e) => setConfig({ ...config, end: e.target.value })}
              />
            </label>
          </div>
          <label>
            {t("Версия правил", "Rules version")}
            <select
              disabled={busy}
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
            >
              <option value="">
                {t(
                  "Текущий черновик → новая точная версия",
                  "Current draft → a new exact version",
                )}
              </option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {t("Версия", "Version")} {v.number} · {date(v.created_at)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div>
          <div className="eyebrow">
            02 / {t("КАПИТАЛ И ИЗДЕРЖКИ", "CAPITAL & COSTS")}
          </div>
          <label>
            {t("Начальный капитал, USDT", "Initial capital, USDT")}
            <input
              type="number"
              min="10"
              max="10000000"
              disabled={busy}
              value={config.initial_cash}
              onChange={(e) =>
                setConfig({ ...config, initial_cash: +e.target.value })
              }
            />
          </label>
          <div className="form-row">
            <label>
              {t("Комиссия, bp / сторона", "Fee, bp / side")}
              <input
                type="number"
                min="0"
                max="100"
                disabled={busy}
                value={config.fee_bps}
                onChange={(e) =>
                  setConfig({ ...config, fee_bps: +e.target.value })
                }
              />
            </label>
            <label>
              {t("Проскальзывание, bp", "Slippage, bp")}
              <input
                type="number"
                min="0"
                max="100"
                disabled={busy}
                value={config.slippage_bps}
                onChange={(e) =>
                  setConfig({ ...config, slippage_bps: +e.target.value })
                }
              />
            </label>
          </div>
          {spec.schema_version===2&&<label>{t("Режим исполнения","Execution mode")}<select data-testid="execution-mode" value={config.execution_mode} onChange={e=>setConfig({...config,execution_mode:e.target.value,execution_delay_bars:1,availability_seconds:e.target.value==="next_bar_open_optimistic"?0:5})}><option value="full_bar_embargo">{t("Полная свеча эмбарго: консервативный архивный ориентир","Full-bar embargo: conservative archive reference")}</option><option value="next_bar_open_optimistic">{t("Следующее открытие: оптимистично, задержка получения 0","Next open: optimistic, zero receipt latency")}</option></select></label>}
          <label>
            {t("Задержка, полных свечей", "Delay, full bars")}
            <input
              type="number"
              min="1"
              max={config.execution_mode==="next_bar_open_optimistic"?1:6}
              disabled={busy||config.execution_mode==="next_bar_open_optimistic"}
              value={config.execution_delay_bars}
              onChange={(e) =>
                setConfig({ ...config, execution_delay_bars: +e.target.value })
              }
            />
          </label>
          <Notice>
            {t(
              config.execution_mode==="next_bar_open_optimistic"?"Оптимистичное исполнение на следующем открытии после сигнального закрытия: задержка публикации и получения принята нулевой. Это не подтверждённая цена заявки.":"1 bp = 0,01%. Сигнал на закрытии свечи i исполняется на открытии i + задержка + 1. Сделок по сигнальному закрытию нет.",
              config.execution_mode==="next_bar_open_optimistic"?"Optimistic next-open execution assumes zero publication and receipt latency after signal completion. This is not a verified order fill.":"1 bp = 0.01%. A signal at bar i close executes at the open of i + delay + 1. No execution at the signal close.",
            )}
          </Notice>
        </div>
      </div>
      {!available.length && (
        <div className="inline-error">
          {t(
            "Для этого рынка нет доступного набора данных. Выберите другой рынок в редакторе.",
            "No dataset is available for this market. Choose another market in the editor.",
          )}
        </div>
      )}
      {!valid && (
        <div className="inline-error">
          {t(
            "Сначала исправьте ошибки схемы.",
            "Fix the graph validation errors first.",
          )}
        </div>
      )}
      {error && (
        <div className="inline-error" role="alert">
          {error}
        </div>
      )}
      {job && busy && (
        <div className="job-progress">
          <span className="status-dot" />
          <div>
            <b>
              {job.status === "queued"
                ? t("Проверка поставлена в очередь", "Test is queued")
                : t(
                    "Рассчитываем по зафиксированным правилам",
                    "Calculating the immutable strategy",
                  )}
            </b>
            <small>
              {t(
                "Результат сохранится в истории. Это историческая симуляция.",
                "The result will be saved to history. This is a historical simulation.",
              )}
            </small>
          </div>
          <span className="progress-line" />
        </div>
      )}
      <div className="modal-actions">
        <span className="fine-print">
          {t(
            "Приватный результат. Можно опубликовать позже.",
            "Private result. You can publish it later.",
          )}
        </span>
        <button
          data-testid="confirm-backtest"
          className="btn primary"
          disabled={busy || !valid || !dataset}
          onClick={() => void submit()}
        >
          <Play size={15} />
          {busy
            ? t("Выполняется…", "Running…")
            : t("Запустить проверку", "Run backtest")}
        </button>
      </div>
    </Modal>
  );
}
