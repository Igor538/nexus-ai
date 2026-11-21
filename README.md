# Nexus AI

**Automação de workflows com IA — do rascunho em linguagem natural à execução observável.**

Monte fluxos em um editor de nós, gere um grafo inicial com IA, conecte gatilhos (manual, webhook, agendamento ou evento) e execute ações HTTP, notificações, lógica condicional e blocos de IA. Cada execução tem histórico, detalhe por nó e reprocessamento; credenciais ficam cifradas e webhooks são assinados.

---

## Visão geral

| | |
| --- | --- |
| **Backend** | Python 3.13 · FastAPI · SQLAlchemy 2 · Pydantic v2 · Alembic · PostgreSQL 16 · Redis 7 · Celery |
| **Frontend** | React 19 · TypeScript 5.8 · Vite 7 · React Flow · React Router 7 · lucide-react |
| **Infra** | Docker Compose · nginx (SPA + proxy reverso) |
| **Qualidade** | 34 testes pytest · 15 testes Vitest · 5 cenários Playwright · ruff · ESLint · typecheck |

### Destaques

- **Gerador de fluxo por IA** — descreva o processo em linguagem natural e receba um grafo validado, com os nós posicionados, pronto para editar (`POST /workflows/generate`).
- **Editor visual** — paleta de nós, canvas React Flow, inspetor com formulários dinâmicos a partir do `config_schema` de cada nó.
- **Execução confiável** — modo `inline` para desenvolvimento ou Celery + Redis em produção, com retries, limites de tempo, tamanho de resposta e concorrência por workflow.
- **Gatilhos completos** — manual, webhook com segredo rotacionável e assinatura HMAC, e agendamento por cron/timezone.
- **Versionamento** — histórico do grafo a cada salvamento, comparação e restauração de versões anteriores.
- **Segredo bem guardado** — credenciais cifradas com Fernet e segredos de webhook exibidos apenas na criação/rotação.
- **Observabilidade** — dashboard, notificações, log de execuções e healthcheck.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Início rápido com Docker](#início-rápido-com-docker)
- [Desenvolvimento local](#desenvolvimento-local)
- [Configuração](#configuração)
- [API](#api)
- [Testes e qualidade](#testes-e-qualidade)
- [Segurança](#segurança)
- [Documentação](#documentação)

---

## Arquitetura

```text
                      ┌──────────────────────────┐
   Navegador  ───────▶│ nginx :3000              │
                      │ SPA React + proxy /api   │
                      └────────────┬─────────────┘
                                   │ /api/v1
                      ┌────────────▼─────────────┐        ┌───────────┐
                      │ FastAPI :8000            │───────▶│ Postgres  │
                      │ auth · workflows · IA    │        └───────────┘
                      │ executor · webhooks      │        ┌───────────┐
                      └──────┬────────────┬──────┘───────▶│ Redis     │
                             │            │              └─────┬─────┘
                    inline   │            │ celery              │
                             ▼            ▼                     ▼
                    execução local   worker + beat  ◀────── filas/cron
```

```text
backend/
  app/
    api/            rotas HTTP sob /api/v1
    core/           config, segurança, logging, rate limit, proteção SSRF
    models/         entidades SQLAlchemy
    schemas/        contratos Pydantic
    services/       regras de negócio, executor, nós, credenciais, webhooks, IA
    worker/         Celery (execuções assíncronas e agendamentos)
  alembic/          migrações
  tests/            pytest (34 testes)
frontend/
  src/
    components/     shell, modais, badges, preview de grafo
    context/        autenticação e toasts
    lib/            cliente de API, tipos, utilitários, sessão
    pages/          dashboard, workflows, editor, execuções, credenciais, ajustes, auth
  e2e/              Playwright (5 fluxos ponta a ponta)
  nginx.conf        SPA fallback e proxy /api e /health para api:8000
docker-compose.yml  api · worker · beat · frontend · postgres · redis
```

---

## Início rápido com Docker

**1. Prepare o ambiente.** Copie o modelo de variáveis e gere os dois segredos obrigatórios:

```bash
cp .env.example .env

python -c "import secrets; print(secrets.token_urlsafe(48))"
# → JWT_SECRET_KEY

python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → CREDENTIALS_ENCRYPTION_KEY
```

**2. Suba a stack:**

```bash
docker compose up -d --build
```

**3. Acesse:**

| Serviço | Endereço |
| --- | --- |
| Interface | http://localhost:3000 |
| Documentação interativa | http://localhost:8000/docs |
| Healthcheck | http://localhost:8000/health |

A API aplica as migrações Alembic no start. O `worker` executa as automações e o `beat` dispara os agendamentos (`EXECUTION_MODE=celery` no Compose).

Para desligar tudo: `docker compose down` (use `-v` para remover também o volume do Postgres).

---

## Desenvolvimento local

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

É necessário PostgreSQL e Redis ativos (ou `docker compose up -d postgres redis` com `DATABASE_URL` e `REDIS_URL` ajustados). Para um bootstrap rápido sem Postgres, use SQLite apenas em desenvolvimento:

```bash
set DATABASE_URL=sqlite:///./dev.db
set AUTO_CREATE_TABLES=true
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

O Vite serve em http://localhost:5173 e encaminha `/api` para `http://localhost:8000` (`VITE_PROXY_TARGET` altera o alvo; `VITE_API_URL` aponta para uma API remota).

| Script | O que faz |
| --- | --- |
| `npm run dev` | Servidor de desenvolvimento |
| `npm run build` | `tsc -b` + build de produção |
| `npm run typecheck` | Somente checagem de tipos |
| `npm run lint` | ESLint (TypeScript + React Hooks) |
| `npm test` | Testes unitários (Vitest + jsdom) |
| `npm run preview` | Pré-visualiza o build |
| `npm run test:e2e` | Testes ponta a ponta (Playwright) |

---

## Configuração

Todas as variáveis estão documentadas em [`.env.example`](.env.example). Os grupos principais:

| Grupo | Variáveis | Finalidade |
| --- | --- | --- |
| Autenticação | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_RESET_EXPIRE_MINUTES` | tokens e recuperação de senha |
| Criptografia | `CREDENTIALS_ENCRYPTION_KEY` | cifra credenciais em repouso (Fernet) |
| Execução | `EXECUTION_MODE`, `EXECUTION_TIMEOUT_SECONDS`, `EXECUTION_MAX_STEPS`, `EXECUTION_MAX_OUTPUT_BYTES`, `MAX_ACTIVE_EXECUTIONS_PER_WORKFLOW` | limites e concorrência |
| Rede | `HTTP_*`, `RATE_LIMIT_*`, `WEBHOOK_*`, `CORS_ORIGINS`, `FRONTEND_URL`, `WEBHOOK_BASE_URL` | SSRF, rate limit, assinatura e URLs públicas |
| IA | `AI_DEFAULT_PROVIDER`, `AI_DEFAULT_MODEL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `AI_DAILY_TOKEN_LIMIT` | provedores e cotas do gerador/agente |
| E-mail | `SMTP_*` | notificações por e-mail |

A geração por IA funciona com Gemini, OpenAI, Groq, OpenRouter ou Ollama. Sem nenhuma chave configurada, o modal do gerador informa que não há provedor disponível.

---

## API

Prefixo de todas as rotas: `/api/v1`.

| Grupo | Recursos |
| --- | --- |
| `auth` | registro, login, usuário atual, troca de senha, `/forgot-password`, `/reset-password` |
| `workflows` | CRUD, validação, execução, duplicação, ativar/desativar, webhook (info e rotação), versionamento do grafo (`/versions`, `/{version}`, `/{version}/restore`) e `POST /workflows/generate` |
| `executions` | listagem filtrável, detalhe por nó e reprocessamento |
| `credentials` | CRUD de credenciais cifradas |
| `nodes` | catálogo de nós com `config_schema` para formulários dinâmicos |
| `ai` | provedores/modelos disponíveis e teste de conexão |
| `dashboard`, `notifications`, `health` | métricas, avisos e healthcheck |

Webhook público: `POST /api/v1/webhooks/{token}` aceita `x-webhook-secret` ou assinatura HMAC em `x-nexus-signature`, com limite de corpo configurável.

---

## Testes e qualidade

```bash
# Backend
cd backend
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .

# Frontend
cd frontend
npm test
npm run lint
npm run typecheck
npm run build

# Ponta a ponta — sobe API + Vite em SQLite temporário
npx playwright install chromium
npx playwright test
```

Os 5 fluxos E2E cobrem: ciclo de workflow/versões/restauração, recuperação de senha, webhook + rotação de segredo + agendamento, credenciais e geração de fluxo por IA.

Para testar contra a stack Docker já no ar (nginx e proxy reais):

```bash
cd frontend
$env:PLAYWRIGHT_BASE_URL="http://localhost:3000"   # Linux/macOS: export PLAYWRIGHT_BASE_URL=...
npx playwright test
```

A integração contínua (`.github/workflows/ci.yml`) executa `ruff`, `pytest`, `npm run lint`, `npm test`, `typecheck`, `build` e Playwright a cada push em `main` e em pull requests.

---

## Segurança

- Senhas com Argon2 (`pwdlib`) e JWT com expiração.
- Credenciais cifradas com Fernet; segredos de webhook revelados só na criação/rotação.
- Proteção contra SSRF nas requisições HTTP (`HTTP_ALLOW_PRIVATE_NETWORKS=false`).
- Rate limit no login e nos webhooks, com logs estruturados.
- Cabeçalhos de segurança e cache definidos no nginx.

---

## Documentação

- [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) — estado de implementação e matriz de verificação.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — visão técnica de backend, frontend e execução.
