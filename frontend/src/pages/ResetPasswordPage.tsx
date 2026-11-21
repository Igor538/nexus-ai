import { useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  KeyRound,
  Loader2,
  LockKeyhole,
  Mail,
} from "lucide-react";
import { api } from "../lib/api";
import { getErrorMessage } from "../lib/utils";

export function ResetPasswordPage() {
  const location = useLocation();
  const [email, setEmail] = useState(
    (location.state as { email?: string } | null)?.email ?? "",
  );
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password !== confirmation) {
      setError("As senhas não coincidem.");
      return;
    }
    setBusy(true);
    try {
      await api.resetPassword(email.trim(), code.trim(), password);
      setDone(true);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth auth--solo">
      <section className="auth__panel">
        <div className="auth__form-wrap">
          <span className="eyebrow">Nova senha</span>
          <h2>Redefinir senha</h2>
          <p className="muted">
            Informe o código que enviamos por e-mail e escolha uma nova senha com letras e
            números, de 8 a 128 caracteres.
          </p>

          {done ? (
            <div className="form-stack">
              <p className="form-success">
                <CheckCircle2 size={18} /> Senha redefinida com sucesso.
              </p>
              <Link className="button button--primary button--block" to="/login">
                Entrar com a nova senha <ArrowRight size={17} />
              </Link>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="form-stack">
              <label className="field">
                <span>E-mail</span>
                <span className="input-with-icon">
                  <Mail size={16} />
                  <input
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="voce@empresa.com"
                    required
                    autoComplete="email"
                  />
                </span>
              </label>

              <label className="field">
                <span>Código de verificação</span>
                <span className="input-with-icon">
                  <KeyRound size={16} />
                  <input
                    type="text"
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                    placeholder="000000"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    minLength={6}
                    maxLength={6}
                    required
                    autoComplete="one-time-code"
                  />
                </span>
              </label>

              <label className="field">
                <span>Nova senha</span>
                <span className="input-with-icon">
                  <LockKeyhole size={16} />
                  <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Letras e números, 8+"
                    minLength={8}
                    maxLength={128}
                    required
                    autoComplete="new-password"
                  />
                </span>
              </label>

              <label className="field">
                <span>Confirmar senha</span>
                <span className="input-with-icon">
                  <LockKeyhole size={16} />
                  <input
                    type="password"
                    value={confirmation}
                    onChange={(event) => setConfirmation(event.target.value)}
                    placeholder="Repita a nova senha"
                    minLength={8}
                    maxLength={128}
                    required
                    autoComplete="new-password"
                  />
                </span>
              </label>

              {error ? <p className="form-error">{error}</p> : null}

              <button
                type="submit"
                className="button button--primary button--block"
                disabled={busy}
              >
                {busy ? <Loader2 size={17} className="spin" /> : null}
                Redefinir senha
                {!busy ? <ArrowRight size={17} /> : null}
              </button>
            </form>
          )}

          {!done ? (
            <p className="auth__switch">
              <Link to="/forgot-password">Solicitar novo código</Link>
              <span className="muted"> · </span>
              <Link to="/login">
                <ArrowLeft size={14} /> Voltar ao login
              </Link>
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
