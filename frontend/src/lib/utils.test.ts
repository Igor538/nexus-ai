import { describe, expect, it } from "vitest";
import { deepGet, deepSet, formatDuration, getErrorMessage, truncate } from "./utils";

describe("formatDuration", () => {
  it("formats milliseconds, seconds and minutes", () => {
    expect(formatDuration(500)).toBe("500 ms");
    expect(formatDuration(1500)).toBe("1.5 s");
    expect(formatDuration(65_000)).toBe("1m 5s");
  });

  it("handles absent values", () => {
    expect(formatDuration(null)).not.toBe("");
    expect(formatDuration(undefined)).toBe(formatDuration(null));
  });
});

describe("deepGet / deepSet", () => {
  it("reads nested values and returns undefined for missing paths", () => {
    expect(deepGet({ a: { b: { c: 3 } } }, "a.b.c")).toBe(3);
    expect(deepGet({ a: 1 }, "a.b.c")).toBeUndefined();
  });

  it("sets nested values without mutating the source", () => {
    const source = { a: { b: 1 } };
    const updated = deepSet(source, "a.c", 2);
    expect(updated).toEqual({ a: { b: 1, c: 2 } });
    expect(source).toEqual({ a: { b: 1 } });
  });

  it("creates intermediate objects", () => {
    expect(deepSet({}, "a.b.c", true)).toEqual({ a: { b: { c: true } } });
  });
});

describe("truncate", () => {
  it("keeps short values and trims long ones", () => {
    expect(truncate("curto", 10)).toBe("curto");
    expect(truncate("0123456789", 5)).toHaveLength(5);
  });
});

describe("getErrorMessage", () => {
  it("uses the error message or a fallback", () => {
    expect(getErrorMessage(new Error("falhou"))).toBe("falhou");
    expect(getErrorMessage("texto")).toBe("Algo deu errado. Tente novamente.");
  });
});
