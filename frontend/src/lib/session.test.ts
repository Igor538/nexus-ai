import { afterEach, describe, expect, it } from "vitest";
import { clearSession, getStoredUser, getToken, saveSession, saveUser } from "./session";
import type { User } from "./types";

const user: User = {
  id: 1,
  name: "Pessoa",
  email: "pessoa@nexus.test",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};

afterEach(() => {
  clearSession();
  localStorage.clear();
});

describe("session storage", () => {
  it("starts empty", () => {
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });

  it("saves and restores the session", () => {
    saveSession("token-123", user);
    expect(getToken()).toBe("token-123");
    expect(getStoredUser()).toEqual(user);

    saveUser({ ...user, name: "Outro nome" });
    expect(getStoredUser()?.name).toBe("Outro nome");
  });

  it("ignores malformed stored users", () => {
    localStorage.setItem("nexus.user", "{not-json");
    expect(getStoredUser()).toBeNull();
  });

  it("clears the session", () => {
    saveSession("token-123", user);
    clearSession();
    expect(getToken()).toBeNull();
    expect(getStoredUser()).toBeNull();
  });
});
