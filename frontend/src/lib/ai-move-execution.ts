import type { NextRequest } from "next/server";
import { AsyncLocalStorage } from "node:async_hooks";

export type AiMoveBackendRequest = (
  path: string,
  init?: { method?: "GET" | "POST" | "PATCH"; body?: unknown },
) => Promise<Record<string, unknown> | null>;

const backendTransport = new AsyncLocalStorage<AiMoveBackendRequest>();

export function currentAiMoveBackendTransport(): AiMoveBackendRequest | null {
  return backendTransport.getStore() ?? null;
}

/** Shared execution boundary used by normal play and privileged simulation turns. */
export async function executeAiMoveRequest(
  request: NextRequest,
  implementation: (request: NextRequest) => Promise<Response>,
  transport?: AiMoveBackendRequest,
): Promise<Response> {
  if (transport) {
    return backendTransport.run(transport, () => implementation(request));
  }
  return implementation(request);
}
