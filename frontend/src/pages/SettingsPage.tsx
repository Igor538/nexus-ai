import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Cpu, Loader2, LockKeyhole, Sparkles, UserRound } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { api } from "../lib/api";
import type { AIProviderList, AIUsage } from "../lib/types";
import { formatCurrency, formatDate, formatNumber, getErrorMessage } from "../lib/utils";

export function SettingsPage() {
  const { user, setUser } = useAuth();
  const { notify } = useToast();
  const [name, setName] = useState(user?.name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [profileBusy, setProfileBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [providers, setProviders] = useState<AIProviderList | null>(null);
  const [usage, setUsage] = useState<AIUsage | null>(null);

  useEffect(() => {
    api.aiProviders().then(setProviders).catch(() => undefined);
    api.aiUsage(30).then(setUsage).catch(() => undefined);
  }, []);

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setProfileBusy(true);
    try {
      const updated = await api.updateMe({ name: name.trim(), email: email.trim() });
      setUser(updated);
      notify("success", "Perfil atualizado.");
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setProfileBusy(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordBusy(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      notify("success", "Senha alterada.");
    } catch (error) {
      notify("error", getErrorMessage(error));
    } finally {
      setPasswordBusy(false);
    }
  }

  const byModel = (usage?.by_model as Array<Record<string, unknown>> | undefined) ?? [];

  return (
    <div className="page page--settings">
      <section className="page-head">
        <div>
          <span className="eyebrow">Conta</span>
          <h2>Ajustes</h2>
          <p className="muted">Perfil, segurança e o pulso dos provedores de IA.</p>
        </div>
      </section>

      <div className="settings-grid">
        <section className="panel">
          <header className="panel__head">
            <div>
              <span className="eyebrow">Perfil</span>
              <h3>Como você aparece</h3>
            </div>
            <UserRound size={18} className="muted" />
          </header>
          <form className="form-stack" onSubmit={saveProfile}>
            <label className="field">
              <span>Nome</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                minLength={2}
                maxLength={100}
                required
              />
            </label>
            <label className="field">
              <span>E-mail</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <p className="muted small">
              Conta criada em {formatDate(user?.created_at)} · último acesso{" "}
              {formatDate(user?.last_login_at)}
            </p>
            <button type="submit" className="button button--primary" disabled={profileBusy}>
              {profileBusy ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
              Salvar perfil
            </button>
          </form>
        </section>

        <section className="panel">
          <header className="panel__head">
            <div>
              <span className="eyebrow">Segurança</span>
              <h3>Trocar senha</h3>
            </div>
            <LockKeyhole size={18} className="muted" />
          </header>
          <form className="form-stack" onSubmit={changePassword}>
            <label className="field">
              <span>Senha atual</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <label className="field">
              <span>Nova senha</span>
              <input
                type="password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                minLength={8}
                maxLength={128}
                autoComplete="new-password"
                placeholder="Letras e números, 8+"
                required
              />
            </label>
            <p className="muted small">
              O token atual continua válido até expirar. Em caso de dúvida, saia e entre novamente.
            </p>
            <button type="submit" className="button button--ghost" disabled={passwordBusy}>
              {passwordBusy ? <Loader2 size={16} className="spin" /> : <LockKeyhole size={16} />}
              Atualizar senha
            </button>
          </form>
        </section>
      </div>

      <section className="panel">
        <header className="panel__head">
          <div>
            <span className="eyebrow">Modelos</span>
            <h3>Provedores de IA</h3>
          </div>
          <Cpu size={18} className="muted" />
        </header>
        <p className="muted small">
          Padrão atual: <strong>{providers?.default_provider ?? "—"}</strong> · modelo{" "}
          <span className="mono">{providers?.default_model ?? "—"}</span>. Chaves vêm de
          credenciais ou do ambiente do servidor.
        </p>
        <div className="provider-grid">
          {(providers?.providers ?? []).map((provider) => (
            <article key={provider.name} className="provider-card">
              <div className="provider-card__head">
                <strong>{provider.label}</strong>
                {provider.is_default ? <span className="pill pill--live">padrão</span> : null}
              </div>
              <span className={`provider-state ${provider.configured ? "is-on" : ""}`}>
                <i className="dot" /> {provider.configured ? "configurado" : "sem chave"}
              </span>
              <small className="mono">{provider.default_model}</small>
              <div className="field-tags">
                {provider.models.slice(0, 3).map((model) => (
                  <span key={model} className="mono">
                    {model}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <header className="panel__head">
          <div>
            <span className="eyebrow">Consumo</span>
            <h3>Uso de IA nos últimos 30 dias</h3>
          </div>
          <Sparkles size={18} className="muted" />
        </header>
        <div className="usage-stats">
          <div>
            <span className="metric__label">Tokens</span>
            <strong>{formatNumber(Number(usage?.total_tokens ?? 0))}</strong>
          </div>
          <div>
            <span className="metric__label">Custo estimado</span>
            <strong className="mono">{formatCurrency(Number(usage?.cost_usd ?? 0))}</strong>
          </div>
          <div>
            <span className="metric__label">Chamadas</span>
            <strong>{formatNumber(Number(usage?.calls ?? 0))}</strong>
          </div>
          <div>
            <span className="metric__label">Limite diário</span>
            <strong>{formatNumber(Number(usage?.daily_limit ?? 0))}</strong>
          </div>
        </div>
        {byModel.length > 0 ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Provedor</th>
                  <th>Modelo</th>
                  <th>Tokens</th>
                  <th>Chamadas</th>
                  <th>Custo</th>
                </tr>
              </thead>
              <tbody>
                {byModel.map((row) => (
                  <tr key={`${String(row.provider)}-${String(row.model)}`}>
                    <td>{String(row.provider ?? "")}</td>
                    <td className="mono">{String(row.model ?? "")}</td>
                    <td className="mono">{formatNumber(Number(row.total_tokens ?? 0))}</td>
                    <td className="mono">{formatNumber(Number(row.calls ?? 0))}</td>
                    <td className="mono">{formatCurrency(Number(row.cost_usd ?? 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-note">Nenhuma chamada de IA registrada no período.</p>
        )}
      </section>
    </div>
  );
}
