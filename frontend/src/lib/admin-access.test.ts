import { describe, expect, it } from "vitest";
import { safeAdminCallback } from "./admin-access";

describe("safeAdminCallback", () => {
  it.each(["/admin", "/admin/playground", "/admin/analytics", "/admin/replay/123e4567-e89b-42d3-a456-426614174000"])("allows %s", (path) => expect(safeAdminCallback(path)).toBe(path));
  it.each(["https://evil.test/admin", "//evil.test", "/admin\\replay", "/admin/login", "/admin/replay/nope", "/admin?x=1"])("rejects %s", (path) => expect(safeAdminCallback(path)).toBe("/admin"));
});
