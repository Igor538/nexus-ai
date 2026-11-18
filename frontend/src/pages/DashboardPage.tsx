import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Blocks,
  CalendarClock,
  CirclePlay,
  Clock3,
  Plus,
  RefreshCw,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import type { DashboardStats, WorkflowSummary } from "../lib/types";
import {
  formatDate,
  formatDuration,
  formatNumber,
  formatRelative,
  getErrorMessage,
} from "../lib/utils";
import { StatusBadge } from "../components/StatusBadge";
import { CreateWorkflowModal } from "../components/CreateWorkflowModal";

export function DashboardPage() {
  const { user } = useAuth();
  const { notify } = useToast();
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [running, setRunning] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statsResponse, workflowResponse] = await Promise.all([
        api.dashboard(),
        api.workflows(),
      ]);
      setStats(statsResponse);
      setWorkflows(workflowResponse.slice(0, 4));
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(workflow: WorkflowSummary) {
    setRunning(workflow.id);
    try {
      const execution = await api.runWorkflow(workflow.id);
      notify("success", `Execução #${execution.id} iniciada.`);
      navigate(`/executions?highlight=${execution.id}`);
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setRunning(null);
    }
  }

  const daily = (stats?.daily ?? []).slice(-14);
  const dailyMax = Math.max(
    1,
    ...daily.map(
      (day) =>
        Number(day.success ?? 0) + Number(day.failed ?? 0) + Number(day.cancelled ?? 0),
    ),
  );

  const firstName = (user?.name ?? "por aí").split(" ")[0];

  return (
    <div className="page page--dashboard">
      <section className="hero-strip">
        <div>
          <span className="eyebrow">Olá, {firstName}</span>
          <h2>Suas automações, em movimento.</h2>
          <p className="muted">
            {stats
              ? `${formatNumber(stats.executions.total)} execuções nos últimos 30 dias · ${stats.executions.success_rate}% de sucesso`
              : "Carregando o pulso do workspace…"}
          </p>
        </div>
        <div className="hero-strip__actions">
          <button type="button" className="button button--ghost" onClick={() => void load()}>
            <RefreshCw size={16} className={loading ? "spin" : ""} /> Atualizar
          </button>
          <button type="button" className="button button--primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} /> Nova automação
          </button>
        </div>
      </section>

      <section className="metrics">
        <article className="metric metric--amber">
          <div className="metric__icon">
            <Blocks size={18} />
          </div>
          <span className="metric__label">Automações</span>
          <strong>{stats ? formatNumber(stats.workflows.total) : "—"}</strong>
          <small>{stats ? `${stats.workflows.active} ativas agora` : " "}</small>
        </article>
        <article className="metric metric--teal">
          <div className="metric__icon">
            <Zap size={18} />
          </div>
          <span className="metric__label">Execuções / 30d</span>
          <strong>{stats ? formatNumber(stats.executions.total) : "—"}</strong>
          <small>{stats ? `${stats.executions.success_rate}% concluídas` : " "}</small>
        </article>
        <article className="metric metric--violet">
          <div className="metric__icon">
            <Timer size={18} />
          </div>
          <span className="metric__label">Duração média</span>
          <strong>{stats ? formatDuration(stats.executions.avg_duration_ms) : "—"}</strong>
          <small>do gatilho à última ação</small>
        </article>
        <article className="metric metric--coral">
          <div className="metric__icon">
            <Sparkles size={18} />
          </div>
          <span className="metric__label">Tokens de IA</span>
          <strong>{stats ? formatNumber(stats.ai.tokens) : "—"}</strong>
          <small>{stats ? `${stats.ai.cost_usd.toFixed(2)} USD estimados` : " "}</small>
        </article>
      </section>

      <div className="dashboard-grid">
        <section className="panel panel--activity">
          <header className="panel__head">
            <div>
              <span className="eyebrow">Ritmo</span>
              <h3>Atividade recente</h3>
            </div>
            <Link className="link-button" to="/executions">
              Ver histórico <ArrowUpRight size={14} />
            </Link>
          </header>

          {daily.length === 0 ? (
            <p className="empty-note">Nenhuma execução nos últimos 30 dias.</p>
          ) : (
            <div className="activity-chart" role="img" aria-label="Execuções por dia">
              {daily.map((day) => {
                const success = Number(day.success ?? 0);
                const failed = Number(day.failed ?? 0);
                const cancelled = Number(day.cancelled ?? 0);
                const total = success + failed + cancelled;
                return (
                  <div className="activity-chart__column" key={String(day.date)}>
                    <div className="activity-chart__bars" title={`${total} execuções`}>
                      {success > 0 ? (
                        <span
                          className="bar bar--success"
                          style={{ height: `${(success / dailyMax) * 100}%` }}
                        />
                      ) : null}
                      {failed > 0 ? (
                        <span
                          className="bar bar--failed"
                          style={{ height: `${(failed / dailyMax) * 100}%` }}
                        />
                      ) : null}
                      {cancelled > 0 ? (
                        <span
                          className="bar bar--cancelled"
                          style={{ height: `${(cancelled / dailyMax) * 100}%` }}
                        />
                      ) : null}
                      {total === 0 ? <span className="bar bar--empty" /> : null}
                    </div>
                    <span>{String(day.date).slice(8, 10)}</span>
                  </div>
                );
              })}
            </div>
          )}

          <div className="activity-legend">
            <span><i className="legend-dot legend-dot--success" /> Concluídas</span>
            <span><i className="legend-dot legend-dot--failed" /> Falhas</span>
            <span><i className="legend-dot legend-dot--cancelled" /> Canceladas</span>
          </div>
        </section>

        <section className="panel">
          <header className="panel__head">
            <div>
              <span className="eyebrow">Fila</span>
              <h3>Próximos agendamentos</h3>
            </div>
            <CalendarClock size={18} className="muted" />
          </header>
          {stats?.upcoming_schedules.length ? (
            <ul className="schedule-list">
              {stats.upcoming_schedules.slice(0, 5).map((item) => (
                <li key={`${item.workflow_id}-${item.node_id}`}>
                  <div>
                    <Link to={`/workflows/${item.workflow_id}`}>{item.workflow_name}</Link>
                    <small className="mono">{item.cron} · {item.timezone}</small>
                  </div>
                  <span className="schedule-list__when">{formatRelative(item.next_run_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-note">
              Sem agendas ativas. Adicione um nó de agendamento para rodar no automático.
            </p>
          )}
        </section>
      </div>

      <section className="panel">
        <header className="panel__head">
          <div>
            <span className="eyebrow">Biblioteca</span>
            <h3>Suas automações</h3>
          </div>
          <Link className="link-button" to="/workflows">
            Gerenciar <ArrowUpRight size={14} />
          </Link>
        </header>

        {loading && workflows.length === 0 ? (
          <div className="skeleton-grid">
            {[1, 2, 3].map((item) => (
              <div key={item} className="skeleton-card" />
            ))}
          </div>
        ) : workflows.length === 0 ? (
          <div className="empty-state">
            <Blocks size={22} />
            <strong>Nenhuma automação ainda</strong>
            <p>Comece com um fluxo simples e evolua para algo maior.</p>
            <button type="button" className="button button--primary" onClick={() => setCreateOpen(true)}>
              <Plus size={16} /> Criar primeira automação
            </button>
          </div>
        ) : (
          <div className="workflow-grid">
            {workflows.map((workflow) => (
              <article key={workflow.id} className="workflow-card">
                <div className="workflow-card__top">
                  <span className={`pill ${workflow.is_active ? "pill--live" : ""}`}>
                    {workflow.is_active ? "ativa" : "pausada"}
                  </span>
                  <span className="mono muted">v{workflow.version}</span>
                </div>
                <Link to={`/workflows/${workflow.id}`} className="workflow-card__title">
                  {workflow.name}
                </Link>
                <p className="muted workflow-card__desc">
                  {workflow.description || `${workflow.node_count} nós · ${workflow.edge_count} conexões`}
                </p>
                <div className="workflow-card__preview">
                  <div className="mini-graph">
                    <div className="mini-graph__dots">
                      <span className="signal-dot" />
                      <span className="mono">{workflow.trigger_types.join(" · ") || "manual"}</span>
                    </div>
                    <span className="mini-graph__count">{workflow.node_count} nós</span>
                  </div>
                </div>
                <div className="workflow-card__actions">
                  <button
                    type="button"
                    className="button button--small button--ghost"
                    onClick={() => void run(workflow)}
                    disabled={running === workflow.id || !workflow.is_active}
                    title={workflow.is_active ? "Executar agora" : "Ative a automação para executar"}
                  >
                    <CirclePlay size={15} /> {running === workflow.id ? "Iniciando…" : "Executar"}
                  </button>
                  <Link className="button button--small button--quiet" to={`/workflows/${workflow.id}`}>
                    Abrir editor
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <header className="panel__head">
          <div>
            <span className="eyebrow">Últimas</span>
            <h3>Execuções recentes</h3>
          </div>
          <Clock3 size={18} className="muted" />
        </header>
        {stats?.recent_executions.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Execução</th>
                  <th>Automação</th>
                  <th>Status</th>
                  <th>Gatilho</th>
                  <th>Duração</th>
                  <th>Quando</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_executions.map((execution) => (
                  <tr
                    key={execution.id}
                    onClick={() => navigate(`/executions?highlight=${execution.id}`)}
                    className="is-clickable"
                  >
                    <td className="mono">#{execution.id}</td>
                    <td>{execution.workflow_name ?? `Workflow ${execution.workflow_id}`}</td>
                    <td><StatusBadge status={execution.status} pulse /></td>
                    <td className="muted">{execution.trigger}</td>
                    <td className="mono">{formatDuration(execution.duration_ms)}</td>
                    <td className="muted">{formatDate(execution.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-note">A primeira execução aparece aqui assim que você rodar um fluxo.</p>
        )}
      </section>

      <CreateWorkflowModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => void load()} />
    </div>
  );
}

