import { expect, it } from "vitest";

import { adminNavigationState } from "./AdminNavigation";

it("identifies each live admin section and compact replay id", () => {
  expect(adminNavigationState("/admin").games).toBe(true);
  expect(adminNavigationState("/admin/playground").playground).toBe(true);
  expect(adminNavigationState("/admin/analytics").analytics).toBe(true);
  expect(adminNavigationState("/admin/replay/123e4567-e89b-42d3-a456-426614174000").replayId).toBe("123e4567e89b");
});
