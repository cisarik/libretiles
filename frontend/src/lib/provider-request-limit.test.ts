import { describe, expect, it, vi } from "vitest";

import { executeAiMoveRequest } from "./ai-move-execution";
import { NextRequest } from "next/server";

describe("AI execution transport boundary", () => {
  it("injects only the scoped backend transport during one execution", async () => {
    const transport = vi.fn(async () => ({ ok: true }));
    const implementation = vi.fn(async () => new Response("ok"));
    await executeAiMoveRequest(
      new NextRequest("http://localhost/api/ai/move", { method: "POST" }),
      implementation,
      transport,
    );
    expect(implementation).toHaveBeenCalledOnce();
    expect(transport).not.toHaveBeenCalled();
  });
});
