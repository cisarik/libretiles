import type {
  AIModel,
  MoveValidationResult,
  QueueJoinResponse,
  UserProfile,
  WSTicketResponse,
} from "@/lib/types";

const DEFAULT_API_BASE = "http://localhost:8000";

function isLoopbackHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function resolveApiBase(): string {
  const configuredBase = trimTrailingSlash(
    process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_BASE,
  );

  if (typeof window === "undefined") {
    return configuredBase;
  }

  const currentHostname = window.location.hostname;
  if (!currentHostname || isLoopbackHostname(currentHostname)) {
    return configuredBase;
  }

  try {
    const configuredUrl = new URL(configuredBase);
    if (!isLoopbackHostname(configuredUrl.hostname)) {
      return configuredBase;
    }

    configuredUrl.hostname = currentHostname;
    return trimTrailingSlash(configuredUrl.toString());
  } catch {
    return configuredBase;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  token?: string | null;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (opts.token) {
    headers["Authorization"] = `Bearer ${opts.token}`;
  }

  const res = await fetch(`${resolveApiBase()}${path}`, {
    method: opts.method || "GET",
    cache: "no-store",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    const text = await res.text();
    try {
      const json = JSON.parse(text);
      if (json.ok === false) return json as T;
    } catch { /* not JSON */ }
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  // Auth
  register: (data: { username: string; email: string; password: string }) =>
    request("/api/auth/register/", { method: "POST", body: data }),

  login: (data: { username: string; password: string }) =>
    request<{ access: string; refresh: string }>("/api/auth/login/", {
      method: "POST",
      body: data,
    }),

  me: (token: string) => request<UserProfile>("/api/auth/me/", { token }),
  updateMe: (token: string, data: Partial<Pick<UserProfile, "preferred_ai_model_id">>) =>
    request<UserProfile>("/api/auth/me/", { method: "PATCH", body: data, token }),

  // Catalog
  getModels: () => request<AIModel[]>("/api/catalog/models/"),

  // Game
  createGame: (
    token: string,
    data: { game_mode?: "vs_ai"; ai_model_id?: number; ai_model_model_id?: string },
  ) => request("/api/game/create/", { method: "POST", body: data, token }),

  joinHumanQueue: (
    token: string,
    data?: { variant_slug?: string },
  ) =>
    request<QueueJoinResponse>("/api/game/queue/join/", {
      method: "POST",
      body: data ?? {},
      token,
    }),

  cancelHumanQueue: (token: string, gameId: string) =>
    request<{ ok: boolean; error?: string }>("/api/game/queue/cancel/", {
      method: "POST",
      body: { game_id: gameId },
      token,
    }),

  updateGameAIModel: (
    token: string,
    gameId: string,
    data: { ai_model_model_id: string },
  ) =>
    request<{ ok: boolean; ai_model_id: string; ai_model_display_name: string }>(
      `/api/game/${gameId}/ai-model/`,
      { method: "PATCH", body: data, token },
    ),

  getGameState: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/`, { token }),

  getWSTicket: (token: string, gameId: string) =>
    request<WSTicketResponse>(`/api/game/${gameId}/ws-ticket/`, {
      method: "POST",
      token,
    }),

  submitMove: (
    token: string,
    gameId: string,
    placements: Array<{ row: number; col: number; letter: string; blank_as?: string }>,
  ) =>
    request(`/api/game/${gameId}/move/`, {
      method: "POST",
      body: { placements },
      token,
    }),

  exchange: (token: string, gameId: string, letters: string[]) =>
    request(`/api/game/${gameId}/exchange/`, {
      method: "POST",
      body: { letters },
      token,
    }),

  pass: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/pass/`, {
      method: "POST",
      token,
    }),

  aiPass: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/ai-pass/`, {
      method: "POST",
      token,
    }),

  aiExchange: (token: string, gameId: string, letters: string[]) =>
    request(`/api/game/${gameId}/ai-exchange/`, {
      method: "POST",
      body: { letters },
      token,
    }),

  giveUp: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/give-up/`, {
      method: "POST",
      token,
    }),

  getAIContext: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/ai-context/`, { token }),

  validateWords: (token: string, gameId: string, words: string[]) =>
    request(`/api/game/${gameId}/validate-words/`, {
      method: "POST",
      body: { words },
      token,
    }),

  validateMove: (
    token: string,
    gameId: string,
    placements: Array<{ row: number; col: number; letter: string; blank_as?: string }>,
  ) =>
    request<MoveValidationResult>(`/api/game/${gameId}/validate-move/`, {
      method: "POST",
      body: { placements },
      token,
    }),

  applyAIMove: (
    token: string,
    gameId: string,
    placements: Array<{ row: number; col: number; letter: string; blank_as?: string }>,
    ai_metadata?: Record<string, unknown>,
  ) =>
    request(`/api/game/${gameId}/ai-move/`, {
      method: "POST",
      body: { placements, ai_metadata },
      token,
    }),

  chargeAITurn: (token: string, gameId: string, ai_metadata?: Record<string, unknown>) =>
    request("/api/billing/charge-ai-turn/", {
      method: "POST",
      body: { game_id: gameId, ai_metadata },
      token,
    }),
};
