import { useGameStore } from "@/hooks/useGameStore";
import { DEFAULT_LOCALE, t, tf } from "@/lib/i18n";
import { isLocale, LOCALE_COOKIE_NAME, type Locale } from "@/lib/i18n/locales";
import type {
  AIModel,
  AIPrompt,
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
import { telemetryFromSsePayload } from "./ai-move-stream";

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

function parseRetryAfterSeconds(text: string, parsed: unknown): number | null {
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
let refreshPromise: Promise<string | null> | null = null;

/**
 * Exchange the stored refresh token for a fresh access token.
 * Updates the store on success; clears auth (forcing re-login) on failure.
 */
async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken } = useGameStore.getState();
  if (!refreshToken) return null;

  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const res = await fetch(`${resolveApiBase()}/api/auth/refresh/`, {
          method: "POST",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh: refreshToken }),
        });
        if (!res.ok) {
          useGameStore.getState().clearAuth();
          return null;
        }
        const data = (await res.json().catch(() => null)) as
          | { access?: string; refresh?: string }
          | null;
        if (!data?.access) {
          useGameStore.getState().clearAuth();
          return null;
        }
        useGameStore.getState().setToken(data.access);
        if (data.refresh) {
          useGameStore.getState().setRefreshToken(data.refresh);
        }
        return data.access;
      } catch {
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }

  return refreshPromise;
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

  let res = await sendRequest(opts.token);

  // Access tokens expire (2h). On an authenticated 401, transparently refresh
  // the access token once and retry, so the user is not kicked out mid-session.
  if (res.status === 401 && opts.token) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      res = await sendRequest(newAccess);
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
    const retryAfter = status === 429 ? parseRetryAfterSeconds(text, parsed) : null;
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
