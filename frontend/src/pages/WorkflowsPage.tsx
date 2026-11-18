import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Blocks,
  CirclePlay,
  Copy,
  Pause,
  Play,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { api } from "../lib/api";
import type { WorkflowSummary } from "../lib/types";
import { formatRelative, getErrorMessage } from "../lib/utils";
import { useToast } from "../context/ToastContext";
import { CreateWorkflowModal } from "../components/CreateWorkflowModal";
import { Modal } from "../components/Modal";

export function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "paused">("all");
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleting, setDeleting] = useState<WorkflowSummary | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const { notify } = useToast();
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setWorkflows(await api.workflows());
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return workflows.filter((workflow) => {
      if (filter === "active" && !workflow.is_active) return false;
      if (filter === "paused" && workflow.is_active) return false;
      if (!term) return true;
      return (
        workflow.name.toLowerCase().includes(term) ||
        (workflow.description ?? "").toLowerCase().includes(term)
      );
    });
  }, [workflows, search, filter]);

  async function toggle(workflow: WorkflowSummary) {
    setBusyId(workflow.id);
    try {
      await api.updateWorkflow(workflow.id, { is_active: !workflow.is_active });
      notify("success", workflow.is_active ? "Automação pausada." : "Automação ativada.");
      await load();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  async function run(workflow: WorkflowSummary) {
    setBusyId(workflow.id);
    try {
      const execution = await api.runWorkflow(workflow.id);
      notify("success", `Execução #${execution.id} iniciada.`);
      navigate(`/executions?highlight=${execution.id}`);
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  async function duplicate(workflow: WorkflowSummary) {
    setBusyId(workflow.id);
    try {
      await api.duplicateWorkflow(workflow.id, `${workflow.name} (cópia)`);
      notify("success", "Automação duplicada.");
      await load();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusyId(deleting.id);
    try {
      await api.deleteWorkflow(deleting.id);
      notify("success", "Automação removida.");
      setDeleting(null);
      await load();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page">
      <section className="page-head">
        <div>
          <span className="eyebrow">Biblioteca</span>
          <h2>Todas as automações</h2>
          <p className="muted">Organize, ative e execute seus fluxos sem sair da lista.</p>
        </div>
        <button type="button" className="button button--primary" onClick={() => setCreateOpen(true)}>
          <Plus size={16} /> Nova automação
        </button>
      </section>

      <section className="toolbar">
        <div className="search">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome ou descrição"
            aria-label="Buscar automações"
          />
        </div>
        <div className="segmented" role="group" aria-label="Filtrar por status">
          <button
            type="button"
            className={filter === "all" ? "is-active" : ""}
            onClick={() => setFilter("all")}
          >
            Todas
          </button>
          <button
            type="button"
            className={filter === "active" ? "is-active" : ""}
            onClick={() => setFilter("active")}
          >
            Ativas
          </button>
          <button
            type="button"
            className={filter === "paused" ? "is-active" : ""}
            onClick={() => setFilter("paused")}
          >
            Pausadas
          </button>
        </div>
      </section>

      {loading ? (
        <div className="skeleton-list">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="skeleton-row" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state empty-state--large">
          <Blocks size={24} />
          <strong>{workflows.length === 0 ? "Comece sua biblioteca" : "Nada com esse filtro"}</strong>
          <p>
            {workflows.length === 0
              ? "Crie um fluxo com gatilho manual e evolua a partir dele."
              : "Ajuste a busca ou o filtro de status para encontrar o fluxo."}
          </p>
          {workflows.length === 0 ? (
            <button type="button" className="button button--primary" onClick={() => setCreateOpen(true)}>
              <Plus size={16} /> Criar automação
            </button>
          ) : null}
        </div>
      ) : (
        <div className="workflow-table">
          {filtered.map((workflow) => (
            <article key={workflow.id} className="workflow-row">
              <div className={`workflow-row__signal ${workflow.is_active ? "is-live" : ""}`}>
                <span />
              </div>
              <div className="workflow-row__main">
                <Link to={`/workflows/${workflow.id}`} className="workflow-row__title">
                  {workflow.name}
                </Link>
                <p className="muted">
                  {workflow.description || "Sem descrição — abra o editor para dar contexto."}
                </p>
                <div className="workflow-row__meta">
                  <span className={`pill ${workflow.is_active ? "pill--live" : ""}`}>
                    {workflow.is_active ? "ativa" : "pausada"}
                  </span>
                  <span>{workflow.node_count} nós</span>
                  <span>{workflow.edge_count} conexões</span>
                  <span className="mono">v{workflow.version}</span>
                  <span>atualizada {formatRelative(workflow.updated_at)}</span>
                </div>
              </div>
              <div className="workflow-row__actions">
                <button
                  type="button"
                  className="button button--small button--ghost"
                  onClick={() => void run(workflow)}
                  disabled={busyId === workflow.id || !workflow.is_active}
                  title="Executar agora"
                >
                  <CirclePlay size={15} /> Executar
                </button>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => void toggle(workflow)}
                  disabled={busyId === workflow.id}
                  aria-label={workflow.is_active ? "Pausar automação" : "Ativar automação"}
                  title={workflow.is_active ? "Pausar" : "Ativar"}
                >
                  {workflow.is_active ? <Pause size={17} /> : <Play size={17} />}
                </button>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => void duplicate(workflow)}
                  disabled={busyId === workflow.id}
                  aria-label="Duplicar automação"
                  title="Duplicar"
                >
                  <Copy size={17} />
                </button>
                <button
                  type="button"
                  className="icon-button icon-button--danger"
                  onClick={() => setDeleting(workflow)}
                  aria-label="Excluir automação"
                  title="Excluir"
                >
                  <Trash2 size={17} />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <CreateWorkflowModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => void load()} />

      <Modal
        open={Boolean(deleting)}
        title="Excluir automação?"
        description={
          deleting
            ? `"${deleting.name}" e seu histórico de execuções serão removidos. Esta ação não pode ser desfeita.`
            : undefined
        }
        onClose={() => setDeleting(null)}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={() => setDeleting(null)}>
              Manter
            </button>
            <button
              type="button"
              className="button button--danger"
              onClick={() => void confirmDelete()}
              disabled={busyId === deleting?.id}
            >
              Excluir definitivamente
            </button>
          </>
        }
      >
        <p className="muted">Dica: pause em vez de excluir se quiser apenas parar as execuções.</p>
      </Modal>
    </div>
  );
}
