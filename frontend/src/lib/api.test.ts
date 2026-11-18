import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import { clearSession, saveSession } from "./session";

function mockResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearSession();
});

describe("api client", () => {
  it("updates a workflow with PATCH", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(200, { id: 7 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.updateWorkflow(7, { name: "Renomeado" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/7");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ name: "Renomeado" });
  });

  it("sends forgot and reset password requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(200, { detail: "ok" }));
    vi.stubGlobal("fetch", fetchMock);

    await api.forgotPassword("pessoa@nexus.test");
    await api.resetPassword("token-de-recuperacao", "NovaSenha123!");

    const [forgotUrl, forgotInit] = fetchMock.mock.calls[0];
    expect(forgotUrl).toBe("/api/v1/auth/forgot-password");
    expect(forgotInit.method).toBe("POST");
    expect(JSON.parse(forgotInit.body)).toEqual({ email: "pessoa@nexus.test" });

    const [resetUrl, resetInit] = fetchMock.mock.calls[1];
    expect(resetUrl).toBe("/api/v1/auth/reset-password");
    expect(JSON.parse(resetInit.body)).toEqual({
      token: "token-de-recuperacao",
      new_password: "NovaSenha123!",
    });
  });

  it("adds the bearer token from the session", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);
    saveSession("token-abc", {
      id: 1,
      name: "Pessoa",
      email: "pessoa@nexus.test",
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      last_login_at: null,
    });

    await api.workflows();

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.get("Authorization")).toBe("Bearer token-abc");
  });

  it("surfaces API errors with status and message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        mockResponse(422, { error: { message: "Dados inválidos" } }),
      ),
    );

    await expect(api.workflows()).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      message: "Dados inválidos",
    } satisfies Partial<ApiError>);
  });
});
