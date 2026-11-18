import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, LockKeyhole } from "lucide-react";
import { api } from "../lib/api";
import { getErrorMessage } from "../lib/utils";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
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
      await api.resetPassword(token, password);
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
          <p className="muted">Escolha uma senha com letras e números, de 8 a 128 caracteres.</p>

          {!token ? (
            <div className="form-stack">
              <p className="form-error">Link inválido ou incompleto. Solicite um novo link.</p>
              <Link className="button button--primary button--block" to="/forgot-password">
                Solicitar novo link <ArrowRight size={17} />
              </Link>
            </div>
          ) : done ? (
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
