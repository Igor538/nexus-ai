import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, Plus } from "lucide-react";
import { Modal } from "./Modal";
import { api } from "../lib/api";
import { useToast } from "../context/ToastContext";
import { getErrorMessage } from "../lib/utils";

export function CreateWorkflowModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated?: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();
  const navigate = useNavigate();

  async function submit() {
    if (name.trim().length < 2) {
      notify("error", "Dê um nome com pelo menos 2 caracteres.");
      return;
    }
    setBusy(true);
    try {
      const workflow = await api.createWorkflow(name.trim(), description.trim());
      notify("success", "Automação criada. Vamos montar o fluxo.");
      setName("");
      setDescription("");
      onClose();
      onCreated?.();
      navigate(`/workflows/${workflow.id}`);
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Nova automação"
      description="Começamos com um gatilho manual e uma notificação de conclusão. Você pode trocar tudo no editor."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button button--ghost" onClick={onClose}>
            Cancelar
          </button>
          <button type="button" className="button button--primary" onClick={submit} disabled={busy}>
            {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
            Criar e abrir editor
          </button>
        </>
      }
    >
      <div className="form-stack">
        <label className="field">
          <span>Nome</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Ex.: Triagem de leads do site"
            maxLength={150}
            autoFocus
          />
        </label>
        <label className="field">
          <span>Descrição <small className="muted">(opcional)</small></span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="O que este fluxo resolve?"
            rows={3}
            maxLength={2000}
          />
        </label>
      </div>
    </Modal>
  );
}
