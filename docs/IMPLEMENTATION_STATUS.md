# Estado de implementação

Atualizado após a rodada de finalização. Legenda: `[x]` concluído e verificado, `[~]` implementado sem verificação automatizada, `[ ]` pendente.

## Backend

- [x] Configuração (`pydantic-settings`), banco, logging estruturado.
- [x] Autenticação JWT, hash Argon2, rate limit, troca de senha.
- [x] CRUD de workflows, validação e normalização de grafo, duplicação, ativação.
- [x] Catálogo de nós e `config_schema` (gatilhos, HTTP, notificação, lógica, IA).
- [x] Executor com contexto, expressões, portas de saída, limites de passos/tempo.
- [x] Execução inline e assíncrona (Celery), histórico por nó e reprocessamento.
- [x] Credenciais cifradas com Fernet.
- [x] Webhooks com token, segredo e assinatura HMAC; rotação de segredo.
- [x] Agendamentos cron com `ScheduledTask` e varredura pelo beat.
- [x] Provedores de IA (Gemini e OpenAI/compatíveis), agente e limite diário de tokens.
- [x] Geração de rascunho de fluxo por IA (`POST /workflows/generate`): prompt → grafo normalizado (ids únicos, tipos válidos, limites de nós/arestas, layout), issues de validação, quota e registro de uso.
- [x] E-mail de notificação via SMTP.
- [x] Migrações Alembic; imagem Docker do backend.
- [x] Histórico de versões do grafo (`workflow_versions`): snapshot a cada alteração, listagem, leitura e restauração.
- [x] Catálogo de nós estável mesmo com campos obrigatórios (defaults derivados dos campos opcionais).
- [x] Suíte pytest: **34 passed**; `ruff check app tests` limpo.

## Frontend

- [x] Entrypoints (`main.tsx`, `App.tsx`), rotas protegidas e fallback.
- [x] Design system completo em `styles.css` (tokens, layout, tabelas, modais, toasts, editor, responsivo).
- [x] Shell com navegação, topbar, busca e notificações.
- [x] Login, cadastro, sessão persistida e recuperação de senha (`/forgot-password`, `/reset-password`, código de 6 dígitos por SMTP).
- [x] Dashboard com métricas e atividade.
- [x] Lista de workflows com busca, filtros, criação, duplicação, ativação e exclusão.
- [x] Editor React Flow: paleta, conexões, inspetor dinâmico por schema, `logic_switch`, validação, execução, webhook, auto-layout, dirty state e atalhos.
- [x] Geração de fluxo por IA no editor: modal com prompt, seleção de provedor/modelo, substituição do grafo com aviso e feedback de issues.
- [x] Páginas de execuções, credenciais e ajustes.
- [x] Cancelamento de execuções em andamento na UI.
- [x] Histórico de versões no editor (listar e restaurar snapshots).
- [x] `typecheck` limpo; `ESLint` sem erros.
- [x] Testes unitários com Vitest (utilitários, sessão e cliente de API): **15 passed**.
- [x] Build de produção limpo (chunks separados para React e React Flow).
- [x] Dockerfile multi-stage + `nginx.conf` (SPA, proxy `/api` e `/health`, healthcheck).
- [x] Testes E2E com Playwright: **5 passed** (workflow → versão → restauração; reset de senha; webhook/rotação/agendamento; credenciais; modal do gerador IA), rodando em Vite+SQLite e contra a stack Docker.
- [x] Alinhamento do editor ao contrato do grafo (`retry_attempts` 1–5, `retry_delay_seconds` 0–30).
- [x] Link "Status da API" aponta para `/health` com proxy no Vite e no nginx.

## Infra e documentação

- [x] `docker-compose.yml` com `api`, `worker`, `beat`, `frontend`, `postgres`, `redis`.
- [x] `.env.example` cobrindo autenticação, execução, HTTP, webhooks, rate limit, IA e SMTP.
- [x] `.gitignore`, `.dockerignore` do frontend; pasta `docker/` vazia removida.
- [x] `docker-compose.yml` usa `AUTO_CREATE_TABLES=false` (migrações via Alembic no start).
- [x] `README.md` com setup local, Docker, scripts e segurança.
- [x] CI em `.github/workflows/ci.yml` (ruff, pytest, lint, testes, typecheck, build e E2E).
- [x] `docs/ARCHITECTURE.md` e este status.

## Verificações executadas

| Comando | Resultado |
| --- | --- |
| `cd frontend && npm install` | sucesso (dependências de lint e teste incluídas) |
| `npm run typecheck` | sem erros |
| `npm run lint` | 0 erros (2 avisos de fast refresh) |
| `npm test` | 15 passed |
| `npm run build` | sucesso (CSS 50,81 kB; JS dividido em `react`, `flow`, `index`) |
| `cd backend && python -m venv .venv` + `pip install -r requirements-dev.txt` | sucesso |
| `ruff check .` | All checks passed |
| `pytest` | 34 passed |
| `alembic upgrade head` (SQLite limpo) | 0001 → 0002 aplicadas, `workflow_versions` criada |
| `npx playwright test` | 5 passed (Vite + SQLite temporário) |
| `npx playwright test` com `PLAYWRIGHT_BASE_URL` | 5 passed (frontend nginx + API + Celery no Docker) |
| `docker compose build` + `up -d` | 6 serviços saudáveis; smoke HTTP real: registro, login, workflow, execução `success`, catálogo (21 nós) e versões |

## Pendências e próximos passos

- [x] Teste ponta a ponta no navegador (criar workflow, executar, restaurar versão; reset de senha).
- [x] Validar `docker compose up --build` em ambiente limpo.
- [x] Geração de fluxo por IA no editor (endpoint dedicado com normalização, validação e limites).
- [x] Mais casos E2E: webhook/rotação de segredo/agendamento, credenciais e modal do gerador IA.
