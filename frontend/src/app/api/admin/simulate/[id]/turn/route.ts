import { NextRequest } from "next/server";

import { POST as executeAiMoveInternal } from "@/app/api/ai/move/route";
import {
  executeAiMoveRequest,
  type AiMoveBackendRequest,
} from "@/lib/ai-move-execution";
import { bearerTokenFromAuthorizationHeader } from "@/lib/api-auth";
import {
  projectedSimulationError,
  simulationBackendRequest,
  simulationSse,
} from "@/lib/admin-simulation-server";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const INVALID_RESPONSE_DETAIL =
  "The simulation backend returned an invalid response.";
const JSON_HEADERS = {
  "Cache-Control": "private, no-store",
  Vary: "Authorization",
};
const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "private, no-store, no-transform",
  Vary: "Authorization",
};

function jsonError(status: number, body: Record<string, unknown>): Response {
  return Response.json(body, { status, headers: JSON_HEADERS });
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
  const token = bearerTokenFromAuthorizationHeader(
    request.headers.get("authorization"),
  );
  if (!token) {
    return jsonError(401, {
      detail: "Authentication credentials were not provided.",
    });
  }
  const { id } = await context.params;
  if (typeof id !== "string" || !UUID_PATTERN.test(id)) {
    return jsonError(404, { detail: "Not found." });
  }
  const body = (await request.json().catch(() => null)) as {
    expected_move_count?: unknown;
  } | null;
  if (
    !body ||
    !Number.isInteger(body.expected_move_count) ||
    Number(body.expected_move_count) < 0
  ) {
    return jsonError(400, {
      detail: "expected_move_count must be a non-negative integer.",
    });
  }
  const expectedMoveCount = Number(body.expected_move_count);
  const claim = await simulationBackendRequest(
    `/api/admin/simulate/${id}/step/`,
    token,
    { expected_move_count: expectedMoveCount },
  );
  if (claim.status !== 200) {
    const projected = projectedSimulationError(claim.status);
    return jsonError(projected.status, {
      detail: projected.detail,
      ...(projected.code ? { code: projected.code } : {}),
    });
  }
  if (claim.data.kind === "cpu") {
    const state = claim.data.state as Record<string, unknown> | null;
    if (
      typeof state !== "object" ||
      state === null ||
      state.simulation_schema_version !== 1 ||
      state.game_id !== id
    ) {
      return jsonError(502, { detail: INVALID_RESPONSE_DETAIL });
    }
    return new Response(
      simulationSse({
        type: "done",
        action: "cpu",
        completion_source: "backend_ranked_candidate",
        turn_provider_requests_used: 0,
        state,
      }),
      { headers: SSE_HEADERS },
    );
  }
  if (
    claim.data.kind !== "llm" ||
    typeof claim.data.lease_id !== "string" ||
    typeof claim.data.model_id !== "string"
  ) {
    return jsonError(502, { detail: INVALID_RESPONSE_DETAIL });
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
      `/api/admin/simulate/${id}/action/`,
      token,
      { operation, ...actionBase, ...operationPayload },
    );
    if (action.status < 200 || action.status >= 300) {
      // Non-success HTTP is a failure even when the body claims ok: true.
      throw new Error("Simulation action failed.");
    }
    return action.data;
  };
  const delegated = new NextRequest(
    request.url.replace(`/api/admin/simulate/${id}/turn`, "/api/ai/move"),
    {
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
    },
  );
  const delegatedResponse = await executeAiMoveRequest(
    delegated,
    executeAiMoveInternal,
    transport,
  );
  const headers = new Headers(delegatedResponse.headers);
  headers.set("Content-Type", "text/event-stream");
  headers.set("Cache-Control", "private, no-store, no-transform");
  headers.set("Vary", "Authorization");
  return new Response(delegatedResponse.body, {
    status: delegatedResponse.status,
    headers,
  });
}