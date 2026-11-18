# Nexus AI

Plataforma de automação de workflows com IA: monte fluxos por nós, conecte gatilhos (manual, webhook, agendamento, evento), execute ações HTTP, notificações, lógica condicional e blocos de IA — com histórico de execuções, credenciais cifradas e webhooks assinados.

## Stack

| Camada | Tecnologias |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, PostgreSQL 16, Redis 7, Celery |
| Frontend | React 19, TypeScript 5.8, Vite 7, React Flow (`@xyflow/react`), React Router 7, `lucide-react` |
| Infra | Docker Compose, nginx (SPA + proxy `/api`) |

## Estrutura

```
backend/
  app/
    api/            rotas HTTP (/api/v1)
    core/           config, segurança, logging, rate limit, SSRF guard
    models/         entidades SQLAlchemy
    schemas/        contratos Pydantic
    services/       regras de negócio, executor, nós, credenciais, webhooks
    worker/         Celery (execuções assíncronas e agendamentos)
  alembic/          migrações
  tests/            suíte pytest (29 testes)
frontend/
  src/
    components/     shell, modais, badges, preview de grafo
    context/        autenticação e toasts
    lib/            cliente de API, tipos, utilitários, sessão
    pages/          dashboard, workflows, editor, execuções, credenciais, ajustes, login/recuperação de senha
  e2e/              Playwright (cadastro, workflow, versões, reset de senha)
  nginx.conf        SPA fallback e proxy /api e /health -> api:8000
docker-compose.yml  api, worker, beat, frontend, postgres, redis
```

## Requisitos

- Docker + Docker Compose (caminho recomendado), ou
- Node.js 22+ e Python 3.13 para rodar localmente.

## Subir com Docker

1. Copie o ambiente e preencha os segredos:

   ```bash
   cp .env.example .env
   # JWT_SECRET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   # CREDENTIALS_ENCRYPTION_KEY
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. Suba os serviços:

   ```bash
   docker compose up -d --build
   ```

3. Acesse:

   - Frontend: http://localhost:3000
   - API e documentação: http://localhost:8000/docs
   - Healthcheck: http://localhost:8000/health

O serviço `api` aplica as migrações Alembic no start. O worker e o beat do Celery executam as automações e os agendamentos (`EXECUTION_MODE=celery` no compose).

## Desenvolvimento local

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

É necessário PostgreSQL e Redis em execução (ou use `docker compose up -d postgres redis` e ajuste `DATABASE_URL`/`REDIS_URL`).

Frontend:

```bash
cd frontend
npm install
npm run dev
```

O Vite serve em http://localhost:5173 e encaminha `/api` para `http://localhost:8000` (`VITE_PROXY_TARGET` para alterar). Para consumir uma API remota, defina `VITE_API_URL`.

## Scripts do frontend

| Comando | Descrição |
| --- | --- |
| `npm run dev` | Servidor de desenvolvimento |
| `npm run build` | Typecheck (`tsc -b`) + build de produção |
| `npm run typecheck` | Somente verificação de tipos |
| `npm run lint` | ESLint (TypeScript + React Hooks) |
| `npm test` | Testes unitários com Vitest + jsdom |
| `npm run preview` | Pré-visualiza o build |
| `npx playwright test` | Testes E2E (API + Vite automáticos) |

## Testes

Backend:

```bash
cd backend
.venv\Scripts\python -m pytest
.venv\Scripts\python -m ruff check .
```

Frontend:

```bash
cd frontend
npm test
npm run lint
```

Ponta a ponta (Playwright): sobe API + Vite automaticamente em banco SQLite temporário.

```bash
cd frontend
npx playwright install chromium
npx playwright test
```

Para rodar contra a stack Docker já no ar (usa o nginx e o proxy `/api` reais):

```bash
cd frontend
$env:PLAYWRIGHT_BASE_URL="http://localhost:3000"   # Linux/macOS: export ...
npx playwright test
```

A integração contínua em `.github/workflows/ci.yml` roda `ruff`, `pytest`, `npm run lint`, `npm test`, `typecheck` e `build` em cada push para `main` e em pull requests.

## Configuração

As variáveis completas estão em `.env.example`. Destaques:

- `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`: autenticação.
- `CREDENTIALS_ENCRYPTION_KEY`: chave Fernet para cifrar credenciais em repouso.
- `EXECUTION_MODE`: `inline` (dev) ou `celery` (compose).
- `CORS_ORIGINS`, `FRONTEND_URL`, `WEBHOOK_BASE_URL`: origens e URLs públicas.
- `HTTP_*`, `RATE_LIMIT_*`, `WEBHOOK_*`: limites de rede, taxa e assinatura de webhooks.
- `AI_DEFAULT_PROVIDER` / `AI_DEFAULT_MODEL` e chaves `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_BASE_URL`: provedores de IA.
- `SMTP_*`: envio de e-mail no nó de notificação.

## API

Prefixo `/api/v1`. Principais grupos:

- `auth`: registro, login, usuário atual, troca de senha e recuperação de senha (`/forgot-password`, `/reset-password`).
- `workflows`: CRUD, validação, execução, duplicação, ativar/desativar, webhook (info e rotação de segredo) e histórico de versões do grafo (`/versions`, `/{version}`, `/{version}/restore`).
- `executions`: listagem com filtros, detalhe por nó e reprocessamento.
- `credentials`: CRUD de credenciais cifradas.
- `nodes`: catálogo de nós com `config_schema` para formulários dinâmicos.
- `ai`: teste de provedores/modelos.
- `dashboard`, `notifications`, `health`.

Webhooks públicos: `POST /api/v1/webhooks/{token}` aceita `x-webhook-secret` ou assinatura `x-nexus-signature` (HMAC), com limite de corpo configurável.

## Segurança

- Senhas com Argon2 (`pwdlib`), JWT com expiração.
- Credenciais cifradas com Fernet; segredos de webhook só são exibidos na criação/rotação.
- Guarda SSRF nas requisições HTTP (`http_allow_private_networks=false`).
- Rate limit no login e logs estruturados.
- Cabeçalhos de segurança e cache no nginx.

## Documentação

- [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md): estado de implementação e verificação.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): visão técnica de backend, frontend e execução.
