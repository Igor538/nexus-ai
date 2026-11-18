import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

function uniqueEmail(prefix: string) {
  return `${prefix}.${Date.now()}.${Math.random().toString(36).slice(2, 8)}@example.com`;
}

const REGISTER_PASSWORD = "Senha12345";

async function registerAndLogin(page: Page, request: APIRequestContext, prefix: string) {
  const email = uniqueEmail(prefix);
  const register = await request.post("/api/v1/auth/register", {
    data: { name: "Teste E2E", email, password: REGISTER_PASSWORD },
  });
  expect(register.ok()).toBeTruthy();
  await page.goto("/login");
  await page.getByPlaceholder("voce@empresa.com").fill(email);
  await page.getByPlaceholder("Sua senha").fill(REGISTER_PASSWORD);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await expect(page.getByRole("heading", { name: "Suas automações, em movimento." })).toBeVisible();
  return email;
}

async function expectToast(page: Page, text: string | RegExp) {
  await expect(page.locator(".toast-stack .toast").filter({ hasText: text }).first()).toBeVisible();
}

async function createWorkflow(page: Page, name: string) {
  await page.goto("/workflows");
  await page.getByRole("button", { name: /Criar automa/ }).first().click();
  await page.getByPlaceholder("Ex.: Triagem de leads do site").fill(name);
  await page.getByRole("button", { name: /Criar e abrir editor/ }).click();
  await expect(page).toHaveURL(/\/workflows\/\d+/);
}

test("registra, cria workflow, gera versão e restaura snapshot", async ({ page }) => {
  page.on("pageerror", (error) => console.log("[pageerror]", error.message));
  page.on("console", (message) => {
    if (message.type() === "error") console.log("[console]", message.text());
  });
  page.on("response", async (response) => {
    if (response.url().includes("/api/") && response.status() >= 400) {
      console.log("[api]", response.status(), response.url(), (await response.text()).slice(0, 300));
    }
  });
  const email = uniqueEmail("flow");
  const workflowName = `Automação E2E ${Date.now()}`;

  await page.goto("/register", { waitUntil: "domcontentloaded" });
  await page.getByPlaceholder("Como devemos te chamar?").fill("Teste E2E");
  await page.getByPlaceholder("voce@empresa.com").fill(email);
  await page.getByPlaceholder("Letras e números, 8+").fill(REGISTER_PASSWORD);
  await page.getByRole("button", { name: /Criar conta e entrar/ }).click();
  await expect(page.getByRole("heading", { name: "Suas automações, em movimento." })).toBeVisible();

  await page.goto("/workflows");
  await page.getByRole("button", { name: /Criar automação/ }).first().click();
  await page.getByPlaceholder("Ex.: Triagem de leads do site").fill(workflowName);
  await page.getByRole("button", { name: /Criar e abrir editor/ }).click();
  await expect(page).toHaveURL(/\/workflows\/\d+/);
  await expect(page.getByRole("button", { name: /Salvar/ })).toBeVisible();

  await page.locator(".palette-item").first().click();
  await page.getByRole("button", { name: /Salvar/ }).click();
  await expectToast(page, "Fluxo salvo.");

  await page.getByRole("button", { name: /Histórico/ }).click();
  await expect(page.getByRole("heading", { name: "Histórico de versões" })).toBeVisible();
  const restore = page.locator("button:not([disabled])", { hasText: "Restaurar" }).first();
  await expect(restore).toBeEnabled();
  await restore.click();
  await expect(page.getByText(/restaurada como v\d+/)).toBeVisible();
});

test("recupera senha pelo token de desenvolvimento e entra com a nova senha", async ({ page, request }) => {
  const email = uniqueEmail("reset");
  const register = await request.post("/api/v1/auth/register", {
    data: { name: "Reset E2E", email, password: REGISTER_PASSWORD },
  });
  expect(register.ok()).toBeTruthy();

  await page.goto("/login");
  await page.getByRole("link", { name: "Esqueci minha senha" }).click();
  await page.getByPlaceholder("voce@empresa.com").fill(email);
  await page.getByRole("button", { name: /Enviar instruções/ }).click();
  await expect(page.getByText("Token de desenvolvimento", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /Redefinir agora/ }).click();
  await expect(page).toHaveURL(/\/reset-password\?token=/);
  const newPassword = "NovaSenha9876";
  await page.getByLabel("Nova senha", { exact: true }).fill(newPassword);
  await page.getByLabel("Confirmar senha", { exact: true }).fill(newPassword);
  await page.getByRole("button", { name: /Redefinir senha/ }).click();
  await expect(page.getByText("Senha redefinida com sucesso.")).toBeVisible();

  await page.getByRole("link", { name: /Entrar com a nova senha/ }).click();
  await page.getByPlaceholder("voce@empresa.com").fill(email);
  await page.getByPlaceholder("Sua senha").fill(newPassword);
  await page.getByRole("button", { name: /^Entrar$/ }).click();
  await expect(page.getByRole("heading", { name: "Suas automações, em movimento." })).toBeVisible();
});

test("configura webhook, rotaciona o segredo e agenda a execução", async ({ page, request }) => {
  const workflowName = `Agenda E2E ${Date.now()}`;
  await registerAndLogin(page, request, "schedule");
  await createWorkflow(page, workflowName);

  const paletteFilter = page.locator('input[placeholder^="Filtrar"]');
  await paletteFilter.fill("webhook");
  await page.locator(".editor__palette").getByRole("button", { name: "Webhook", exact: true }).click();
  await page.getByRole("button", { name: /Salvar/ }).click();
  await expectToast(page, /Fluxo salvo/);

  await page.locator(".editor__actions").getByRole("button", { name: /Webhook/ }).click();
  const rotate = page.getByRole("button", { name: /Rotacionar segredo/ });
  await expect(rotate).toBeEnabled();
  await rotate.click();
  await expect(page.locator(".webhook-secret")).toBeVisible();
  await page.locator(".modal__footer").getByRole("button", { name: "Fechar" }).click();

  await paletteFilter.fill("agendamento");
  await page.getByRole("button", { name: "Agendamento", exact: true }).click();
  await page.getByLabel("Cron").fill("*/15 * * * *");
  await page.getByRole("button", { name: /Salvar/ }).click();
  await expectToast(page, /Fluxo salvo/);

  await page.goto("/");
  const scheduled = page.locator(".schedule-list li", { hasText: workflowName });
  await expect(scheduled).toBeVisible();
  await expect(scheduled).toContainText("*/15 * * * *");
});

test("cria e exclui uma credencial criptografada", async ({ page, request }) => {
  await registerAndLogin(page, request, "credential");
  const credentialName = `Chave E2E ${Date.now()}`;

  await page.goto("/credentials");
  await page.getByRole("button", { name: /Nova credencial/ }).first().click();
  await page.getByLabel("Nome", { exact: true }).fill(credentialName);
  await page.locator(".modal select").selectOption("api_key");
  await page.locator('.modal input[type="password"]').fill("sk-test-e2e-123456789");
  await page.getByRole("button", { name: /Salvar/ }).click();
  await expect(page.getByText(/Credencial salva/)).toBeVisible();
  await expect(page.getByText(credentialName)).toBeVisible();

  await page.getByRole("button", { name: `Excluir credencial ${credentialName}` }).click();
  await page.getByRole("button", { name: "Excluir", exact: true }).click();
  await expect(page.getByText(/Credencial removida/)).toBeVisible();
  await expect(page.getByText(credentialName)).toHaveCount(0);
});

test("abre o gerador de fluxo com IA no editor", async ({ page, request }) => {
  await registerAndLogin(page, request, "ai");
  await createWorkflow(page, `IA E2E ${Date.now()}`);

  await page.locator(".editor__actions").getByRole("button", { name: /Gerar com IA/ }).click();
  await expect(page.getByRole("heading", { name: "Gerar fluxo com IA" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Gerar fluxo/ })).toBeVisible();
  await page.getByRole("button", { name: "Fechar", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Gerar fluxo com IA" })).toHaveCount(0);
});
