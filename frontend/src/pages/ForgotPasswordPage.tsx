import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, Mail } from "lucide-react";
import { api } from "../lib/api";
import { getErrorMessage } from "../lib/utils";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ detail: string; dev_token?: string } | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      setResult(await api.forgotPassword(email.trim()));
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
          <span className="eyebrow">Recuperação de acesso</span>
          <h2>Esqueceu a senha?</h2>
          <p className="muted">
            Informe o e-mail cadastrado e enviaremos um link para criar uma nova senha.
          </p>

          {result ? (
            <div className="form-stack">
              <p className="form-success">{result.detail}</p>
              {result.dev_token ? (
                <div className="auth__note">
                  <span>Token de desenvolvimento</span>
                  <code>{result.dev_token}</code>
                  <Link
                    className="button button--primary button--block"
                    to={`/reset-password?token=${encodeURIComponent(result.dev_token)}`}
                  >
                    Redefinir agora <ArrowRight size={17} />
                  </Link>
                </div>
              ) : null}
              <Link className="button button--ghost button--block" to="/login">
                <ArrowLeft size={17} /> Voltar ao login
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

              {error ? <p className="form-error">{error}</p> : null}

              <button
                type="submit"
                className="button button--primary button--block"
                disabled={busy}
              >
                {busy ? <Loader2 size={17} className="spin" /> : null}
                Enviar instruções
                {!busy ? <ArrowRight size={17} /> : null}
              </button>
            </form>
          )}

          {!result ? (
            <p className="auth__switch">
              <Link to="/login">Voltar ao login</Link>
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
