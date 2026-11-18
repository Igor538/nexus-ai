import { expect, test } from "@playwright/test";

function uniqueEmail(prefix: string) {
  return `${prefix}.${Date.now()}.${Math.random().toString(36).slice(2, 8)}@example.com`;
}

const REGISTER_PASSWORD = "Senha12345";

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
  await expect(page.getByText("Fluxo salvo.")).toBeVisible();

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
