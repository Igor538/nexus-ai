import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import {
  ArrowLeft,
  CheckCircle2,
  CircleAlert,
  Copy,
  History,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  Sparkles,
  Trash2,
  Webhook,
} from "lucide-react";
import { Modal } from "../components/Modal";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import type {
  AIProviderList,
  Credential,
  Graph,
  GraphEdge,
  GraphNode,
  JsonSchemaProperty,
  NodeCatalog,
  NodeCatalogEntry,
  ValidationResult,
  WebhookInfo,
  Workflow,
  WorkflowVersionSummary,
} from "../lib/types";
import { formatDate, getErrorMessage } from "../lib/utils";

type EditorNodeData = {
  nodeType: string;
  label: string;
  config: Record<string, unknown>;
  disabled: boolean;
  retryAttempts: number;
  retryDelay: number;
  outputs: string[];
  dynamicOutputs: boolean;
  isTrigger: boolean;
  category: string;
};

type EditorNode = Node<EditorNodeData, "nexus">;

type SwitchCase = { id: string; match: unknown };

const LONG_TEXT_FIELDS = new Set(["template", "prompt", "system", "goal", "message", "text", "description"]);

const VERSION_ORIGIN_LABELS: Record<string, string> = {
  create: "criação",
  update: "edição",
  duplicate: "duplicação",
  restore: "restauração",
  baseline: "estado atual",
  manual: "edição",
};

function fieldLabel(field: string): string {
  const spaced = field.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function readCases(config: Record<string, unknown>): SwitchCase[] {
  const raw = config.cases;
  if (!Array.isArray(raw)) return [];
  const cases: SwitchCase[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const id = typeof record.id === "string" ? record.id : "";
    if (!id) continue;
    cases.push({ id, match: record.match ?? "" });
  }
  return cases;
}

function summarize(type: string, config: Record<string, unknown>): string[] {
  const pick = (key: string): string => {
    const value = config[key];
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    return "";
  };
  let values: string[];
  if (type === "action_http") {
    values = [pick("method"), pick("url")];
  } else if (type.startsWith("ai_")) {
    values = [pick("provider"), pick("model") || pick("prompt") || pick("text") || pick("goal")];
  } else if (type === "logic_if" || type === "logic_compare" || type === "logic_filter") {
    values = [`${pick("left")} ${pick("operator")} ${pick("right")}`.trim()];
  } else if (type === "trigger_schedule") {
    values = [pick("cron"), pick("timezone")];
  } else if (type === "trigger_webhook") {
    values = [pick("method")];
  } else if (type === "trigger_event") {
    values = [pick("topic")];
  } else if (type === "action_notification") {
    values = [pick("channel"), pick("title")];
  } else {
    values = Object.values(config).filter(
      (value): value is string => typeof value === "string" && value.trim().length > 0,
    );
  }
  return values
    .filter((value) => value.trim().length > 0)
    .slice(0, 2)
    .map((value) => (value.length > 36 ? `${value.slice(0, 35)}…` : value));
}

function toneForCategory(category: string): string {
  if (category === "trigger") return "#F2A33C";
  if (category === "logic") return "#A78BFA";
  if (category === "ai") return "#F2795B";
  return "#2ED3B7";
}

function toFlowNode(node: GraphNode, catalog: Map<string, NodeCatalogEntry>): EditorNode {
  const entry = catalog.get(node.type);
  return {
    id: node.id,
    type: "nexus",
    position: { x: node.position?.x ?? 0, y: node.position?.y ?? 0 },
    data: {
      nodeType: node.type,
      label: node.label || entry?.label || node.type,
      config: node.config ?? {},
      disabled: Boolean(node.disabled),
      retryAttempts: node.retry_attempts ?? 1,
      retryDelay: node.retry_delay_seconds ?? 0,
      outputs: entry?.outputs ?? ["output"],
      dynamicOutputs: Boolean(entry?.dynamic_outputs),
      isTrigger: Boolean(entry?.is_trigger),
      category: entry?.category ?? "action",
    },
  };
}

function toFlowEdge(edge: GraphEdge): Edge {
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
    label:
      edge.label ??
      (edge.sourceHandle && edge.sourceHandle !== "output" ? edge.sourceHandle : undefined),
  };
}

function EditorNodeView({ data, selected }: NodeProps<EditorNode>) {
  const outputs = data.dynamicOutputs
    ? [
        ...readCases(data.config).map((item) => item.id),
        typeof data.config.default_label === "string" && data.config.default_label.trim()
          ? data.config.default_label
          : "default",
      ]
    : data.outputs.length
      ? data.outputs
      : ["output"];
  const summary = summarize(data.nodeType, data.config);

  return (
    <div
      className={`editor-node editor-node--${data.category} ${selected ? "is-selected" : ""} ${
        data.disabled ? "is-disabled" : ""
      }`}
    >
      {data.isTrigger ? null : <Handle type="target" position={Position.Left} />}
      <div className="editor-node__head">
        <span className={`palette-item__dot palette-item__dot--${data.category}`} />
        <span className="editor-node__title">{data.label || data.nodeType}</span>
        {data.disabled ? <span className="editor-node__badge">off</span> : null}
      </div>
      <div className="editor-node__config">
        <span className="mono">{data.nodeType}</span>
        {summary.map((line, index) => (
          <span key={`${line}-${index}`}>{line}</span>
        ))}
      </div>
      {outputs.map((output, index) => {
        const top = `${((index + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <div key={`${output}-${index}`}>
            <Handle type="source" position={Position.Right} id={output} style={{ top }} />
            {outputs.length > 1 ? (
              <span
                style={{
                  position: "absolute",
                  right: 10,
                  top,
                  transform: "translateY(-50%)",
                  fontSize: "0.55rem",
                  color: "var(--muted)",
                  pointerEvents: "none",
                }}
              >
                {output}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

const nodeTypes = { nexus: EditorNodeView };

function JsonField({
  value,
  onChange,
  rows = 4,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  rows?: number;
}) {
  const [text, setText] = useState(() =>
    value === undefined ? "null" : JSON.stringify(value ?? null, null, 2),
  );
  const [invalid, setInvalid] = useState(false);

  return (
    <div className="form-stack" style={{ gap: "0.3rem" }}>
      <textarea
        className="mono"
        rows={rows}
        value={text}
        spellCheck={false}
        onChange={(event) => {
          const next = event.target.value;
          setText(next);
          try {
            onChange(next.trim() === "" ? null : JSON.parse(next));
            setInvalid(false);
          } catch {
            setInvalid(true);
          }
        }}
      />
      {invalid ? <span className="form-error">JSON inválido — ainda não aplicado.</span> : null}
    </div>
  );
}

function AnyField({ value, onChange }: { value: unknown; onChange: (value: unknown) => void }) {
  const [text, setText] = useState(() => {
    if (typeof value === "string") return value;
    if (value === null || value === undefined) return "";
    return JSON.stringify(value);
  });

  function commit(next: string) {
    setText(next);
    if (next.trim() === "") {
      onChange(null);
      return;
    }
    const trimmed = next.trim();
    if (trimmed === "true" || trimmed === "false") {
      onChange(trimmed === "true");
      return;
    }
    if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
      onChange(Number(trimmed));
      return;
    }
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        onChange(JSON.parse(trimmed));
        return;
      } catch {
        // Falls back to the raw string.
      }
    }
    onChange(next);
  }

  return (
    <input
      value={text}
      onChange={(event) => commit(event.target.value)}
      placeholder="texto, número, true/false ou JSON"
    />
  );
}

function ConfigField({
  field,
  property,
  defs,
  value,
  credentials,
  onChange,
  nodeId,
}: {
  field: string;
  property: JsonSchemaProperty;
  defs?: Record<string, JsonSchemaProperty>;
  value: unknown;
  credentials: Credential[];
  onChange: (value: unknown) => void;
  nodeId: string;
}) {
  let schema = property;
  let guard = 0;
  while (schema.$ref && guard < 5) {
    const name = schema.$ref.split("/").pop() ?? "";
    const next = defs?.[name];
    if (!next) break;
    schema = next;
    guard += 1;
  }

  const title = schema.title ?? fieldLabel(field);
  const description = schema.description;

  if (field === "credential_id") {
    return (
      <label className="field">
        <span>{title}</span>
        <select
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
        >
          <option value="">Nenhuma credencial</option>
          {credentials.map((credential) => (
            <option key={credential.id} value={credential.id}>
              {credential.name} ({credential.type})
            </option>
          ))}
        </select>
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  if (schema.enum && schema.enum.length > 0) {
    return (
      <label className="field">
        <span>{title}</span>
        <select
          value={value === null || value === undefined ? "" : String(value)}
          onChange={(event) => {
            const raw = event.target.value;
            const match = schema.enum?.find((option) => String(option) === raw);
            onChange(match === undefined ? raw : match);
          }}
        >
          {schema.enum.map((option) => (
            <option key={String(option)} value={String(option)}>
              {option === "" ? "Automático" : String(option)}
            </option>
          ))}
        </select>
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  if (schema.type === "boolean" || typeof value === "boolean") {
    return (
      <label className="inspector-row">
        <span>{title}</span>
        <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
      </label>
    );
  }

  if (schema.type === "integer" || schema.type === "number") {
    return (
      <label className="field">
        <span>{title}</span>
        <input
          type="number"
          value={value === null || value === undefined || value === "" ? "" : Number(value)}
          min={schema.minimum}
          max={schema.maximum}
          onChange={(event) => {
            const raw = event.target.value;
            onChange(raw === "" ? null : Number(raw));
          }}
        />
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  if (schema.type === "array" && schema.items?.type === "string") {
    return (
      <label className="field">
        <span>{title}</span>
        <input
          value={Array.isArray(value) ? value.map(String).join(", ") : ""}
          onChange={(event) =>
            onChange(
              event.target.value
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
          placeholder="separados por vírgula"
        />
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  if (schema.type === "array" || schema.type === "object") {
    return (
      <div className="field">
        <span>{title}</span>
        <JsonField key={`${nodeId}-${field}`} value={value} onChange={onChange} />
        {description ? <small className="muted small">{description}</small> : null}
      </div>
    );
  }

  if (schema.type === "string" && LONG_TEXT_FIELDS.has(field)) {
    return (
      <label className="field">
        <span>{title}</span>
        <textarea rows={4} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} />
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  if (schema.type === "string") {
    return (
      <label className="field">
        <span>{title}</span>
        <input
          value={typeof value === "string" ? value : value === null || value === undefined ? "" : String(value)}
          onChange={(event) => onChange(event.target.value)}
        />
        {description ? <small className="muted small">{description}</small> : null}
      </label>
    );
  }

  return (
    <div className="field">
      <span>{title}</span>
      <AnyField key={`${nodeId}-${field}`} value={value} onChange={onChange} />
      {description ? <small className="muted small">{description}</small> : null}
    </div>
  );
}

function SwitchCasesEditor({
  cases,
  onChange,
}: {
  cases: SwitchCase[];
  onChange: (cases: SwitchCase[]) => void;
}) {
  return (
    <div className="field">
      <span>Casos</span>
      <div className="switch-cases">
        {cases.map((item, index) => (
          <div className="switch-case" key={`${item.id}-${index}`}>
            <input
              value={item.id}
              placeholder="identificador"
              maxLength={40}
              onChange={(event) => {
                const next = cases.map((entry, position) =>
                  position === index ? { ...entry, id: event.target.value } : entry,
                );
                onChange(next);
              }}
            />
            <input
              value={typeof item.match === "string" ? item.match : JSON.stringify(item.match ?? "")}
              placeholder="valor"
              onChange={(event) => {
                const next = cases.map((entry, position) =>
                  position === index ? { ...entry, match: event.target.value } : entry,
                );
                onChange(next);
              }}
            />
            <button
              type="button"
              className="icon-button icon-button--danger icon-button--small"
              onClick={() => onChange(cases.filter((_, position) => position !== index))}
              aria-label="Remover caso"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {cases.length < 10 ? (
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => onChange([...cases, { id: `caso_${cases.length + 1}`, match: "" }])}
          >
            <Plus size={14} /> Adicionar caso
          </button>
        ) : null}
      </div>
      <small className="muted small">Saídas dinâmicas: cada caso vira uma conexão no canvas.</small>
    </div>
  );
}

export function WorkflowEditorPage() {
  const params = useParams();
  const workflowId = Number(params.id);
  const navigate = useNavigate();
  const { notify } = useToast();

  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [catalog, setCatalog] = useState<NodeCatalog | null>(null);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [webhook, setWebhook] = useState<WebhookInfo | null>(null);
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [paletteSearch, setPaletteSearch] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [webhookOpen, setWebhookOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [runInput, setRunInput] = useState("{}");
  const [runBusy, setRunBusy] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versions, setVersions] = useState<WorkflowVersionSummary[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState("");
  const [aiProviders, setAiProviders] = useState<AIProviderList | null>(null);
  const [aiProvider, setAiProvider] = useState("");
  const [aiModel, setAiModel] = useState("");

  const [nodes, setNodes, onNodesChange] = useNodesState<EditorNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const catalogMap = useMemo(
    () => new Map((catalog?.nodes ?? []).map((entry) => [entry.type, entry])),
    [catalog],
  );

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? null,
    [nodes, selectedId],
  );

  useEffect(() => {
    if (!Number.isFinite(workflowId)) {
      navigate("/workflows", { replace: true });
      return;
    }
    let active = true;
    setLoading(true);
    setError("");
    Promise.all([
      api.workflow(workflowId),
      api.catalog(),
      api.credentials().catch(() => [] as Credential[]),
      api.webhookInfo(workflowId).catch(() => null),
    ])
      .then(([loadedWorkflow, loadedCatalog, loadedCredentials, loadedWebhook]) => {
        if (!active) return;
        const map = new Map(loadedCatalog.nodes.map((entry) => [entry.type, entry]));
        setWorkflow(loadedWorkflow);
        setCatalog(loadedCatalog);
        setCredentials(loadedCredentials);
        setWebhook(loadedWebhook);
        setNodes(loadedWorkflow.graph.nodes.map((node) => toFlowNode(node, map)));
        setEdges(loadedWorkflow.graph.edges.map(toFlowEdge));
        setValidation(null);
        setSelectedId(null);
        setWebhookSecret(null);
        setDirty(false);
      })
      .catch((reason) => {
        if (active) setError(getErrorMessage(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workflowId, navigate, setNodes, setEdges]);

  useEffect(() => {
    if (selectedId && !nodes.some((node) => node.id === selectedId)) {
      setSelectedId(null);
    }
  }, [nodes, selectedId]);

  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const buildGraph = useCallback(
    (): Graph => ({
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.data.nodeType,
        label: node.data.label || null,
        position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
        config: node.data.config,
        disabled: node.data.disabled,
        retry_attempts: node.data.retryAttempts,
        retry_delay_seconds: node.data.retryDelay,
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? null,
        targetHandle: edge.targetHandle ?? null,
        label: typeof edge.label === "string" ? edge.label : null,
      })),
      viewport: null,
    }),
    [nodes, edges],
  );

  const handleConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((current) =>
        addEdge(
          {
            ...connection,
            id: `edge_${connection.source}_${connection.sourceHandle ?? "out"}_${connection.target}_${Date.now().toString(36)}`,
            label:
              connection.sourceHandle && connection.sourceHandle !== "output"
                ? connection.sourceHandle
                : undefined,
          },
          current,
        ),
      );
      setDirty(true);
    },
    [setEdges],
  );

  const handleNodesChange: OnNodesChange<EditorNode> = useCallback(
    (changes) => {
      onNodesChange(changes);
      if (changes.some((change) => change.type !== "select" && change.type !== "dimensions")) {
        setDirty(true);
      }
    },
    [onNodesChange],
  );

  const handleEdgesChange: OnEdgesChange<Edge> = useCallback(
    (changes) => {
      onEdgesChange(changes);
      if (changes.some((change) => change.type !== "select")) {
        setDirty(true);
      }
    },
    [onEdgesChange],
  );

  function patchSelected(patch: Partial<EditorNodeData>) {
    if (!selectedId) return;
    setNodes((current) =>
      current.map((node) =>
        node.id === selectedId ? { ...node, data: { ...node.data, ...patch } } : node,
      ),
    );
    setDirty(true);
  }

  function setConfigField(field: string, value: unknown) {
    if (!selectedNode) return;
    patchSelected({ config: { ...selectedNode.data.config, [field]: value } });
  }

  function addNode(entry: NodeCatalogEntry) {
    const id = `${entry.type}_${Math.random().toString(36).slice(2, 8)}`;
    const index = nodes.length;
    const node: EditorNode = {
      id,
      type: "nexus",
      position: {
        x: 80 + (index % 3) * 260,
        y: 60 + Math.floor(index / 3) * 150,
      },
      data: {
        nodeType: entry.type,
        label: entry.label,
        config: { ...(entry.defaults ?? {}) },
        disabled: false,
        retryAttempts: 1,
        retryDelay: 0,
        outputs: entry.outputs,
        dynamicOutputs: entry.dynamic_outputs,
        isTrigger: entry.is_trigger,
        category: entry.category,
      },
    };
    setNodes((current) => [...current, node]);
    setSelectedId(id);
    setDirty(true);
  }

  function autoLayout() {
    const incoming = new Map<string, number>();
    const outgoing = new Map<string, string[]>();
    nodes.forEach((node) => {
      incoming.set(node.id, 0);
      outgoing.set(node.id, []);
    });
    edges.forEach((edge) => {
      if (!incoming.has(edge.target) || !outgoing.has(edge.source)) return;
      incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
      outgoing.get(edge.source)?.push(edge.target);
    });
    const levels = new Map<string, number>();
    const queue = nodes.filter((node) => (incoming.get(node.id) ?? 0) === 0).map((node) => node.id);
    queue.forEach((id) => levels.set(id, 0));
    const order = [...queue];
    while (order.length) {
      const id = order.shift();
      if (!id) continue;
      const level = levels.get(id) ?? 0;
      for (const next of outgoing.get(id) ?? []) {
        if (levels.has(next)) continue;
        levels.set(next, level + 1);
        order.push(next);
      }
    }
    nodes.forEach((node) => {
      if (!levels.has(node.id)) levels.set(node.id, 0);
    });
    const byLevel = new Map<number, string[]>();
    nodes.forEach((node) => {
      const level = levels.get(node.id) ?? 0;
      byLevel.set(level, [...(byLevel.get(level) ?? []), node.id]);
    });
    setNodes((current) =>
      current.map((node) => {
        const level = levels.get(node.id) ?? 0;
        const index = (byLevel.get(level) ?? []).indexOf(node.id);
        return { ...node, position: { x: 60 + level * 270, y: 60 + index * 140 } };
      }),
    );
    setDirty(true);
  }

  async function save() {
    if (!workflow) return;
    setSaving(true);
    try {
      const updated = await api.updateWorkflow(workflow.id, { graph: buildGraph() });
      setWorkflow(updated);
      setNodes(updated.graph.nodes.map((node) => toFlowNode(node, catalogMap)));
      setEdges(updated.graph.edges.map(toFlowEdge));
      setDirty(false);
      setValidation(null);
      const freshWebhook = await api.webhookInfo(updated.id).catch(() => null);
      if (freshWebhook) setWebhook(freshWebhook);
      notify("success", "Fluxo salvo.");
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  async function validate() {
    setValidating(true);
    try {
      const result = await api.validateWorkflow(buildGraph());
      setValidation(result);
      if (result.valid) notify("success", "Fluxo válido e pronto para executar.");
      else notify("error", `A validação encontrou ${result.issues.length} problema(s).`);
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setValidating(false);
    }
  }

  async function toggleActive() {
    if (!workflow) return;
    try {
      const updated = await api.updateWorkflow(workflow.id, { is_active: !workflow.is_active });
      setWorkflow(updated);
      notify("success", updated.is_active ? "Automação ativada." : "Automação pausada.");
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    }
  }

  async function submitRun() {
    if (!workflow) return;
    let payload: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(runInput.trim() || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Informe um objeto JSON para a entrada.");
      }
      payload = parsed as Record<string, unknown>;
    } catch (reason) {
      notify("error", reason instanceof Error ? reason.message : "JSON inválido.");
      return;
    }
    setRunBusy(true);
    try {
      const execution = await api.runWorkflow(workflow.id, payload);
      notify("success", `Execução #${execution.id} iniciada.`);
      setRunOpen(false);
      navigate(`/executions?highlight=${execution.id}`);
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setRunBusy(false);
    }
  }

  function openSettings() {
    if (!workflow) return;
    setName(workflow.name);
    setDescription(workflow.description ?? "");
    setSettingsOpen(true);
  }

  function openGenerator() {
    setAiOpen(true);
    setAiError("");
    if (aiProviders) return;
    api
      .aiProviders()
      .then((list) => {
        setAiProviders(list);
        const preferred =
          list.providers.find((item) => item.is_default && item.configured) ??
          list.providers.find((item) => item.configured) ??
          list.providers.find((item) => item.is_default) ??
          list.providers[0];
        if (preferred) {
          setAiProvider(preferred.name);
          setAiModel(preferred.default_model);
        }
      })
      .catch((reason) => setAiError(getErrorMessage(reason)));
  }

  function chooseProvider(providerName: string) {
    setAiProvider(providerName);
    const provider = aiProviders?.providers.find((item) => item.name === providerName);
    setAiModel(provider?.default_model ?? "");
  }

  async function generateGraph() {
    const prompt = aiPrompt.trim();
    if (prompt.length < 3) {
      setAiError("Descreva a automação com pelo menos 3 caracteres.");
      return;
    }
    setAiBusy(true);
    setAiError("");
    try {
      const result = await api.generateWorkflow(
        prompt,
        aiProvider || undefined,
        aiModel || undefined,
      );
      setNodes(result.graph.nodes.map((node) => toFlowNode(node, catalogMap)));
      setEdges(result.graph.edges.map(toFlowEdge));
      setSelectedId(null);
      setDirty(true);
      setValidation({
        valid: !result.issues.some((issue) => issue.severity === "error"),
        issues: result.issues,
      });
      setAiOpen(false);
      notify(
        "success",
        `Fluxo gerado por ${result.provider_label ?? result.provider}. Revise e salve.`,
      );
    } catch (reason) {
      setAiError(getErrorMessage(reason));
    } finally {
      setAiBusy(false);
    }
  }

  async function saveSettings() {
    if (!workflow) return;
    if (name.trim().length < 2) {
      notify("error", "O nome precisa de pelo menos 2 caracteres.");
      return;
    }
    setSettingsBusy(true);
    try {
      const updated = await api.updateWorkflow(workflow.id, {
        name: name.trim(),
        description: description.trim() || null,
      });
      setWorkflow(updated);
      notify("success", "Identidade do fluxo atualizada.");
      setSettingsOpen(false);
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setSettingsBusy(false);
    }
  }

  async function rotateSecret() {
    if (!workflow) return;
    setRotating(true);
    try {
      const result = await api.rotateWebhook(workflow.id, webhook?.node_id ?? undefined);
      setWebhookSecret(typeof result.secret === "string" ? result.secret : null);
      setWebhook(await api.webhookInfo(workflow.id).catch(() => webhook));
      notify("success", "Novo segredo gerado. Copie agora — ele não aparece de novo.");
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setRotating(false);
    }
  }

  async function openVersions() {
    if (!workflow) return;
    setVersionsOpen(true);
    setVersionsLoading(true);
    try {
      setVersions(await api.workflowVersions(workflow.id));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setVersionsLoading(false);
    }
  }

  async function restoreVersion(version: number) {
    if (!workflow) return;
    setRestoringVersion(version);
    try {
      const updated = await api.restoreWorkflowVersion(workflow.id, version);
      setWorkflow(updated);
      setNodes(updated.graph.nodes.map((node) => toFlowNode(node, catalogMap)));
      setEdges(updated.graph.edges.map(toFlowEdge));
      setSelectedId(null);
      setValidation(null);
      setDirty(false);
      notify("success", `Versão ${version} restaurada como v${updated.version}.`);
      setVersions(await api.workflowVersions(workflow.id));
    } catch (reason) {
      notify("error", getErrorMessage(reason));
    } finally {
      setRestoringVersion(null);
    }
  }

  async function copy(value: string | null | undefined, label: string) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      notify("success", `${label} copiado.`);
    } catch {
      notify("error", "Não foi possível copiar automaticamente.");
    }
  }

  if (loading) {
    return (
      <div className="editor-loading">
        <Loader2 size={22} className="spin" />
        <span>Montando o canvas…</span>
      </div>
    );
  }

  if (error || !workflow || !catalog) {
    return (
      <div className="page">
        <div className="alert alert--error">{error || "Automação não encontrada."}</div>
        <Link className="button button--ghost" to="/workflows">
          <ArrowLeft size={16} /> Voltar para a biblioteca
        </Link>
      </div>
    );
  }

  const entry = selectedNode ? catalogMap.get(selectedNode.data.nodeType) : undefined;
  const schema = entry?.config_schema;
  const switchCases = selectedNode ? readCases(selectedNode.data.config) : [];
  const query = paletteSearch.trim().toLowerCase();
  const selectedProvider = aiProviders?.providers.find((item) => item.name === aiProvider);
  const aiModels = selectedProvider?.models ?? [];
  const aiReady = Boolean(aiProviders?.providers.some((item) => item.configured));

  return (
    <div className="editor">
      <header className="editor__top">
        <div className="editor__meta">
          <Link to="/workflows" className="icon-button" aria-label="Voltar">
            <ArrowLeft size={18} />
          </Link>
          <h2>{workflow.name}</h2>
          <span className={`pill ${workflow.is_active ? "pill--live" : ""}`}>
            {workflow.is_active ? "ativa" : "pausada"}
          </span>
          <span className="mono muted">v{workflow.version}</span>
          <span className="muted small">
            {nodes.length} nós · {edges.length} conexões
          </span>
          {dirty ? <span className="dirty-dot" title="Alterações não salvas" /> : null}
        </div>

        <div className="editor__actions">
          <button type="button" className="icon-button" onClick={openSettings} title="Editar nome e descrição">
            <Settings2 size={17} />
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => setWebhookOpen(true)}
          >
            <Webhook size={15} /> Webhook
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => void openVersions()}
            title="Histórico de versões do fluxo"
          >
            <History size={15} /> Histórico
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={openGenerator}
            title="Gerar um fluxo a partir de uma descrição"
          >
            <Sparkles size={15} /> Gerar com IA
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={autoLayout}
            title="Organizar nós automaticamente"
          >
            <RefreshCw size={15} /> Organizar
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => void validate()}
            disabled={validating}
          >
            {validating ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />} Validar
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => void toggleActive()}
            title={workflow.is_active ? "Pausar automação" : "Ativar automação"}
          >
            {workflow.is_active ? <Pause size={17} /> : <Play size={17} />}
          </button>
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => setRunOpen(true)}
            disabled={!workflow.is_active}
            title={workflow.is_active ? "Executar agora" : "Ative a automação para executar"}
          >
            <Play size={15} /> Executar
          </button>
          <button
            type="button"
            className="button button--primary button--small"
            onClick={() => void save()}
            disabled={saving || !dirty}
          >
            {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />} Salvar
          </button>
        </div>
      </header>

      <div className="editor__body">
        <aside className="editor__palette" aria-label="Biblioteca de nós">
          <input
            value={paletteSearch}
            onChange={(event) => setPaletteSearch(event.target.value)}
            placeholder="Filtrar nós"
            aria-label="Filtrar nós"
          />
          {catalog.categories.map((category) => {
            const items = catalog.nodes.filter(
              (node) =>
                node.category === category.key &&
                (!query ||
                  node.label.toLowerCase().includes(query) ||
                  node.type.toLowerCase().includes(query)),
            );
            if (items.length === 0) return null;
            return (
              <div className="palette-group" key={category.key}>
                <span>{category.label}</span>
                {items.map((item) => (
                  <button
                    type="button"
                    className="palette-item"
                    key={item.type}
                    onClick={() => addNode(item)}
                    title={item.description}
                  >
                    <span className={`palette-item__dot palette-item__dot--${item.category}`} />
                    {item.label}
                  </button>
                ))}
              </div>
            );
          })}
        </aside>

        <section className="editor__canvas" aria-label="Canvas do fluxo">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={handleConnect}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            minZoom={0.3}
            maxZoom={1.6}
            defaultEdgeOptions={{ type: "smoothstep" }}
            deleteKeyCode={["Backspace", "Delete"]}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={18}
              size={1.5}
              color="rgba(255,255,255,0.09)"
            />
            <MiniMap
              pannable
              zoomable
              nodeColor={(node: Node) => toneForCategory(String(node.data?.category ?? "action"))}
            />
            <Controls showInteractive={false} />
          </ReactFlow>
        </section>

        <aside className="editor__inspector" aria-label="Inspetor do nó">
          {validation ? (
            <div className="inspector-section">
              <div className="inspector-section__head">
                <h3>Validação</h3>
                <button
                  type="button"
                  className="icon-button icon-button--small"
                  onClick={() => setValidation(null)}
                  aria-label="Fechar validação"
                >
                  <Trash2 size={13} />
                </button>
              </div>
              {validation.issues.length === 0 ? (
                <ul className="validation-list">
                  <li className="is-ok">
                    <CheckCircle2 size={13} /> Nenhum problema encontrado.
                  </li>
                </ul>
              ) : (
                <ul className="validation-list">
                  {validation.issues.map((issue, index) => (
                    <li
                      key={`${issue.node_id ?? "graph"}-${index}`}
                      className={issue.severity === "error" ? "is-error" : ""}
                    >
                      <CircleAlert size={13} />
                      <span>
                        {issue.node_id ? <span className="mono">{issue.node_id}: </span> : null}
                        {issue.message}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {!selectedNode ? (
            <div className="inspector-empty">
              <span className="eyebrow">Inspetor</span>
              <strong>Selecione um nó</strong>
              <p>Clique em um nó do canvas para ajustar rótulo, configuração e resiliência.</p>
              <p>Arraste da porta de saída para conectar. Delete remove o item selecionado.</p>
            </div>
          ) : (
            <>
              <div className="inspector-section">
                <div className="inspector-section__head">
                  <h3>{entry?.label ?? selectedNode.data.nodeType}</h3>
                  <span className={`palette-item__dot palette-item__dot--${selectedNode.data.category}`} />
                </div>
                <label className="field">
                  <span>Rótulo</span>
                  <input
                    value={selectedNode.data.label}
                    onChange={(event) => patchSelected({ label: event.target.value })}
                  />
                </label>
                <div className="inspector-row">
                  <span>Tipo</span>
                  <span className="mono">{selectedNode.data.nodeType}</span>
                </div>
                <label className="inspector-row">
                  <span>Desativado</span>
                  <input
                    type="checkbox"
                    checked={selectedNode.data.disabled}
                    onChange={(event) => patchSelected({ disabled: event.target.checked })}
                  />
                </label>
                {entry?.description ? <p className="inspector-hint">{entry.description}</p> : null}
              </div>

              <div className="inspector-section">
                <div className="inspector-section__head">
                  <h3>Resiliência</h3>
                </div>
                <label className="field">
                  <span>Tentativas (1–5)</span>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={selectedNode.data.retryAttempts}
                    onChange={(event) =>
                      patchSelected({
                        retryAttempts: Math.min(5, Math.max(1, Number(event.target.value) || 1)),
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>Espera entre tentativas (s)</span>
                  <input
                    type="number"
                    min={0}
                    max={30}
                    value={selectedNode.data.retryDelay}
                    onChange={(event) =>
                      patchSelected({
                        retryDelay: Math.min(30, Math.max(0, Number(event.target.value) || 0)),
                      })
                    }
                  />
                </label>
              </div>

              <div className="inspector-section">
                <div className="inspector-section__head">
                  <h3>Configuração</h3>
                </div>
                {!schema || !schema.properties ? (
                  <p className="inspector-hint">Este nó não expõe configuração editável.</p>
                ) : (
                  <>
                    {Object.entries(schema.properties).map(([field, property]) => {
                      if (selectedNode.data.nodeType === "logic_switch" && field === "cases") {
                        return (
                          <SwitchCasesEditor
                            key={`${selectedNode.id}-cases`}
                            cases={switchCases}
                            onChange={(cases) => setConfigField("cases", cases)}
                          />
                        );
                      }
                      return (
                        <ConfigField
                          key={`${selectedNode.id}-${field}`}
                          field={field}
                          property={property}
                          defs={schema.$defs}
                          value={selectedNode.data.config[field]}
                          credentials={credentials}
                          nodeId={selectedNode.id}
                          onChange={(value) => setConfigField(field, value)}
                        />
                      );
                    })}
                  </>
                )}
              </div>
            </>
          )}
        </aside>
      </div>

      <Modal
        open={versionsOpen}
        title="Histórico de versões"
        description="Cada alteração no grafo gera um snapshot restaurável."
        onClose={() => setVersionsOpen(false)}
        wide
        footer={
          <button type="button" className="button button--ghost" onClick={() => setVersionsOpen(false)}>
            Fechar
          </button>
        }
      >
        {versionsLoading ? (
          <p className="muted">
            <Loader2 size={16} className="spin" /> Carregando versões…
          </p>
        ) : versions.length === 0 ? (
          <div className="alert">Nenhuma versão registrada para este fluxo.</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Versão</th>
                  <th>Quando</th>
                  <th>Grafo</th>
                  <th>Origem</th>
                  <th aria-label="Ações" />
                </tr>
              </thead>
              <tbody>
                {versions.map((item) => {
                  const isCurrent = item.version === workflow.version;
                  return (
                    <tr key={item.id}>
                      <td className="mono">
                        v{item.version}
                        {isCurrent ? <span className="pill pill--live">atual</span> : null}
                      </td>
                      <td className="muted">{formatDate(item.created_at)}</td>
                      <td className="mono">
                        {item.node_count} nós · {item.edge_count} conexões
                      </td>
                      <td className="muted">
                        {VERSION_ORIGIN_LABELS[item.origin] ?? item.origin}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="button button--ghost button--small"
                          onClick={() => void restoreVersion(item.version)}
                          disabled={isCurrent || restoringVersion !== null}
                        >
                          {restoringVersion === item.version ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <RotateCcw size={14} />
                          )}{" "}
                          Restaurar
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <Modal
        open={webhookOpen}
        title="Gatilho por webhook"
        description="Endereço público para iniciar este fluxo via HTTP."
        onClose={() => setWebhookOpen(false)}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={() => setWebhookOpen(false)}>
              Fechar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void rotateSecret()}
              disabled={rotating || !webhook?.node_id}
            >
              {rotating ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />} Rotacionar segredo
            </button>
          </>
        }
      >
        {webhook?.node_id ? (
          <div className="form-stack">
            <div className="webhook-box">
              <span className="muted">Requisição</span>
              <code>
                {webhook.method ?? "POST"} {webhook.url ?? "—"}
              </code>
              <button
                type="button"
                className="link-button"
                onClick={() => void copy(webhook.url, "URL")}
              >
                <Copy size={12} /> copiar URL
              </button>
            </div>
            <p className="muted small">
              {webhook.secret_configured
                ? "Assinatura obrigatória: envie X-Webhook-Secret ou X-Nexus-Signature (HMAC SHA-256 do corpo)."
                : "Nenhum segredo configurado. Gere um para exigir assinatura."}
            </p>
            {webhookSecret ? (
              <div className="webhook-secret">
                <span>Copie agora — o segredo não será mostrado novamente:</span>
                <span>{webhookSecret}</span>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => void copy(webhookSecret, "Segredo")}
                >
                  <Copy size={12} /> copiar segredo
                </button>
              </div>
            ) : null}
            <p className="inspector-hint">
              O nó de gatilho webhook precisa estar ativo no canvas. A URL usa o host da API configurado
              no servidor.
            </p>
          </div>
        ) : (
          <div className="alert">
            Adicione um nó <span className="mono">trigger_webhook</span> ao fluxo e salve para habilitar
            o endereço.
          </div>
        )}
      </Modal>

      <Modal
        open={runOpen}
        title="Executar automação"
        description="A entrada fica disponível para os nós como variáveis do fluxo."
        onClose={() => setRunOpen(false)}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={() => setRunOpen(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void submitRun()}
              disabled={runBusy}
            >
              {runBusy ? <Loader2 size={16} className="spin" /> : <Play size={16} />} Executar agora
            </button>
          </>
        }
      >
        <div className="form-stack">
          <label className="field">
            <span>Entrada (JSON)</span>
            <textarea
              className="run-input"
              value={runInput}
              spellCheck={false}
              onChange={(event) => setRunInput(event.target.value)}
            />
          </label>
          <p className="inspector-hint">
            Exemplo: <span className="mono">{'{"email": "cliente@empresa.com", "plano": "pro"}'}</span>
          </p>
        </div>
      </Modal>

      <Modal
        open={settingsOpen}
        title="Editar automação"
        onClose={() => setSettingsOpen(false)}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={() => setSettingsOpen(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void saveSettings()}
              disabled={settingsBusy}
            >
              {settingsBusy ? <Loader2 size={16} className="spin" /> : <Save size={16} />} Salvar
            </button>
          </>
        }
      >
        <div className="form-stack">
          <label className="field">
            <span>Nome</span>
            <input value={name} maxLength={150} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="field">
            <span>Descrição</span>
            <textarea
              rows={4}
              maxLength={2000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="O que este fluxo resolve?"
            />
          </label>
        </div>
      </Modal>

      <Modal
        open={aiOpen}
        title="Gerar fluxo com IA"
        description="A IA propõe o grafo; nada é salvo até você revisar e confirmar."
        onClose={() => setAiOpen(false)}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={() => setAiOpen(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => void generateGraph()}
              disabled={aiBusy || !aiReady || aiPrompt.trim().length < 3 || !aiProvider}
            >
              {aiBusy ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />} Gerar fluxo
            </button>
          </>
        }
      >
        <div className="form-stack">
          {aiError ? <div className="alert alert--error">{aiError}</div> : null}
          <label className="field">
            <span>Descreva a automação</span>
            <textarea
              rows={4}
              maxLength={2000}
              value={aiPrompt}
              placeholder="Quando chegar um lead no webhook, avalie o plano com IA e notifique o time comercial."
              onChange={(event) => setAiPrompt(event.target.value)}
            />
          </label>
          {!aiProviders ? (
            <p className="inspector-hint">Carregando provedores…</p>
          ) : !aiReady ? (
            <p className="inspector-hint">
              Nenhum provedor de IA configurado. Defina a chave no ambiente (por exemplo,
              <span className="mono"> GEMINI_API_KEY</span>) para habilitar a geração.
            </p>
          ) : (
            <>
              <label className="field">
                <span>Provedor</span>
                <select value={aiProvider} onChange={(event) => chooseProvider(event.target.value)}>
                  {aiProviders.providers.map((provider) => (
                    <option key={provider.name} value={provider.name}>
                      {provider.label}
                      {provider.configured ? "" : " (sem chave)"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Modelo</span>
                <select value={aiModel} onChange={(event) => setAiModel(event.target.value)}>
                  {aiModels.length === 0 ? <option value={aiModel}>{aiModel || "padrão"}</option> : null}
                  {aiModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {nodes.length > 0 ? (
            <p className="inspector-hint">
              O grafo atual ({nodes.length} nós) será substituído ao gerar. Salve só depois de revisar.
            </p>
          ) : null}
        </div>
      </Modal>
    </div>
  );
}
