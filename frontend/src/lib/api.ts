const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const res = await fetch(`${API_BASE}${path}`, {
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

  me: (token: string) => request("/api/auth/me/", { token }),

  // Catalog
  getModels: () =>
    request<
      Array<{
        id: number;
        provider: string;
        model_id: string;
        display_name: string;
        description: string;
        quality_tier: string;
        cost_per_game: string;
      }>
    >("/api/catalog/models/"),

  // Game
  createGame: (token: string, data: { game_mode?: string; ai_model_id?: number }) =>
    request("/api/game/create/", { method: "POST", body: data, token }),

  getGameState: (token: string, gameId: string, slot: number = 0) =>
    request(`/api/game/${gameId}/?slot=${slot}`, { token }),

  submitMove: (
    token: string,
    gameId: string,
    slot: number,
    placements: Array<{ row: number; col: number; letter: string; blank_as?: string }>,
  ) =>
    request(`/api/game/${gameId}/move/`, {
      method: "POST",
      body: { slot, placements },
      token,
    }),

  exchange: (token: string, gameId: string, slot: number, letters: string[]) =>
    request(`/api/game/${gameId}/exchange/`, {
      method: "POST",
      body: { slot, letters },
      token,
    }),

  pass: (token: string, gameId: string, slot: number) =>
    request(`/api/game/${gameId}/pass/`, {
      method: "POST",
      body: { slot },
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
};
