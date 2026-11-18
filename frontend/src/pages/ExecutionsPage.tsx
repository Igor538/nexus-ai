import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  ArrowDownUp,
  CircleX,
  History,
  Loader2,
  RotateCcw,
  Search,
} from "lucide-react";
import { api } from "../lib/api";
import type {
  ExecutionDetail,
  ExecutionList,
  ExecutionStatus,
  WorkflowSummary,
} from "../lib/types";
import {
  formatDate,
  formatDuration,
  getErrorMessage,
  TRIGGER_LABELS,
} from "../lib/utils";
import { useToast } from "../context/ToastContext";
import { StatusBadge } from "../components/StatusBadge";
import { Modal } from "../components/Modal";

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Todos os status" },
  { value: "success", label: "Concluídas" },
  { value: "failed", label: "Falhas" },
  { value: "running", label: "Em execução" },
  { value: "queued", label: "Na fila" },
  { value: "cancelled", label: "Canceladas" },
];

const ACTIVE_STATUSES = new Set<ExecutionStatus>(["pending", "queued", "running"]);

function JsonBlock({ value, label }: { value: unknown; label: string }) {
  const [open, setOpen] = useState(false);
  const text = value === null || value === undefined ? "—" : JSON.stringify(value, null, 2);
  return (
    <div className="json-block">
      <button type="button" className="json-block__head" onClick={() => setOpen((v) => !v)}>
        <span>{label}</span>
        <span className="mono">{open ? "recolher" : "expandir"}</span>
      </button>
      {open ? <pre>{text}</pre> : null}
    </div>
  );
}

export function ExecutionsPage() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<ExecutionList | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [workflowFilter, setWorkflowFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const detailIdRef = useRef<string | null>(null);

  const highlight = params.get("highlight");

  const load = useCallback(
    async (offset = 0) => {
      setLoading(true);
      try {
        const response = await api.executions({
          workflowId: workflowFilter ? Number(workflowFilter) : undefined,
          status: statusFilter || undefined,
          limit: 50,
          offset,
        });
        setData((current) =>
          offset === 0 || !current
            ? response
            : { ...response, items: [...current.items, ...response.items] },
        );
      } catch (error) {
        notify("error", getErrorMessage(error));
      } finally {
        setLoading(false);
      }
    },
    [workflowFilter, statusFilter, notify],
  );

  useEffect(() => {
    void load(0);
  }, [load]);

  useEffect(() => {
    api.workflows().then(setWorkflows).catch(() => undefined);
  }, []);

  const openDetail = useCallback(
    async (id: number) => {
      setDetailLoading(true);
      try {
        const response = await api.execution(id);
        setDetail(response);
        detailIdRef.current = String(id);
      } catch (error) {
        notify("error", getErrorMessage(error));
      } finally {
        setDetailLoading(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    if (!highlight) {
      setDetail(null);
      return;
    }
    void openDetail(Number(highlight));
  }, [highlight, openDetail]);

  useEffect(() => {
    if (!detail || !ACTIVE_STATUSES.has(detail.status as ExecutionStatus)) return;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api.execution(detail.id);
        setDetail(fresh);
        if (!ACTIVE_STATUSES.has(fresh.status as ExecutionStatus)) {
          void load(0);
        }
      } catch {
        // Keep the current view; the next poll can recover.
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [detail, load]);

  function closeDetail() {
    setDetail(null);
    detailIdRef.current = null;
    if (params.has("highlight")) {
      const next = new URLSearchParams(params);
      next.delete("highlight");
      setParams(next, { replace: true });
    }
  }

  async function retry() {
    if (!detail) return;
    setBusy(true);
    try {
      const execution = await api.retryExecution(detail.id);
      notify("success", `Nova execução #${execution.id} criada.`);
      closeDetail();
      await load(0);
      setParams({ highlight: String(execution.id) });
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!detail) return;
    setBusy(true);
    try {
      const execution = await api.cancelExecution(detail.id);
      setDetail((current) => (current ? { ...current, ...execution } : current));
      notify("success", "Cancelamento solicitado.");
      await load(0);
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const workflowsById = useMemo(
    () => new Map(workflows.map((workflow) => [workflow.id, workflow.name])),
    [workflows],
  );

  return (
    <div className="page">
      <section className="page-head">
        <div>
          <span className="eyebrow">Histórico</span>
          <h2>Execuções</h2>
          <p className="muted">Veja o que rodou, quanto levou e onde falhou.</p>
        </div>
        <span className="count-pill">{data ? `${data.total} no total` : "—"}</span>
      </section>

      <section className="toolbar">
        <div className="workflow-select">
          <Search size={16} />
          <select
            value={workflowFilter}
            onChange={(event) => setWorkflowFilter(event.target.value)}
            aria-label="Filtrar por automação"
          >
            <option value="">Todas as automações</option>
            {workflows.map((workflow) => (
              <option key={workflow.id} value={workflow.id}>
                {workflow.name}
              </option>
            ))}
          </select>
        </div>
        <div className="segmented segmented--wrap" role="group" aria-label="Filtrar por status">
          {STATUS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={statusFilter === option.value ? "is-active" : ""}
              onClick={() => setStatusFilter(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </section>

      {loading && !data ? (
        <div className="skeleton-list">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="skeleton-row" />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="empty-state empty-state--large">
          <History size={24} />
          <strong>Nenhuma execução por aqui</strong>
          <p>Execute uma automação para acompanhar o histórico completo.</p>
        </div>
      ) : (
        <div className="panel panel--flush">
          <div className="table-wrap">
            <table className="data-table data-table--executions">
              <thead>
                <tr>
                  <th>Execução</th>
                  <th>Automação</th>
                  <th>Status</th>
                  <th>Gatilho</th>
                  <th>Passos</th>
                  <th>Duração</th>
                  <th>Início</th>
                  <th aria-label="Ações" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((execution) => (
                  <tr
                    key={execution.id}
                    className="is-clickable"
                    onClick={() => setParams({ highlight: String(execution.id) })}
                  >
                    <td className="mono">#{execution.id}</td>
                    <td>{workflowsById.get(execution.workflow_id) ?? execution.workflow_name ?? `#${execution.workflow_id}`}</td>
                    <td>
                      <StatusBadge status={execution.status} pulse />
                    </td>
                    <td className="muted">{TRIGGER_LABELS[execution.trigger] ?? execution.trigger}</td>
                    <td className="mono">{execution.steps}</td>
                    <td className="mono">{formatDuration(execution.duration_ms)}</td>
                    <td className="muted">{formatDate(execution.created_at)}</td>
                    <td>
                      <span className="row-arrow">ver <ArrowDownUp size={13} /></span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.items.length < data.total ? (
            <div className="load-more">
              <button
                type="button"
                className="button button--ghost"
                onClick={() => void load(data.items.length)}
                disabled={loading}
              >
                {loading ? <Loader2 size={16} className="spin" /> : null} Carregar mais
              </button>
            </div>
          ) : null}
        </div>
      )}

      <Modal
        open={Boolean(detail) || detailLoading}
        title={detail ? `Execução #${detail.id}` : "Carregando execução"}
        description={
          detail
            ? `${workflowsById.get(detail.workflow_id) ?? detail.workflow_name ?? "Automação"} · ${formatDate(detail.created_at)}`
            : undefined
        }
        onClose={closeDetail}
        wide
        footer={
          detail ? (
            <>
              {ACTIVE_STATUSES.has(detail.status as ExecutionStatus) ? (
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => void cancel()}
                  disabled={busy}
                >
                  <CircleX size={16} /> Cancelar execução
                </button>
              ) : null}
              <button type="button" className="button button--primary" onClick={() => void retry()} disabled={busy}>
                <RotateCcw size={16} /> Executar novamente
              </button>
            </>
          ) : undefined
        }
      >
        {detailLoading && !detail ? (
          <p className="muted">Buscando detalhes…</p>
        ) : detail ? (
          <div className="execution-detail">
            <div className="execution-detail__meta">
              <div>
                <span className="eyebrow">Status</span>
                <StatusBadge status={detail.status} pulse />
              </div>
              <div>
                <span className="eyebrow">Gatilho</span>
                <strong>{TRIGGER_LABELS[detail.trigger] ?? detail.trigger}</strong>
              </div>
              <div>
                <span className="eyebrow">Duração</span>
                <strong className="mono">{formatDuration(detail.duration_ms)}</strong>
              </div>
              <div>
                <span className="eyebrow">Passos</span>
                <strong className="mono">{detail.steps}</strong>
              </div>
            </div>

            {detail.error ? <div className="alert alert--error">{detail.error}</div> : null}

            <div className="timeline">
              <h4>Passo a passo</h4>
              {detail.logs.length === 0 ? (
                <p className="empty-note">A execução ainda não registrou passos.</p>
              ) : (
                detail.logs.map((log) => (
                  <details key={log.id} className={`timeline__item timeline__item--${log.status}`}>
                    <summary>
                      <span className="timeline__marker" />
                      <div>
                        <strong>{log.node_name ?? log.node_id ?? "Nó"}</strong>
                        <small className="mono">
                          {log.node_type} · tentativa {log.attempt} · {formatDuration(log.duration_ms)}
                        </small>
                      </div>
                      <StatusBadge status={log.status === "success" ? "success" : log.status} />
                    </summary>
                    <div className="timeline__body">
                      {log.message ? <p>{log.message}</p> : null}
                      {log.error ? <p className="form-error">{log.error}</p> : null}
                      <JsonBlock value={log.input} label="Entrada" />
                      <JsonBlock value={log.output} label="Saída" />
                    </div>
                  </details>
                ))
              )}
            </div>

            <div className="execution-detail__blocks">
              <JsonBlock value={detail.trigger_data} label="Dados do gatilho" />
              <JsonBlock value={detail.input} label="Entrada da execução" />
              <JsonBlock value={detail.output} label="Saída final" />
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
