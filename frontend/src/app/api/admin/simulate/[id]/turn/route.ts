import { NextRequest } from "next/server";

import { POST as executeAiMoveInternal } from "@/app/api/ai/move/route";
import {
  executeAiMoveRequest,
  type AiMoveBackendRequest,
} from "@/lib/ai-move-execution";
import {
  simulationBackendRequest,
  simulationSse,
} from "@/lib/admin-simulation-server";

function bearerToken(request: NextRequest): string | null {
  const authorization = request.headers.get("authorization") ?? "";
  return authorization.startsWith("Bearer ") ? authorization.slice(7) : null;
}

function gameOperation(path: string): string | null {
  if (path.endsWith("/ai-context/")) return "context";
  if (path.endsWith("/ai-candidates/")) return "candidates";
  if (path.endsWith("/ai-playability/")) return "playability";
  if (path.endsWith("/validate-move/")) return "validate";
  if (path.endsWith("/ai-move/")) return "place";
  if (path.endsWith("/ai-exchange/")) return "exchange";
  if (path.endsWith("/ai-pass/")) return "pass";
  return null;
}

export async function POST(
  request: NextRequest,
  context: RouteContext<"/api/admin/simulate/[id]/turn">,
) {
  const token = bearerToken(request);
  if (!token) {
    return Response.json({ detail: "Authentication credentials were not provided." }, { status: 401 });
  }
  const { id } = await context.params;
  const body = (await request.json().catch(() => null)) as {
    expected_move_count?: unknown;
  } | null;
  if (!body || !Number.isInteger(body.expected_move_count) || Number(body.expected_move_count) < 0) {
    return Response.json({ detail: "expected_move_count must be a non-negative integer." }, { status: 400 });
  }
  const expectedMoveCount = Number(body.expected_move_count);
  const claim = await simulationBackendRequest(
    `/api/admin/simulate/${encodeURIComponent(id)}/step/`,
    token,
    { expected_move_count: expectedMoveCount },
  );
  if (claim.status !== 200) {
    return Response.json(claim.data, { status: claim.status });
  }
  if (claim.data.kind === "cpu") {
    return new Response(
      simulationSse({
        type: "done",
        action: "cpu",
        completion_source: "backend_ranked_candidate",
        turn_provider_requests_used: 0,
        state: claim.data.state,
      }),
      { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform" } },
    );
  }
  if (
    claim.data.kind !== "llm" ||
    typeof claim.data.lease_id !== "string" ||
    typeof claim.data.model_id !== "string"
  ) {
    return Response.json({ detail: "The simulation turn claim was invalid." }, { status: 502 });
  }

  const actionBase = {
    lease_id: claim.data.lease_id,
    expected_move_count: expectedMoveCount,
  };
  const transport: AiMoveBackendRequest = async (path, init) => {
    if (path === "/api/catalog/models/") return null;
    const operation = gameOperation(path);
    if (!operation) {
      if (path.endsWith("/ai-model/")) {
        return { ok: false, error: "Simulation model preferences are immutable." };
      }
      throw new Error(`Unsupported simulation AI operation: ${path}`);
    }
    const source =
      typeof init?.body === "object" && init.body !== null
        ? (init.body as Record<string, unknown>)
        : {};
    const operationPayload: Record<string, unknown> = {};
    if (operation === "validate" || operation === "place") {
      operationPayload.placements = source.placements;
    }
    if (operation === "exchange") operationPayload.letters = source.letters;
    if (operation === "place" || operation === "exchange" || operation === "pass") {
      operationPayload.ai_metadata = source.ai_metadata;
    }
    const action = await simulationBackendRequest(
      `/api/admin/simulate/${encodeURIComponent(id)}/action/`,
      token,
      { operation, ...actionBase, ...operationPayload },
    );
    return action.data;
  };
  const delegated = new NextRequest(request.url.replace(`/api/admin/simulate/${id}/turn`, "/api/ai/move"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      game_id: id,
      token,
      model_id: claim.data.model_id,
      runtime_model_id: claim.data.model_id,
      timeout: claim.data.timeout,
      max_steps: claim.data.max_steps,
    }),
  });
  return executeAiMoveRequest(delegated, executeAiMoveInternal, transport);
}
