# Arquitetura

## Visão geral

```
Browser ── nginx (SPA) ──/api/ e /health──> FastAPI (/api/v1, /health)
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                  │
              PostgreSQL           Redis             Celery
             (dados, grafo)    (broker/result)   (execução, schedules)
```

O frontend é uma SPA estática; em produção o nginx serve os assets e faz proxy de `/api` e `/health` para a API. A API é stateless e usa JWT (header `Authorization: Bearer`). O estado vive no PostgreSQL; o Redis é broker/result backend do Celery.

## Backend

### Camadas

- `app/api`: rotas FastAPI, dependências (`deps.py`), validação de entrada e serialização.
- `app/services`: regras de negócio — `workflow_service` (grafo, validação, normalização, redação), `executions` (ciclo de vida), `credentials` (Fernet), `webhooks` (segredo/HMAC), `scheduling` (cron com `croniter`), `expressions` (interpolação `{{ ... }}`), `mailer`.
- `app/services/executor`: `engine.py` percorre o grafo; `context.py` mantém entradas, saídas por nó e variáveis.
- `app/services/nodes`: catálogo extensível (`registry.py`) com `base.py` (contrato) e implementações `triggers`, `logic`, `actions`, `ai`.
- `app/services/ai`: provedores (`gemini`, `openai`/compatíveis), registro, agente, controle de uso e gerador de rascunho de fluxo (prompt → grafo normalizado com layout e issues de validação).
- `app/worker`: `celery_app.py` e `tasks.py` (`run_workflow_task`, `scan_schedules_task`).
- `app/core`: configuração (`pydantic-settings`), banco, segurança/JWT, cifra, logging, rate limit, cliente HTTP com guarda SSRF.

### Modelo de dados

`User`, `Workflow`, `WorkflowVersion`, `Execution`, `NodeExecution`, `Credential`, `Webhook` (por workflow), `ScheduledTask`, `AIUsage` (limite diário de tokens). O grafo do workflow é JSON: `nodes` (id, type, posição, config) e `edges` (source/target, portas de saída). `WorkflowVersion` guarda snapshots imutáveis e sem segredos do grafo a cada alteração (origem `create`, `update`, `restore`, `baseline`), permitindo listar e restaurar versões.

### Execução

1. Gatilho cria uma `Execution` (`pending`) e o grafo é validado.
2. `inline`: a API executa `ExecutionEngine().run(execution_id)`. `celery`: a tarefa é enfileirada e o worker executa.
3. O engine resolve o nó inicial a partir do gatilho, avalia cada nó e segue as portas de saída (`true`/`false` em `logic_if`, `cases` em `logic_switch`), respeitando `EXECUTION_MAX_STEPS` e `EXECUTION_TIMEOUT_SECONDS`.
4. Saídas ficam no contexto e são referenciáveis em configs (`{{ node_id.campo }}`); cada nó grava um `NodeExecution` com status, entrada/saída e erro.
5. Ao final a execução vira `success`/`failed`/`cancelled`. `MAX_ACTIVE_EXECUTIONS_PER_WORKFLOW` evita concorrência por workflow.

Agendamentos: `trigger_schedule` gera `ScheduledTask` com `cron`, timezone e `next_run_at`; o beat chama `scan_schedules_task`, que usa `SELECT ... FOR UPDATE SKIP LOCKED` no PostgreSQL para evitar dupla execução.

Webhooks: cada workflow tem token e segredo cifrado. A rota pública valida `x-webhook-secret` ou `x-nexus-signature` (HMAC-SHA256 do corpo) e respeita o limite de corpo. A rotação gera novo segredo e persiste no grafo normalizado; segredos anteriores são preservados em `normalize_graph` quando o grafo enviado não os contém.

### Segurança

- Senhas com Argon2; JWT assinado com `JWT_SECRET_KEY`.
- Credenciais e segredos de webhook cifrados com Fernet.
- Guarda SSRF no cliente HTTP de ações (bloqueia redes privadas por padrão).
- Rate limit em login; logs estruturados; erros sem vazamento de segredo.
- Grafo sempre `redact_graph` antes de sair da API (nunca devolve `secret_encrypted`).

## Frontend

- `main.tsx`: `StrictMode` → `BrowserRouter` → `ToastProvider` → `AuthProvider` → `App`.
- `App.tsx`: rotas protegidas por `RequireAuth`; `AppShell` compartilha rail de navegação, topbar, notificações e busca de workflows.
- `lib/api.ts`: cliente `fetch` com `API_BASE` (`VITE_API_URL` ou `/api/v1`), `ApiError` tipado e tratamento global de 401 (limpa sessão e redireciona para `/login`).
- `lib/types.ts`: contratos espelhando os schemas Pydantic; `lib/utils.ts`: formatação, labels e mensagens.
- `pages/AuthPage.tsx`, `ForgotPasswordPage.tsx` e `ResetPasswordPage.tsx`: login/cadastro e recuperação de senha (link por e-mail ou token de desenvolvimento quando não há SMTP).
- `pages/WorkflowEditorPage.tsx`: React Flow com nó customizado (`nexus`), handles por output, paleta filtrável pelo catálogo da API, inspetor gerado a partir de `config_schema` (inclui `$defs`, enums, booleanos, listas e JSON), editor de casos do `logic_switch`, validação, ativação, execução, webhook (URL/segredo/rotação), geração de fluxo por IA (prompt + provedor/modelo), organização automática do grafo e proteção contra sair com alterações não salvas.
- Estilos: `styles.css` com tokens (fundo escuro, âmbar/teal/violeta/coral), tipografia Bricolage Grotesque + Inter Tight + IBM Plex Mono, layout responsivo e overrides do React Flow.

## Produção

`docker compose up -d --build` sobe `postgres`, `redis`, `api` (migra e serve), `worker`, `beat` e `frontend` (nginx na porta 3000). `api` e `frontend` têm healthchecks; o frontend depende do healthcheck da API.

## Limitações conhecidas

- Catálogo de nós é estático por tipo; novos nós exigem registro no backend.
- Sem upload de arquivos/anexos.
- Não há editor colaborativo.
- O histórico de versões permite listar e restaurar, mas ainda não há diff visual entre snapshots.
