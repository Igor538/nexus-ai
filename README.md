# Nexus AI

**Automação de workflows com IA — do rascunho em linguagem natural à execução observável.**

Monte fluxos em um editor de nós, gere um grafo inicial com IA, conecte gatilhos (manual, webhook, agendamento ou evento) e execute ações HTTP, notificações, lógica condicional e blocos de IA. Cada execução tem histórico, detalhe por nó e reprocessamento; credenciais ficam cifradas e webhooks são assinados.

---

## Visão geral

Monte fluxos em um editor de nós, gere um grafo inicial com IA, conecte gatilhos (manual, webhook, agendamento ou evento) e execute ações HTTP, notificações, lógica condicional e blocos de IA. Cada execução tem histórico, detalhe por nó e reprocessamento; credenciais ficam cifradas e webhooks são assinados.

---

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
                      ┌──────────────────────────┤
   Navegador  ───────▶│ nginx :3000              │
                      │ SPA React + proxy /api   │
                      └────────────┬─────────────┤
                                   │ /api/v1
                      ┌────────────▼─────────────┤
                      │ FastAPI :8000            │───────▶│ Postgres │
                      │ auth · workflows · IA    │        └───────────┤
                      │ executor · webhooks      │           │ Redis     │
                      └──────┬────────────┬──────┘           └─────┬─────┘
                             │            │ celery               │
                             ▼            ▼                     ▼
                    inline   │            │ celery              │
                             │            ▼                     ▼
                    execução local   worker + beat  ◀────── filas/cron
 ```

```text
 backend/
   app/
     api/            rotas HTTP sob /api/v1
     core/           config, segurança, logging, rate limit, SSRF guard
     core/           config, segurança, logging, rate limit, SSRF guard
     schemas/        validações e esquemas Pydantic v2
     services/       lógica de negócio, e-mail, segurança
     models/         modelos SQLAlchemy 2
     tests/          testes pytest (34 testes)
     docker/         configurações Docker
```

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

## Início rápido com Docker

```bash
# Clonar o repositório
git clone https://github.com/Igor538/nexus-ai.git

# Entrar no diretório
cd nexus-ai

# Subir os containers
docker compose up -d

# Acessar
# Frontend: http://localhost:3000
# API: http://localhost:8000
```

---

## Desenvolvimento local

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v

# Frontend
cd frontend
npm install
npm run dev
```

---

## Configuração

O sistema usa variáveis de ambiente no arquivo `.env` (gitignorado). As configurações principais:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `SMTP_HOST` | Host SMTP para envios | `smtp-relay.brevo.com` |
| `SMTP_PORT` | Porta SMTP | `587` |
| `SMTP_USER` | Usuário SMTP | `seu@email.com` |
| `SMTP_PASSWORD` | Senha SMTP | `(vazio)` |
| `SMTP_FROM` | Remetente | `no-reply@nexus.local` |
| `SMTP_USE_TLS` | Usar TLS | `true` |
| `JWT_SECRET_KEY` | Segredo para JWT | `(gerar)` |
| `CREDENTIALS_ENCRYPTION_KEY` | Chave para cifrar credenciais | `(gerar com Fernet)` |
| `APP_ENV` | Ambiente | `development` |
| `RATE_LIMIT_ENABLED` | Rate limiting | `true` |

---

## API

### Autenticação

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/auth/register` | `POST` | Registrar novo usuário |
| `/api/v1/auth/login` | `POST` | Login de acesso |
| `/api/v1/auth/forgot-password` | `POST` | Solicitar código de redefinição (envia e-mail com código de 6 dígitos) |
| `/api/v1/auth/reset-password` | `POST` | Redefinir senha com código e novo password |

### Workflows

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/workflows` | `POST` | Criar novo workflow |
| `/api/v1/workflows` | `GET` | Listar workflows |
| `/api/v1/workflows/{id}` | `GET` | Obter workflow por ID |
| `/api/v1/workflows/{id}` | `PUT` | Atualizar workflow |
| `/api/v1/workflows/{id}` | `DELETE` | Excluir workflow |

---

## Testes e qualidade

| Ferramenta | Quantidade |
|------------|------------|
| **pytest** | 34 testes |
| **Vitest** | 15 testes |
| **Playwright** | 5 cenários e2e |
| **Ruff** | Linting |
| **ESLint** | Linting React |
| **Typecheck** | TypeScript check |

---

## Segurança

- **Nenhum token/vazado em URL**: O código de redefinição nunca aparece em parâmetros de URL após o envio do e-mail. O fluxo é todo baseado em estado do lado do cliente e verificação no backend.
- **Expiração de 30 minutos**: Configurado em `PASSWORD_RESET_EXPIRE_MINUTES=30`. Após esse tempo, erro `"Código inválido ou expirado."`.
- **Enumeração de e-mail proteção**: A resposta do `forgot-password` sempre é `"Se o e-mail existir, enviaremos instruções."` — não revela se o e-mail existe ou não.
- **Código de uso único**: Cada código pode ser usado somente uma vez; tentativas repetidas falham.
- **SMTP Brevo**: Login testado (`LOGIN_OK`) e envio de teste (`SENT_OK`) verificado. Remetente verificado: `Nexus AI <nexusai908@gmail.com>`.

---

## Documentação

- `docs/ARCHITECTURE.md` — Arquitetura detalhada do sistema
- `docs/IMPLEMENTATION_STATUS.md` — Status de implementação de features

---

## Licença

Este projeto está licenciado sob a licença MIT.