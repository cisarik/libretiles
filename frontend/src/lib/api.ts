import { useGameStore } from "@/hooks/useGameStore";
import { DEFAULT_LOCALE, t, tf } from "@/lib/i18n";
import { isLocale, LOCALE_COOKIE_NAME, type Locale } from "@/lib/i18n/locales";
import type {
  AIModel,
  AIPrompt,
  AdminGameListParams,
  AdminGameListResponse,
  AdminAnalyticsParams,
  AdminAnalyticsResponse,
  AdminReplayPayload,
  AiTurnTelemetry,
  GameHistoryFilter,
  GameHistoryResponse,
  GameHistorySort,
  MoveValidationResult,
  QueueJoinResponse,
  UserProfile,
  VariantSummary,
  WSTicketResponse,
} from "@/lib/types";
import { parseAdminAnalytics } from "./admin-analytics";
import { telemetryFromSsePayload } from "./ai-move-stream";
import {
  parseSimulationState,
  type SimulationConfig,
  type SimulationState,
} from "./admin-simulation";

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

export class ApiError extends Error {
  readonly status: number;
  readonly fields: Record<string, string[]> | null;

  constructor(
    status: number,
    message: string,
    fields: Record<string, string[]> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function extractFieldEntries(parsed: unknown): Record<string, string[]> | null {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const fields: Record<string, string[]> = {};
  for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (key === "ok" || key === "detail" || key === "error" || key === "code") continue;
    if (Array.isArray(value) && value.every((item) => typeof item === "string")) {
      fields[key] = value;
    } else if (typeof value === "string" && value.trim()) {
      fields[key] = [value];
    }
  }
  return Object.keys(fields).length > 0 ? fields : null;
}

function firstFieldMessage(parsed: unknown): string | null {
  if (!parsed || typeof parsed !== "object") return null;
  const rec = parsed as Record<string, unknown>;
  if (typeof rec.detail === "string" && rec.detail.trim() && !rec.detail.startsWith("{")) {
    return rec.detail;
  }
  if (Array.isArray(rec.detail) && typeof rec.detail[0] === "string") {
    return rec.detail[0];
  }
  if (typeof rec.error === "string" && rec.error.trim()) {
    return rec.error;
  }
  if (Array.isArray(rec.non_field_errors) && typeof rec.non_field_errors[0] === "string") {
    return rec.non_field_errors[0];
  }
  const preferred = ["password", "username", "email", "current_password", "new_password"];
  for (const key of preferred) {
    const value = rec[key];
    if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim()) {
      return value[0];
    }
    if (typeof value === "string" && value.trim()) return value;
  }
  for (const [key, value] of Object.entries(rec)) {
    if (key === "ok" || key === "code") continue;
    if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim()) {
      return value[0];
    }
  }
  return null;
}

function parseRetryAfterSeconds(
  headerValue: string | null,
  text: string,
  parsed: unknown,
): number | null {
  // Prefer the numeric Retry-After header. DRF sets it at
  // rest_framework/views.py:92 whenever the throttle knows the wait, and unlike
  // the body it is locale-independent — uii-01-F01.
  //
  // The prose fallbacks below are KEPT rather than replaced. The header is only
  // readable cross-origin while the backend lists it in CORS_EXPOSE_HEADERS, and
  // a reverse proxy may strip it, so losing the header must degrade to today's
  // behaviour rather than to "unknown wait". A Retry-After HTTP-date also lands
  // here and correctly falls through, because DRF only ever sends an integer.
  if (headerValue) {
    const seconds = Number(headerValue.trim());
    if (Number.isFinite(seconds) && seconds >= 0) {
      return seconds;
    }
  }
  if (parsed && typeof parsed === "object" && parsed !== null) {
    const detail = (parsed as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      const match = detail.match(/(\d+)\s+seconds/i);
      if (match) return Number(match[1]);
    }
  }
  const match = text.match(/(\d+)\s+seconds/i);
  return match ? Number(match[1]) : null;
}

function formatThrottleWait(seconds: number | null, locale: Locale): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return t(locale, "error.throttled.unknown");
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes === 1) {
    return t(locale, "error.throttled.oneMinute");
  }
  return tf(locale, "error.throttled.minutes", { minutes });
}

function humanMessageForStatus(
  status: number,
  fieldMessage: string | null,
  retryAfterSeconds: number | null,
  requestCarriedToken: boolean,
  locale: Locale,
): string {
  switch (status) {
    case 400:
      return fieldMessage ?? t(locale, "error.checkFields");
    case 401:
      return requestCarriedToken
        ? t(locale, "error.sessionExpired")
        : t(locale, "error.invalidCredentials");
    case 403:
      return t(locale, "error.forbidden");
    case 404:
      return t(locale, "error.notFound");
    case 409:
      return fieldMessage ?? t(locale, "error.conflict");
    case 429:
      return formatThrottleWait(retryAfterSeconds, locale);
    case 503:
      return t(locale, "error.unavailable");
    default:
      return t(locale, "error.generic");
  }
}

// Shared in-flight refresh so concurrent 401s trigger only one refresh call.
// The flight is keyed by the authEpoch it started from: a logout or an account
// switch (both bump authEpoch) must never share or join an older flight.
type RefreshSnapshot = {
  epoch: number;
  token: string;
  refreshToken: string;
};

let refreshFlight: { epoch: number; promise: Promise<string | null> } | null =
  null;

function clearAuthIfMatches(snapshot: RefreshSnapshot): void {
  const store = useGameStore.getState();
  if (
    store.authEpoch === snapshot.epoch &&
    store.token === snapshot.token &&
    store.refreshToken === snapshot.refreshToken
  ) {
    store.clearAuth();
  }
}

async function performRefresh(snapshot: RefreshSnapshot): Promise<string | null> {
  let res: Response;
  try {
    res = await fetch(`${resolveApiBase()}/api/auth/refresh/`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: snapshot.refreshToken }),
    });
  } catch {
    // Transport failure: keep the current tokens (today's behaviour).
    return null;
  }
  if (!res.ok) {
    clearAuthIfMatches(snapshot);
    return null;
  }
  const data = await res.json().catch(() => null);
  const access =
    typeof data === "object" && data !== null
      ? (data as { access?: unknown }).access
      : undefined;
  const refresh =
    typeof data === "object" && data !== null
      ? (data as { refresh?: unknown }).refresh
      : undefined;
  if (typeof access !== "string" || access.length === 0) {
    clearAuthIfMatches(snapshot);
    return null;
  }
  if (refresh !== undefined && (typeof refresh !== "string" || refresh.length === 0)) {
    clearAuthIfMatches(snapshot);
    return null;
  }
  const applied = useGameStore.getState().applyRefreshedAuth(
    {
      epoch: snapshot.epoch,
      token: snapshot.token,
      refreshToken: snapshot.refreshToken,
    },
    {
      access,
      ...(typeof refresh === "string" ? { refresh } : {}),
    },
  );
  return applied ? access : null;
}

function refreshForEpoch(snapshot: RefreshSnapshot): Promise<string | null> {
  if (refreshFlight && refreshFlight.epoch === snapshot.epoch) {
    return refreshFlight.promise;
  }
  const flight: { epoch: number; promise: Promise<string | null> } = {
    epoch: snapshot.epoch,
    // Ownership is assigned before the refresh body can run, so a synthetic
    // synchronous fetch failure can never leave the slot unwrapped.
    promise: Promise.resolve().then(() => performRefresh(snapshot)),
  };
  flight.promise = flight.promise.finally(() => {
    if (refreshFlight === flight) refreshFlight = null;
  });
  refreshFlight = flight;
  return flight.promise;
}

function acceptLanguageFromCookie(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const prefix = `${LOCALE_COOKIE_NAME}=`;
  for (const raw of document.cookie.split(";")) {
    const cookie = raw.trim();
    if (!cookie.startsWith(prefix)) continue;
    const value = cookie.slice(prefix.length);
    return isLocale(value) ? value : undefined;
  }
  return undefined;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const sendRequest = (bearer?: string | null) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    const acceptLanguage = acceptLanguageFromCookie();
    if (acceptLanguage) {
      headers["Accept-Language"] = acceptLanguage;
    }
    if (bearer) {
      headers["Authorization"] = `Bearer ${bearer}`;
    }
    return fetch(`${resolveApiBase()}${path}`, {
      method: opts.method || "GET",
      cache: "no-store",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  };

  const requestEpoch = useGameStore.getState().authEpoch;
  const requestUsedStoreToken =
    opts.token !== null && opts.token === useGameStore.getState().token;

  let res = await sendRequest(opts.token);

  // Access tokens expire (2h). On an authenticated 401, transparently refresh
  // the access token once and retry, so the user is not kicked out mid-session.
  // The refresh is owned by the session it started from (authEpoch + token
  // pair): a logout or an account switch while the request is in flight
  // invalidates the refresh and forbids a retry under the new identity.
  if (res.status === 401 && opts.token) {
    const store = useGameStore.getState();
    if (store.authEpoch !== requestEpoch) {
      // Identity changed mid-flight: no refresh, no retry under the new session.
    } else if (opts.token === store.token) {
      if (store.refreshToken) {
        const newAccess = await refreshForEpoch({
          epoch: requestEpoch,
          token: store.token,
          refreshToken: store.refreshToken,
        });
        if (newAccess) {
          // Re-verify before the retry: the session must still be the same
          // one and the store must carry the refreshed access token.
          const current = useGameStore.getState();
          if (current.authEpoch === requestEpoch && current.token === newAccess) {
            res = await sendRequest(newAccess);
          }
        }
      }
    } else if (requestUsedStoreToken) {
      // A sibling refresh rotated the access token while this request was in
      // flight; retry once with the newer token instead of starting another
      // refresh wave.
      res = await sendRequest(store.token);
    }
  }

  if (!res.ok) {
    const status = res.status;
    const text = await res.text();
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
    if (
      parsed !== null &&
      typeof parsed === "object" &&
      (parsed as { ok?: unknown }).ok === false
    ) {
      return parsed as T;
    }
    const fields = extractFieldEntries(parsed);
    const fieldMessage = firstFieldMessage(parsed);
    const retryAfter =
      status === 429
        ? parseRetryAfterSeconds(res.headers.get("Retry-After"), text, parsed)
        : null;
    const locale: Locale = useGameStore.getState().uiLocale ?? DEFAULT_LOCALE;
    throw new ApiError(
      status,
      humanMessageForStatus(
        status,
        fieldMessage,
        retryAfter,
        Boolean(opts.token),
        locale,
      ),
      fields,
    );
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

  logout: (access: string, refresh: string) =>
    request<{ ok: boolean }>("/api/auth/logout/", {
      method: "POST",
      body: { refresh },
      token: access,
    }),

  me: (token: string) => request<UserProfile>("/api/auth/me/", { token }),
  updateMe: (token: string, data: Partial<Pick<UserProfile, "preferred_ai_model_id">>) =>
    request<UserProfile>("/api/auth/me/", { method: "PATCH", body: data, token }),
  changePassword: (
    token: string,
    data: { current_password: string; new_password: string },
  ) =>
    request<{ ok: boolean; error?: string }>("/api/auth/change-password/", {
      method: "POST",
      body: data,
      token,
    }),

  // Catalog
  getModels: () => request<AIModel[]>("/api/catalog/models/"),

  getVariants: (token: string) =>
    request<VariantSummary[]>("/api/game/variants/", { token }),

  admin: {
    listGames: (token: string, params: AdminGameListParams = {}) => {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== "") query.set(key, String(value));
      }
      const suffix = query.size ? `?${query.toString()}` : "";
      return request<AdminGameListResponse>(`/api/admin/games/${suffix}`, { token });
    },
    getReplay: (token: string, gameId: string) =>
      request<AdminReplayPayload>(`/api/admin/games/${encodeURIComponent(gameId)}/replay/`, { token }),
    getAnalytics: async (token: string, params: AdminAnalyticsParams = {}) => {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== "") query.set(key, String(value));
      }
      const suffix = query.size ? `?${query.toString()}` : "";
      return parseAdminAnalytics(await request<AdminAnalyticsResponse>(`/api/admin/analytics/${suffix}`, { token }));
    },
    createSimulation: async (token: string, data: SimulationConfig) =>
      parseSimulationState(
        await request<SimulationState>("/api/admin/simulate/", {
          method: "POST",
          body: data,
          token,
        }),
      ),
    getSimulation: async (token: string, gameId: string) =>
      parseSimulationState(
        await request<SimulationState>(
          `/api/admin/simulate/${encodeURIComponent(gameId)}/`,
          { token },
        ),
      ),
    stepSimulation: (
      token: string,
      gameId: string,
      expectedMoveCount: number,
    ) =>
      request<Record<string, unknown>>(
        `/api/admin/simulate/${encodeURIComponent(gameId)}/step/`,
        {
          method: "POST",
          body: { expected_move_count: expectedMoveCount },
          token,
        },
      ),
    stopSimulation: async (token: string, gameId: string) =>
      parseSimulationState(
        await request<SimulationState>(
          `/api/admin/simulate/${encodeURIComponent(gameId)}/stop/`,
          { method: "POST", body: {}, token },
        ),
      ),
  },

  // Game
  createGame: (
    token: string,
    data: {
      game_mode?: "vs_ai";
      ai_model_id?: number;
      ai_model_model_id?: string;
      ai_prompt_id?: number;
      variant_slug?: string;
    },
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
  updateGameAIPrompt: (
    token: string,
    gameId: string,
    data: { ai_prompt_id: number },
  ) =>
    request<{ ok: boolean; ai_prompt_id: number; ai_prompt_name: string; ai_prompt_fitness: number }>(
      `/api/game/${gameId}/ai-prompt/`,
      { method: "PATCH", body: data, token },
    ),

  getGameState: (token: string, gameId: string) =>
    request(`/api/game/${gameId}/`, { token }),

  getPrompts: () => request<AIPrompt[]>("/api/catalog/prompts/"),

  listGameHistory: (
    token: string,
    params?: { game_mode?: GameHistoryFilter; sort?: GameHistorySort; page?: number; page_size?: number },
  ) => {
    const query = new URLSearchParams();
    if (params?.game_mode) query.set("game_mode", params.game_mode);
    if (params?.sort) query.set("sort", params.sort);
    if (params?.page) query.set("page", String(params.page));
    if (params?.page_size) query.set("page_size", String(params.page_size));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<GameHistoryResponse>(`/api/game/history/${suffix}`, { token });
  },

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

};

/** Transient AI-turn diagnostics from an SSE payload. Never persisted. */
export function readAiTurnTelemetry(
  payload: Record<string, unknown> | null | undefined,
): AiTurnTelemetry | null {
  if (!payload) return null;
  return telemetryFromSsePayload(payload);
}
