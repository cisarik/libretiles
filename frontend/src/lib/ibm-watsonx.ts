/** Server-only IBM watsonx.ai Chat Completions runtime. */

import { createOpenAI } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import {
  ProviderRuntimeError,
  requireServerCredential,
  type ProviderRequestTracker,
} from "./openai-compatible";
import { recordProviderFailure } from "./provider-logging";
import {
  IBM_WATSONX_MODEL_ID,
  IBM_WATSONX_PROVIDER,
} from "./provider-registry";

const IBM_IAM_URL = "https://iam.cloud.ibm.com/identity/token";
const IBM_API_VERSION = "2023-10-25";
const SDK_BASE_URL = "https://ibm-watsonx.invalid/v1";
const SDK_CHAT_URL = `${SDK_BASE_URL}/chat/completions`;
const SDK_PLACEHOLDER_KEY = "ibm-iam-managed-by-runtime";
const TOKEN_REFRESH_SKEW_MS = 60_000;
const MAX_TOKEN_LIFETIME_MS = 3_600_000;

const ALLOWED_REGIONS = new Set([
  "eu-de",
  "eu-gb",
  "us-south",
  "jp-tok",
  "au-syd",
]);

const SAFE_RESPONSE_HEADERS = [
  "content-type",
  "date",
  "retry-after",
  "server-timing",
  "x-global-transaction-id",
  "x-request-id",
] as const;

type IbmWatsonxConfig = Readonly<{
  apiKey: string;
  projectId: string;
  inferenceUrl: string;
}>;

type CachedIamToken = {
  accessToken: string;
  expiresAtMs: number;
};

type IamTokenFlight = {
  controller: AbortController;
  promise: Promise<CachedIamToken>;
  waiters: number;
  settled: boolean;
  abandoned: boolean;
};

const cachedIamTokens = new Map<string, CachedIamToken>();
const iamTokenFlights = new Map<string, IamTokenFlight>();
let nowForRuntime = () => Date.now();
let fetchForRuntime: typeof globalThis.fetch = (input, init) =>
  globalThis.fetch(input, init);

function unavailable(): ProviderRuntimeError {
  return new ProviderRuntimeError("provider_unavailable");
}

function requireProjectId(value: string | undefined): string {
  const projectId = requireServerCredential(value);
  if (!/^[A-Za-z0-9-]{8,128}$/.test(projectId)) {
    throw new ProviderRuntimeError("provider_auth_failed");
  }
  return projectId;
}

function requireRegion(value: string | undefined): string {
  const region = requireServerCredential(value);
  if (!ALLOWED_REGIONS.has(region)) {
    throw new ProviderRuntimeError("provider_auth_failed");
  }
  return region;
}

function readConfig(): IbmWatsonxConfig {
  const apiKey = requireServerCredential(process.env.IBM_CLOUD_API_KEY);
  const projectId = requireProjectId(process.env.IBM_WATSONX_PROJECT_ID);
  const region = requireRegion(process.env.IBM_WATSONX_REGION);
  return {
    apiKey,
    projectId,
    inferenceUrl: `https://${region}.ml.cloud.ibm.com/ml/v1/text/chat?version=${IBM_API_VERSION}`,
  };
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  );
}

function safeAbortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

function throwIfAborted(signal: AbortSignal | undefined): void {
  if (signal?.aborted) throw safeAbortError();
}

async function trackedFetch(
  tracker: ProviderRequestTracker,
  input: string | URL | Request,
  init: RequestInit,
): Promise<Response> {
  tracker.noteProviderRequest();
  let response: Response;
  try {
    response = await fetchForRuntime(input, init);
  } catch (error) {
    if (isAbortError(error)) throw error;
    recordProviderFailure({
      provider: IBM_WATSONX_PROVIDER,
      phase: "provider_transport",
      error,
    });
    throw unavailable();
  }
  tracker.recordRetryAfter(response.headers.get("retry-after"));
  if (!response.ok) {
    recordProviderFailure({
      provider: IBM_WATSONX_PROVIDER,
      phase: "provider_http",
      status: response.status,
      error: new Error(`HTTP ${response.status}`),
    });
  }
  return response;
}

function boundedExpiry(payload: Record<string, unknown>, nowMs: number): number {
  const candidates: number[] = [];
  const expiration = payload.expiration;
  if (typeof expiration === "number" && Number.isFinite(expiration)) {
    candidates.push(expiration * 1000);
  }

  const expiresIn = payload.expires_in;
  if (
    typeof expiresIn === "number" &&
    Number.isFinite(expiresIn) &&
    expiresIn > 0
  ) {
    candidates.push(
      nowMs + Math.min(Math.floor(expiresIn * 1000), MAX_TOKEN_LIFETIME_MS),
    );
  }

  if (candidates.length === 0) throw unavailable();
  const expiresAtMs = Math.min(
    Math.min(...candidates),
    nowMs + MAX_TOKEN_LIFETIME_MS,
  );
  if (expiresAtMs <= nowMs + TOKEN_REFRESH_SKEW_MS) throw unavailable();
  return expiresAtMs;
}

async function requestIamToken(
  apiKey: string,
  tracker: ProviderRequestTracker,
  signal: AbortSignal,
): Promise<CachedIamToken> {
  const body = new URLSearchParams({
    grant_type: "urn:ibm:params:oauth:grant-type:apikey",
    apikey: apiKey,
  });
  const response = await trackedFetch(tracker, IBM_IAM_URL, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
    signal,
  });

  if (!response.ok) {
    if ([400, 401, 403].includes(response.status)) {
      throw new ProviderRuntimeError("provider_auth_failed");
    }
    if (response.status === 429) {
      throw new ProviderRuntimeError("provider_rate_limited");
    }
    throw unavailable();
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw unavailable();
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw unavailable();
  }

  const record = payload as Record<string, unknown>;
  const accessToken =
    typeof record.access_token === "string" ? record.access_token.trim() : "";
  if (!accessToken) throw unavailable();
  const nowMs = nowForRuntime();
  return {
    accessToken,
    expiresAtMs: boundedExpiry(record, nowMs),
  };
}

function freshCachedToken(
  apiKey: string,
  nowMs: number,
): CachedIamToken | null {
  const cached = cachedIamTokens.get(apiKey) ?? null;
  if (cached?.expiresAtMs && cached.expiresAtMs - TOKEN_REFRESH_SKEW_MS > nowMs) {
    return cached;
  }
  cachedIamTokens.delete(apiKey);
  return null;
}

async function acquireIamToken(
  apiKey: string,
  tracker: ProviderRequestTracker,
  signal: AbortSignal | undefined,
): Promise<CachedIamToken> {
  throwIfAborted(signal);
  const cached = freshCachedToken(apiKey, nowForRuntime());
  if (cached) return cached;
  let flight = iamTokenFlights.get(apiKey);
  if (!flight) {
    const controller = new AbortController();
    const currentFlight: IamTokenFlight = {
      controller,
      promise: requestIamToken(apiKey, tracker, controller.signal)
        .then((token) => {
          if (
            !currentFlight.abandoned &&
            iamTokenFlights.get(apiKey) === currentFlight
          ) {
            cachedIamTokens.set(apiKey, token);
          }
          return token;
        })
        .catch((error) => {
          if (iamTokenFlights.get(apiKey) === currentFlight) {
            cachedIamTokens.delete(apiKey);
          }
          throw error;
        })
        .finally(() => {
          currentFlight.settled = true;
          if (iamTokenFlights.get(apiKey) === currentFlight) {
            iamTokenFlights.delete(apiKey);
          }
        }),
      waiters: 0,
      settled: false,
      abandoned: false,
    };
    iamTokenFlights.set(apiKey, currentFlight);
    flight = currentFlight;
  }

  const joinedFlight = flight;
  joinedFlight.waiters += 1;
  return new Promise<CachedIamToken>((resolve, reject) => {
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      signal?.removeEventListener("abort", onAbort);
      joinedFlight.waiters -= 1;
      if (joinedFlight.waiters === 0 && !joinedFlight.settled) {
        joinedFlight.abandoned = true;
        cachedIamTokens.delete(apiKey);
        if (iamTokenFlights.get(apiKey) === joinedFlight) {
          iamTokenFlights.delete(apiKey);
        }
        joinedFlight.controller.abort(safeAbortError());
      }
    };
    const onAbort = () => {
      release();
      reject(safeAbortError());
    };

    signal?.addEventListener("abort", onAbort, { once: true });
    if (signal?.aborted) {
      onAbort();
      return;
    }
    joinedFlight.promise.then(
      (token) => {
        release();
        resolve(token);
      },
      (error) => {
        release();
        reject(error);
      },
    );
  });
}

function invalidateIamToken(apiKey: string, accessToken: string): void {
  if (cachedIamTokens.get(apiKey)?.accessToken === accessToken) {
    cachedIamTokens.delete(apiKey);
  }
}

function requestUrl(input: string | URL | Request): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestAbortSignal(
  input: string | URL | Request,
  init: RequestInit | undefined,
): AbortSignal | undefined {
  if (init?.signal) return init.signal;
  return input instanceof Request ? input.signal : undefined;
}

function translateRequestBody(
  init: RequestInit | undefined,
  projectId: string,
): string {
  if (typeof init?.body !== "string") throw unavailable();

  let payload: unknown;
  try {
    payload = JSON.parse(init.body);
  } catch {
    throw unavailable();
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw unavailable();
  }

  const record = payload as Record<string, unknown>;
  if (record.model !== IBM_WATSONX_MODEL_ID || record.stream === true) {
    throw unavailable();
  }
  const { model: _model, ...supportedChatFields } = record;
  void _model;
  return JSON.stringify({
    ...supportedChatFields,
    model_id: IBM_WATSONX_MODEL_ID,
    project_id: projectId,
  });
}

function inferenceInit(
  init: RequestInit | undefined,
  body: string,
  accessToken: string,
): RequestInit {
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  headers.set("Content-Type", "application/json");
  return {
    ...init,
    method: "POST",
    headers,
    body,
  };
}

function safeResponseHeaders(source: Headers): Headers {
  const headers = new Headers();
  for (const name of SAFE_RESPONSE_HEADERS) {
    const value = source.get(name);
    if (value !== null) headers.set(name, value);
  }
  headers.delete("content-length");
  return headers;
}

async function translateSuccessResponse(response: Response): Promise<Response> {
  const rawBody = await response.text();
  let payload: unknown;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return new Response(rawBody, {
      status: response.status,
      statusText: response.statusText,
      headers: safeResponseHeaders(response.headers),
    });
  }
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return new Response(rawBody, {
      status: response.status,
      statusText: response.statusText,
      headers: safeResponseHeaders(response.headers),
    });
  }

  const record = payload as Record<string, unknown>;
  const { model_id: modelId, ...openAiFields } = record;
  return new Response(
    JSON.stringify({
      ...openAiFields,
      ...(typeof modelId === "string" ? { model: modelId } : {}),
    }),
    {
      status: response.status,
      statusText: response.statusText,
      headers: safeResponseHeaders(response.headers),
    },
  );
}

function createIbmInferenceFetch(
  config: IbmWatsonxConfig,
  tracker: ProviderRequestTracker,
): typeof globalThis.fetch {
  return async (input, init) => {
    if (requestUrl(input) !== SDK_CHAT_URL) throw unavailable();
    const body = translateRequestBody(init, config.projectId);
    const abortSignal = requestAbortSignal(input, init);
    let token = await acquireIamToken(config.apiKey, tracker, abortSignal);
    let response = await trackedFetch(
      tracker,
      config.inferenceUrl,
      inferenceInit(init, body, token.accessToken),
    );

    if (response.status === 401) {
      invalidateIamToken(config.apiKey, token.accessToken);
      token = await acquireIamToken(config.apiKey, tracker, abortSignal);
      response = await trackedFetch(
        tracker,
        config.inferenceUrl,
        inferenceInit(init, body, token.accessToken),
      );
    }

    if (!response.ok) return response;
    return translateSuccessResponse(response);
  };
}

export async function getIbmWatsonxModel(
  modelId: string,
  tracker: ProviderRequestTracker,
): Promise<LanguageModel> {
  if (modelId !== IBM_WATSONX_MODEL_ID) throw unavailable();
  const config = readConfig();
  const compatible = createOpenAI({
    baseURL: SDK_BASE_URL,
    apiKey: SDK_PLACEHOLDER_KEY,
    name: IBM_WATSONX_PROVIDER,
    fetch: createIbmInferenceFetch(config, tracker),
  });
  return compatible.chat(modelId);
}

/** Deterministic cache/clock/fetch controls. Never use outside unit tests. */
export const __ibmWatsonxRuntimeTestOnly = {
  reset(): void {
    cachedIamTokens.clear();
    for (const flight of iamTokenFlights.values()) {
      flight.abandoned = true;
      flight.controller.abort(safeAbortError());
    }
    iamTokenFlights.clear();
    nowForRuntime = () => Date.now();
    fetchForRuntime = (input, init) => globalThis.fetch(input, init);
  },
  setNow(now: () => number): void {
    nowForRuntime = now;
  },
  setFetch(fetchImplementation: typeof globalThis.fetch): void {
    fetchForRuntime = fetchImplementation;
  },
};
