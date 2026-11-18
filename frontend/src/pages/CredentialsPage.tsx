import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Database, KeyRound, Loader2, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Credential } from "../lib/types";
import { formatDate, getErrorMessage } from "../lib/utils";
import { useToast } from "../context/ToastContext";
import { Modal } from "../components/Modal";

interface CredentialType {
  type: string;
  label: string;
  fields: Array<{ name: string; secret: boolean }>;
}

const PROVIDER_HINTS: Record<string, string> = {
  openai: "Chave da OpenAI (paga).",
  gemini: "Chave do Google AI Studio (free tier).",
  groq: "Chave da Groq (free tier).",
  openrouter: "Chave do OpenRouter (modelos :free).",
  http: "Cabeçalhos para APIs externas.",
  smtp: "Servidor de e-mail para notificações.",
};

export function CredentialsPage() {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [types, setTypes] = useState<CredentialType[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState<Credential | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState("openai");
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const { notify } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [credentialList, typeList] = await Promise.all([
        api.credentials(),
        api.credentialTypes(),
      ]);
      setCredentials(credentialList);
      setTypes(typeList.types);
      if (typeList.types.length > 0 && !typeList.types.some((item) => item.type === type)) {
        setType(typeList.types[0].type);
      }
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [notify, type]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedType = useMemo(
    () => types.find((item) => item.type === type) ?? null,
    [types, type],
  );

  function resetForm() {
    setName("");
    setValues({});
    setOpen(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selectedType) return;
    const data: Record<string, unknown> = {};
    for (const field of selectedType.fields) {
      const value = values[field.name]?.trim();
      if (!value) {
        notify("error", `Preencha o campo "${field.name}".`);
        return;
      }
      data[field.name] = value;
    }
    setBusy(true);
    try {
      await api.createCredential({ name: name.trim(), type, data });
      notify("success", "Credencial salva e criptografada.");
      resetForm();
      await load();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    try {
      await api.deleteCredential(deleting.id);
      notify("success", "Credencial removida.");
      setDeleting(null);
      await load();
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <section className="page-head">
        <div>
          <span className="eyebrow">Cofre</span>
          <h2>Credenciais</h2>
          <p className="muted">
            Chaves e segredos ficam criptografados no servidor. O valor nunca volta para a tela.
          </p>
        </div>
        <button type="button" className="button button--primary" onClick={() => setOpen(true)}>
          <Plus size={16} /> Nova credencial
        </button>
      </section>

      <div className="credential-note">
        <ShieldCheck size={18} />
        <p>
          Use credenciais no lugar de chaves fixas nos nós. Elas são cifradas com AES/Fernet e só
          são descriptografadas no momento da execução.
        </p>
      </div>

      {loading ? (
        <div className="skeleton-list">
          {[1, 2, 3].map((item) => (
            <div key={item} className="skeleton-row" />
          ))}
        </div>
      ) : credentials.length === 0 ? (
        <div className="empty-state empty-state--large">
          <Database size={24} />
          <strong>Nenhuma credencial guardada</strong>
          <p>Adicione chaves de IA ou tokens de API para usar nos fluxos.</p>
          <button type="button" className="button button--primary" onClick={() => setOpen(true)}>
            <Plus size={16} /> Adicionar credencial
          </button>
        </div>
      ) : (
        <div className="credential-grid">
          {credentials.map((credential) => (
            <article key={credential.id} className="credential-card">
              <div className="credential-card__icon">
                <KeyRound size={20} />
              </div>
              <div className="credential-card__body">
                <strong>{credential.name}</strong>
                <span className="pill">{credential.type}</span>
                <small className="muted">criada em {formatDate(credential.created_at)}</small>
                <div className="field-tags">
                  {credential.fields.map((field) => (
                    <span key={field} className="mono">
                      {field}
                    </span>
                  ))}
                </div>
              </div>
              <button
                type="button"
                className="icon-button icon-button--danger"
                onClick={() => setDeleting(credential)}
                aria-label={`Excluir credencial ${credential.name}`}
              >
                <Trash2 size={17} />
              </button>
            </article>
          ))}
        </div>
      )}

      <Modal
        open={open}
        title="Nova credencial"
        description="O payload é validado por tipo e cifrado antes de tocar o banco."
        onClose={resetForm}
        footer={
          <>
            <button type="button" className="button button--ghost" onClick={resetForm}>
              Cancelar
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={(event) => void submit(event as unknown as FormEvent)}
              disabled={busy}
            >
              {busy ? <Loader2 size={16} className="spin" /> : <ShieldCheck size={16} />} Salvar
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
              placeholder="Ex.: Gemini produção"
              maxLength={120}
              autoFocus
            />
          </label>
          <label className="field">
            <span>Tipo</span>
            <select
              value={type}
              onChange={(event) => {
                setType(event.target.value);
                setValues({});
              }}
            >
              {types.map((item) => (
                <option key={item.type} value={item.type}>
                  {item.label}
                </option>
              ))}
            </select>
            {PROVIDER_HINTS[type] ? <small className="muted">{PROVIDER_HINTS[type]}</small> : null}
          </label>
          {selectedType?.fields.map((field) => (
            <label className="field" key={field.name}>
              <span>
                {field.name}
                {field.secret ? <small className="muted"> · secreto</small> : null}
              </span>
              <input
                type={field.secret ? "password" : "text"}
                value={values[field.name] ?? ""}
                onChange={(event) =>
                  setValues((current) => ({ ...current, [field.name]: event.target.value }))
                }
                autoComplete="off"
                placeholder={field.secret ? "••••••••" : field.name}
              />
            </label>
          ))}
        </div>
      </Modal>

      <Modal
        open={Boolean(deleting)}
        title="Excluir credencial?"
        description={
          deleting
            ? `"${deleting.name}" pode estar em uso por automações ativas. Elas vão falhar sem ela.`
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
              disabled={busy}
            >
              Excluir
            </button>
          </>
        }
      >
        <p className="muted">A remoção é definitiva.</p>
      </Modal>
    </div>
  );
}
