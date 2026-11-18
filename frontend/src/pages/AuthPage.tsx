import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ArrowRight, Loader2, LockKeyhole, Mail, UserRound } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { getErrorMessage } from "../lib/utils";

interface AuthPageProps {
  mode: "login" | "register";
}

export function AuthPage({ mode }: AuthPageProps) {
  const { user, login, register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "register") {
        await register(name.trim(), email.trim(), password);
      } else {
        await login(email.trim(), password);
      }
      navigate("/", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <section className="auth__stage">
        <div className="auth__brand">
          <span className="logo-mark logo-mark--large">N</span>
          <span>Nexus AI</span>
        </div>
        <div className="auth__statement">
          <span className="eyebrow">Automação que pensa</span>
          <h1>
            Fluxos que trabalham
            <br />
            enquanto você decide.
          </h1>
          <p>
            Conecte gatilhos, ações e modelos de IA em um canvas único. Acompanhe cada passo,
            cada token e cada resultado — sem colar código.
          </p>
        </div>
        <div className="auth__diagram" aria-hidden="true">
          <span className="auth__node auth__node--trigger">gatilho</span>
          <span className="auth__line" />
          <span className="auth__node auth__node--ai">ia</span>
          <span className="auth__line" />
          <span className="auth__node auth__node--action">ação</span>
          <span className="auth__pulse" />
        </div>
        <footer className="auth__foot">
          <span className="signal-dot" /> Motor de execução ativo
        </footer>
      </section>

      <section className="auth__panel">
        <div className="auth__form-wrap">
          <span className="eyebrow">{mode === "login" ? "Bem-vindo de volta" : "Comece agora"}</span>
          <h2>{mode === "login" ? "Entrar no workspace" : "Criar sua conta"}</h2>
          <p className="muted">
            {mode === "login"
              ? "Use o e-mail cadastrado para retomar suas automações."
              : "Gratuito para começar. Seus segredos ficam criptografados no servidor."}
          </p>

          <form onSubmit={onSubmit} className="form-stack">
            {mode === "register" ? (
              <label className="field">
                <span>Nome</span>
                <span className="input-with-icon">
                  <UserRound size={16} />
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Como devemos te chamar?"
                    minLength={2}
                    maxLength={100}
                    required
                    autoComplete="name"
                  />
                </span>
              </label>
            ) : null}

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
              <span>Senha</span>
              <span className="input-with-icon">
                <LockKeyhole size={16} />
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={mode === "register" ? "Letras e números, 8+" : "Sua senha"}
                  minLength={8}
                  maxLength={128}
                  required
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                />
              </span>
              </label>

            {mode === "login" ? (
              <p className="auth__forgot">
                <Link to="/forgot-password">Esqueci minha senha</Link>
              </p>
            ) : null}

            {error ? <p className="form-error">{error}</p> : null}

            <button type="submit" className="button button--primary button--block" disabled={busy}>
              {busy ? <Loader2 size={17} className="spin" /> : null}
              {mode === "login" ? "Entrar" : "Criar conta e entrar"}
              {!busy ? <ArrowRight size={17} /> : null}
            </button>
          </form>

          <p className="auth__switch">
            {mode === "login" ? (
              <>
                Ainda não tem conta? <Link to="/register">Criar agora</Link>
              </>
            ) : (
              <>
                Já tem conta? <Link to="/login">Entrar</Link>
              </>
            )}
          </p>
        </div>
      </section>
    </div>
  );
}
