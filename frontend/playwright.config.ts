import { defineConfig, devices } from "@playwright/test";

const python = process.env.NEXUS_PYTHON ?? "python";
const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const testEncryptionKey =
  process.env.CREDENTIALS_ENCRYPTION_KEY ?? "ztiFG5_pUbuT3hLqXyryoNiFnBxIs09hRlYMNxquoyw=";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  timeout: 90_000,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: externalBaseURL ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: externalBaseURL
    ? undefined
    : [
        {
          command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
          cwd: "../backend",
          url: "http://127.0.0.1:8000/health",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            DATABASE_URL: "sqlite:///./e2e-playwright.db",
            AUTO_CREATE_TABLES: "true",
            EXECUTION_MODE: "inline",
            RATE_LIMIT_ENABLED: "false",
            SMTP_HOST: "",
            CREDENTIALS_ENCRYPTION_KEY: testEncryptionKey,
          },
        },
        {
          command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
          url: "http://127.0.0.1:5173",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
          env: {
            VITE_PROXY_TARGET: "http://127.0.0.1:8000",
          },
        },
      ],
});
