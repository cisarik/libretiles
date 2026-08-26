import { generateText, tool } from "ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import {
  __ibmWatsonxRuntimeTestOnly,
  getIbmWatsonxModel,
} from "./ibm-watsonx";
import {
  createProviderRequestTracker,
  type ProviderRequestTracker,
} from "./openai-compatible";
import { IBM_WATSONX_MODEL_ID } from "./provider-registry";

const NOW_MS = Date.parse("2026-08-26T10:00:00Z");
const IAM_URL = "https://iam.cloud.ibm.com/identity/token";
const INFERENCE_URL =
  "https://eu-de.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-10-25";
const API_KEY = "ibm-unit-api-key";
const PROJECT_ID = "project-test-1234";

type FetchMock = ReturnType<
  typeof vi.fn<
    (input: string | URL | Request, init?: RequestInit) => Promise<Response>
  >
>;

function configureValidEnvironment(): void {
  vi.stubEnv("IBM_CLOUD_API_KEY", API_KEY);
  vi.stubEnv("IBM_WATSONX_PROJECT_ID", PROJECT_ID);
  vi.stubEnv("IBM_WATSONX_REGION", "eu-de");
}

function installFetch(
  implementation: (
    input: string | URL | Request,
    init?: RequestInit,
  ) => Promise<Response>,
): FetchMock {
  const fetchMock = vi.fn(implementation);
  vi.stubGlobal("fetch", fetchMock);
  __ibmWatsonxRuntimeTestOnly.setFetch(fetchMock);
  return fetchMock;
}

function iamResponse(
  accessToken: string,
  options: { expiresIn?: number; expiration?: number } = {},
): Response {
  return Response.json({
    access_token: accessToken,
    token_type: "Bearer",
    ...(options.expiration === undefined
      ? { expires_in: options.expiresIn ?? 3600 }
      : { expiration: options.expiration }),
  });
}

function chatResponse(
  content = "pong",
  headers: Record<string, string> = {},
): Response {
  return new Response(
    JSON.stringify({
      id: "chatcmpl-ibm-test",
      object: "chat.completion",
      created: 1,
      model_id: IBM_WATSONX_MODEL_ID,
      choices: [
        {
          index: 0,
          message: { role: "assistant", content },
          finish_reason: "stop",
        },
      ],
      usage: { prompt_tokens: 3, completion_tokens: 1, total_tokens: 4 },
    }),
    {
      status: 200,
      headers: { "Content-Type": "application/json", ...headers },
    },
  );
}

function apiError(status: number, retryAfter?: string): Response {
  return new Response(
    JSON.stringify({
      error: {
        message: "watsonx request failed",
        type: "api_error",
        code: `status_${status}`,
      },
    }),
    {
      status,
      headers: {
        "Content-Type": "application/json",
        ...(retryAfter ? { "Retry-After": retryAfter } : {}),
      },
    },
  );
}

function callUrl(input: string | URL | Request): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

async function runtimeWithTracker(): Promise<{
  model: Awaited<ReturnType<typeof getIbmWatsonxModel>>;
  tracker: ProviderRequestTracker;
}> {
  const tracker = createProviderRequestTracker();
  const model = await getIbmWatsonxModel(IBM_WATSONX_MODEL_ID, tracker);
  return { model, tracker };
}

beforeEach(() => {
  __ibmWatsonxRuntimeTestOnly.reset();
  __ibmWatsonxRuntimeTestOnly.setNow(() => NOW_MS);
  configureValidEnvironment();
});

afterEach(() => {
  __ibmWatsonxRuntimeTestOnly.reset();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("IBM watsonx configuration boundary", () => {
  it("rejects missing, placeholder, malformed project, and invalid region before fetch", async () => {
    const fetchMock = installFetch(async () => iamResponse("never-used"));
    const cases = [
      ["IBM_CLOUD_API_KEY", ""],
      ["IBM_CLOUD_API_KEY", "your-ibm-cloud-api-key"],
      ["IBM_WATSONX_PROJECT_ID", ""],
      ["IBM_WATSONX_PROJECT_ID", "replace-me"],
      ["IBM_WATSONX_PROJECT_ID", "bad project/id"],
      ["IBM_WATSONX_REGION", ""],
      ["IBM_WATSONX_REGION", "your-region"],
      ["IBM_WATSONX_REGION", "moon-1"],
    ] as const;

    for (const [name, value] of cases) {
      __ibmWatsonxRuntimeTestOnly.reset();
      __ibmWatsonxRuntimeTestOnly.setNow(() => NOW_MS);
      configureValidEnvironment();
      vi.stubEnv(name, value);
      let caught: unknown;
      try {
        await runtimeWithTracker();
      } catch (error) {
        caught = error;
      }
      expect(caught).toMatchObject({ code: "provider_auth_failed" });
      const rendered = String(caught);
      expect(rendered).not.toContain(API_KEY);
      expect(rendered).not.toContain(PROJECT_ID);
      expect(rendered).not.toContain("eu-de");
      if (value) expect(rendered).not.toContain(value);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an arbitrary IBM model before IAM", async () => {
    const fetchMock = installFetch(async () => iamResponse("never-used"));
    const tracker = createProviderRequestTracker();
    await expect(
      getIbmWatsonxModel("ibm/arbitrary-model", tracker),
    ).rejects.toMatchObject({ code: "provider_unavailable" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(tracker.snapshot().provider_requests).toBe(0);
  });

  it("classifies an IAM credential rejection without exposing account data", async () => {
    const fetchMock = installFetch(async () =>
      new Response(`${API_KEY} ${PROJECT_ID} eu-de`, { status: 401 }),
    );
    const { model, tracker } = await runtimeWithTracker();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(tracker.snapshot().provider_requests).toBe(0);

    let caught: unknown;
    try {
      await generateText({ model, prompt: "ping", maxRetries: 0 });
    } catch (error) {
      caught = error;
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(tracker.snapshot().provider_requests).toBe(1);
    expect(caught).toMatchObject({ code: "provider_auth_failed" });
    const rendered = String(caught);
    expect(rendered).not.toContain(API_KEY);
    expect(rendered).not.toContain(PROJECT_ID);
    expect(rendered).not.toContain("eu-de");
  });
});

describe("IBM IAM and Chat Completions wire translation", () => {
  it("separates IAM auth, preserves named tools, and maps model fields both ways", async () => {
    const fetchMock = installFetch(async (input) => {
      if (callUrl(input) === IAM_URL) return iamResponse("iam-bearer-token");
      return chatResponse("pong", {
        "Content-Length": "9999",
        "X-Request-Id": "request-123",
        "Set-Cookie": "must-not-pass=1",
      });
    });
    const { model, tracker } = await runtimeWithTracker();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(tracker.snapshot().provider_requests).toBe(0);

    const result = await generateText({
      model,
      prompt: "ping",
      maxRetries: 0,
      tools: {
        validateMove: tool({
          description: "validate",
          inputSchema: z.object({ word: z.string() }),
        }),
      },
      toolChoice: { type: "tool", toolName: "validateMove" },
    });

    expect(result.text).toBe("pong");
    expect(result.response.modelId).toBe(IBM_WATSONX_MODEL_ID);
    expect(result.response.headers?.["x-request-id"]).toBe("request-123");
    expect(result.response.headers?.["content-length"]).toBeUndefined();
    expect(result.response.headers?.["set-cookie"]).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const [iamInput, iamInit] = fetchMock.mock.calls[0];
    expect(callUrl(iamInput)).toBe(IAM_URL);
    expect(iamInit?.method).toBe("POST");
    const iamHeaders = new Headers(iamInit?.headers);
    expect(iamHeaders.get("content-type")).toBe(
      "application/x-www-form-urlencoded",
    );
    expect(iamHeaders.get("authorization")).toBeNull();
    const iamBody = new URLSearchParams(String(iamInit?.body));
    expect(iamBody.get("grant_type")).toBe(
      "urn:ibm:params:oauth:grant-type:apikey",
    );
    expect(iamBody.get("apikey")).toBe(API_KEY);

    const [inferenceInput, inferenceRequest] = fetchMock.mock.calls[1];
    expect(callUrl(inferenceInput)).toBe(INFERENCE_URL);
    expect(inferenceRequest?.method).toBe("POST");
    expect(new Headers(inferenceRequest?.headers).get("authorization")).toBe(
      "Bearer iam-bearer-token",
    );
    const payload = JSON.parse(String(inferenceRequest?.body));
    expect(payload.model).toBeUndefined();
    expect(payload.model_id).toBe(IBM_WATSONX_MODEL_ID);
    expect(payload.project_id).toBe(PROJECT_ID);
    expect(payload.messages).toEqual([{ role: "user", content: "ping" }]);
    expect(payload.tools[0]).toMatchObject({
      type: "function",
      function: { name: "validateMove" },
    });
    expect(payload.tool_choice).toEqual({
      type: "function",
      function: { name: "validateMove" },
    });
    expect(tracker.snapshot().provider_requests).toBe(2);
  });

  it("accepts documented absolute expiration", async () => {
    const expiration = Math.floor(NOW_MS / 1000) + 3600;
    const fetchMock = installFetch(async (input) =>
      callUrl(input) === IAM_URL
        ? iamResponse("absolute-expiry-token", { expiration })
        : chatResponse(),
    );
    const first = await runtimeWithTracker();
    const second = await runtimeWithTracker();
    await generateText({ model: first.model, prompt: "ping", maxRetries: 0 });
    await generateText({ model: second.model, prompt: "ping", maxRetries: 0 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.filter(([input]) => callUrl(input) === IAM_URL),
    ).toHaveLength(1);
  });
});

describe("IBM IAM cache lifecycle", () => {
  it("propagates sole-caller abort into uncached IAM and prevents inference", async () => {
    const callerAbort = new AbortController();
    let iamSignal: AbortSignal | null = null;
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) !== IAM_URL) return chatResponse("must-not-run");
      iamSignal = init?.signal ?? null;
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return;
        const rejectAbort = () => reject(signal.reason);
        if (signal.aborted) rejectAbort();
        else signal.addEventListener("abort", rejectAbort, { once: true });
      });
    });
    const { model, tracker } = await runtimeWithTracker();
    const generation = generateText({
      model,
      prompt: "ping",
      maxRetries: 0,
      abortSignal: callerAbort.signal,
    });

    await vi.waitFor(() => expect(iamSignal).not.toBeNull());
    expect((iamSignal as AbortSignal | null)?.aborted).toBe(false);
    callerAbort.abort(
      new Error(`${API_KEY} ${PROJECT_ID} raw-iam-response-data`),
    );

    let caught: unknown;
    try {
      await generation;
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(DOMException);
    expect(caught).toMatchObject({ name: "AbortError" });
    expect((iamSignal as AbortSignal | null)?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => callUrl(input) === INFERENCE_URL),
    ).toHaveLength(0);
    expect(tracker.snapshot().provider_requests).toBe(1);
    const rendered = String(caught);
    expect(rendered).not.toContain(API_KEY);
    expect(rendered).not.toContain(PROJECT_ID);
    expect(rendered).not.toContain("raw-iam-response-data");
  });

  it("lets an aborted same-key joiner leave while a surviving caller completes", async () => {
    let resolveIam: ((response: Response) => void) | undefined;
    let iamSignal: AbortSignal | null = null;
    const pendingIam = new Promise<Response>((resolve) => {
      resolveIam = resolve;
    });
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) !== IAM_URL) return chatResponse();
      iamSignal = init?.signal ?? null;
      return pendingIam;
    });
    const survivorAbort = new AbortController();
    const joinerAbort = new AbortController();
    const survivorRuntime = await runtimeWithTracker();
    const joinerRuntime = await runtimeWithTracker();
    const survivor = generateText({
      model: survivorRuntime.model,
      prompt: "survivor",
      maxRetries: 0,
      abortSignal: survivorAbort.signal,
    });
    const joiner = generateText({
      model: joinerRuntime.model,
      prompt: "joiner",
      maxRetries: 0,
      abortSignal: joinerAbort.signal,
    });

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([input]) => callUrl(input) === IAM_URL),
      ).toHaveLength(1),
    );
    joinerAbort.abort();
    await expect(joiner).rejects.toMatchObject({ name: "AbortError" });
    expect((iamSignal as AbortSignal | null)?.aborted).toBe(false);

    resolveIam?.(iamResponse("surviving-shared-token"));
    await expect(survivor).resolves.toMatchObject({ text: "pong" });
    expect((iamSignal as AbortSignal | null)?.aborted).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(
      survivorRuntime.tracker.snapshot().provider_requests +
        joinerRuntime.tracker.snapshot().provider_requests,
    ).toBe(2);
  });

  it("clears an aborted IAM flight so a later same-key generation recovers", async () => {
    const firstAbort = new AbortController();
    let iamCalls = 0;
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) !== IAM_URL) return chatResponse("recovered");
      iamCalls += 1;
      if (iamCalls > 1) return iamResponse("recovered-after-abort-token");
      return new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        if (!signal) return;
        const rejectAbort = () => reject(signal.reason);
        if (signal.aborted) rejectAbort();
        else signal.addEventListener("abort", rejectAbort, { once: true });
      });
    });
    const abortedRuntime = await runtimeWithTracker();
    const aborted = generateText({
      model: abortedRuntime.model,
      prompt: "abort",
      maxRetries: 0,
      abortSignal: firstAbort.signal,
    });
    await vi.waitFor(() => expect(iamCalls).toBe(1));
    firstAbort.abort();
    await expect(aborted).rejects.toMatchObject({ name: "AbortError" });

    const recoveredRuntime = await runtimeWithTracker();
    await expect(
      generateText({
        model: recoveredRuntime.model,
        prompt: "recover",
        maxRetries: 0,
      }),
    ).resolves.toMatchObject({ text: "recovered" });
    expect(iamCalls).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(abortedRuntime.tracker.snapshot().provider_requests).toBe(1);
    expect(recoveredRuntime.tracker.snapshot().provider_requests).toBe(2);
  });

  it("isolates sequential runtimes by exact API-key identity", async () => {
    const keyA = "ibm-account-a-api-key";
    const keyB = "ibm-account-b-api-key";
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) === IAM_URL) {
        const apiKey = new URLSearchParams(String(init?.body)).get("apikey");
        if (apiKey === keyA) return iamResponse("token-a");
        if (apiKey === keyB) return iamResponse("token-b");
        throw new Error("unexpected synthetic credential identity");
      }
      return chatResponse();
    });

    vi.stubEnv("IBM_CLOUD_API_KEY", keyA);
    const runtimeA = await runtimeWithTracker();
    vi.stubEnv("IBM_CLOUD_API_KEY", keyB);
    const runtimeB = await runtimeWithTracker();
    expect(fetchMock).not.toHaveBeenCalled();

    await generateText({ model: runtimeA.model, prompt: "ping", maxRetries: 0 });
    await generateText({ model: runtimeB.model, prompt: "ping", maxRetries: 0 });

    const iamBodies = fetchMock.mock.calls
      .filter(([input]) => callUrl(input) === IAM_URL)
      .map(([, init]) => new URLSearchParams(String(init?.body)).get("apikey"));
    expect(iamBodies).toEqual([keyA, keyB]);
    const inferenceAuthorization = fetchMock.mock.calls
      .filter(([input]) => callUrl(input) === INFERENCE_URL)
      .map(([, init]) => new Headers(init?.headers).get("authorization"));
    expect(inferenceAuthorization).toEqual(["Bearer token-a", "Bearer token-b"]);
  });

  it("does not join concurrent IAM exchanges for different API keys", async () => {
    const keyA = "ibm-concurrent-a-api-key";
    const keyB = "ibm-concurrent-b-api-key";
    let resolveA: ((response: Response) => void) | undefined;
    let resolveB: ((response: Response) => void) | undefined;
    const pendingA = new Promise<Response>((resolve) => {
      resolveA = resolve;
    });
    const pendingB = new Promise<Response>((resolve) => {
      resolveB = resolve;
    });
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) !== IAM_URL) return chatResponse();
      const apiKey = new URLSearchParams(String(init?.body)).get("apikey");
      if (apiKey === keyA) return pendingA;
      if (apiKey === keyB) return pendingB;
      throw new Error("unexpected synthetic credential identity");
    });

    vi.stubEnv("IBM_CLOUD_API_KEY", keyA);
    const runtimeA = await runtimeWithTracker();
    vi.stubEnv("IBM_CLOUD_API_KEY", keyB);
    const runtimeB = await runtimeWithTracker();
    const generationA = generateText({
      model: runtimeA.model,
      prompt: "ping",
      maxRetries: 0,
    });
    const generationB = generateText({
      model: runtimeB.model,
      prompt: "ping",
      maxRetries: 0,
    });

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([input]) => callUrl(input) === IAM_URL),
      ).toHaveLength(2),
    );
    resolveA?.(iamResponse("concurrent-token-a"));
    resolveB?.(iamResponse("concurrent-token-b"));
    await Promise.all([generationA, generationB]);

    expect(fetchMock).toHaveBeenCalledTimes(4);
    const inferenceAuthorization = fetchMock.mock.calls
      .filter(([input]) => callUrl(input) === INFERENCE_URL)
      .map(([, init]) => new Headers(init?.headers).get("authorization"));
    expect(inferenceAuthorization).toEqual(
      expect.arrayContaining([
        "Bearer concurrent-token-a",
        "Bearer concurrent-token-b",
      ]),
    );
  });

  it("shares one in-flight IAM exchange across concurrent same-key generation", async () => {
    let resolveIam: ((response: Response) => void) | undefined;
    const pendingIam = new Promise<Response>((resolve) => {
      resolveIam = resolve;
    });
    const fetchMock = installFetch(async (input) =>
      callUrl(input) === IAM_URL ? pendingIam : chatResponse(),
    );

    const firstRuntime = await runtimeWithTracker();
    const secondRuntime = await runtimeWithTracker();
    const first = generateText({
      model: firstRuntime.model,
      prompt: "ping",
      maxRetries: 0,
    });
    const second = generateText({
      model: secondRuntime.model,
      prompt: "ping",
      maxRetries: 0,
    });
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([input]) => callUrl(input) === IAM_URL),
      ).toHaveLength(1),
    );
    resolveIam?.(iamResponse("shared-token"));
    await Promise.all([first, second]);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      firstRuntime.tracker.snapshot().provider_requests +
        secondRuntime.tracker.snapshot().provider_requests,
    ).toBe(3);
  });

  it("reuses a cached token before the early-refresh threshold", async () => {
    const fetchMock = installFetch(async (input) =>
      callUrl(input) === IAM_URL ? iamResponse("cached-token") : chatResponse(),
    );
    const first = await runtimeWithTracker();
    const second = await runtimeWithTracker();
    await generateText({ model: first.model, prompt: "ping", maxRetries: 0 });
    await generateText({ model: second.model, prompt: "ping", maxRetries: 0 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(first.tracker.snapshot().provider_requests).toBe(2);
    expect(second.tracker.snapshot().provider_requests).toBe(1);
  });

  it.each([
    ["expires_in", () => ({ expires_in: 7200 })],
    ["expiration", (nowMs: number) => ({ expiration: nowMs / 1000 + 7200 })],
  ])("caps a two-hour %s token to one hour", async (_field, expiryPayload) => {
    let nowMs = NOW_MS;
    __ibmWatsonxRuntimeTestOnly.setNow(() => nowMs);
    let tokenNumber = 0;
    const fetchMock = installFetch(async (input) => {
      if (callUrl(input) !== IAM_URL) return chatResponse();
      tokenNumber += 1;
      return Response.json({
        access_token: `token-${tokenNumber}`,
        token_type: "Bearer",
        ...expiryPayload(nowMs),
      });
    });

    const runtime = await runtimeWithTracker();
    await generateText({ model: runtime.model, prompt: "ping", maxRetries: 0 });
    nowMs += 3_540_000;
    await generateText({ model: runtime.model, prompt: "ping", maxRetries: 0 });
    expect(tokenNumber).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("rejects a token already inside the 60-second refresh window", async () => {
    const fetchMock = installFetch(async () =>
      iamResponse("near-expiry-token", { expiresIn: 60 }),
    );
    const { model, tracker } = await runtimeWithTracker();

    await expect(
      generateText({ model, prompt: "ping", maxRetries: 0 }),
    ).rejects.toMatchObject({ code: "provider_unavailable" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(tracker.snapshot().provider_requests).toBe(1);
  });

  it("clears a failed singleflight so the next acquisition can recover", async () => {
    let call = 0;
    const fetchMock = installFetch(async (input) => {
      if (callUrl(input) !== IAM_URL) return chatResponse();
      call += 1;
      return call === 1 ? apiError(503) : iamResponse("recovered-token");
    });

    const failed = await runtimeWithTracker();
    await expect(
      generateText({ model: failed.model, prompt: "ping", maxRetries: 0 }),
    ).rejects.toMatchObject({ code: "provider_unavailable" });
    const recovered = await runtimeWithTracker();
    expect(recovered.model).not.toBeTypeOf("string");
    if (typeof recovered.model !== "string") {
      expect(recovered.model.modelId).toBe(IBM_WATSONX_MODEL_ID);
    }
    await generateText({
      model: recovered.model,
      prompt: "ping",
      maxRetries: 0,
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(recovered.tracker.snapshot().provider_requests).toBe(2);
  });

  it("a 401 invalidates only the matching credential token", async () => {
    const keyA = "ibm-invalidation-a-api-key";
    const keyB = "ibm-invalidation-b-api-key";
    const iamCounts = new Map<string, number>();
    let tokenAOneInferenceCount = 0;
    const fetchMock = installFetch(async (input, init) => {
      if (callUrl(input) === IAM_URL) {
        const apiKey = new URLSearchParams(String(init?.body)).get("apikey");
        if (apiKey !== keyA && apiKey !== keyB) {
          throw new Error("unexpected synthetic credential identity");
        }
        const next = (iamCounts.get(apiKey) ?? 0) + 1;
        iamCounts.set(apiKey, next);
        return iamResponse(apiKey === keyA ? `token-a-${next}` : `token-b-${next}`);
      }
      const authorization = new Headers(init?.headers).get("authorization");
      if (authorization === "Bearer token-a-1") {
        tokenAOneInferenceCount += 1;
        if (tokenAOneInferenceCount === 2) return apiError(401);
      }
      return chatResponse();
    });

    vi.stubEnv("IBM_CLOUD_API_KEY", keyA);
    const runtimeA = await runtimeWithTracker();
    vi.stubEnv("IBM_CLOUD_API_KEY", keyB);
    const runtimeB = await runtimeWithTracker();
    await generateText({ model: runtimeA.model, prompt: "a1", maxRetries: 0 });
    await generateText({ model: runtimeB.model, prompt: "b1", maxRetries: 0 });
    await generateText({ model: runtimeA.model, prompt: "a2", maxRetries: 0 });
    await generateText({ model: runtimeB.model, prompt: "b2", maxRetries: 0 });

    expect(iamCounts.get(keyA)).toBe(2);
    expect(iamCounts.get(keyB)).toBe(1);
    const bAuthorization = fetchMock.mock.calls
      .filter(([, init]) =>
        new Headers(init?.headers).get("authorization")?.includes("token-b"),
      )
      .map(([, init]) => new Headers(init?.headers).get("authorization"));
    expect(bAuthorization).toEqual(["Bearer token-b-1", "Bearer token-b-1"]);
  });
});

describe("IBM inference retry and accounting", () => {
  it("classifies IAM 429 with bounded Retry-After and one tracked request", async () => {
    const fetchMock = installFetch(async () => apiError(429, "999999"));
    const { model, tracker } = await runtimeWithTracker();

    let caught: unknown;
    try {
      await generateText({ model, prompt: "ping", maxRetries: 0 });
    } catch (error) {
      caught = error;
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(caught).toMatchObject({ code: "provider_rate_limited" });
    expect(String(caught)).toBe(
      "ProviderRuntimeError: This free rival is rate limited. Switch to another free rival or retry later.",
    );
    expect(tracker.snapshot()).toEqual({
      provider_requests: 1,
      retry_after_seconds: 86_400,
    });
  });

  it("performs exactly IAM + inference + IAM + inference after one 401", async () => {
    const sequence = [
      iamResponse("token-one"),
      apiError(401),
      iamResponse("token-two"),
      chatResponse("recovered"),
    ];
    const fetchMock = installFetch(async () => {
      const next = sequence.shift();
      if (!next) throw new Error("unexpected extra request");
      return next;
    });
    const { model, tracker } = await runtimeWithTracker();
    const result = await generateText({ model, prompt: "ping", maxRetries: 0 });

    expect(result.text).toBe("recovered");
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls.map(([input]) => callUrl(input))).toEqual([
      IAM_URL,
      INFERENCE_URL,
      IAM_URL,
      INFERENCE_URL,
    ]);
    expect(
      new Headers(fetchMock.mock.calls[1][1]?.headers).get("authorization"),
    ).toBe("Bearer token-one");
    expect(
      new Headers(fetchMock.mock.calls[3][1]?.headers).get("authorization"),
    ).toBe("Bearer token-two");
    expect(tracker.snapshot().provider_requests).toBe(4);
  });

  it("stops after the second inference 401", async () => {
    const sequence = [
      iamResponse("token-one"),
      apiError(401),
      iamResponse("token-two"),
      apiError(401),
    ];
    const fetchMock = installFetch(async () => {
      const next = sequence.shift();
      if (!next) throw new Error("unexpected extra request");
      return next;
    });
    const { model, tracker } = await runtimeWithTracker();

    await expect(
      generateText({ model, prompt: "ping", maxRetries: 0 }),
    ).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(tracker.snapshot().provider_requests).toBe(4);
  });

  it("does not retry a non-401 inference failure", async () => {
    const sequence = [iamResponse("token-one"), apiError(503)];
    const fetchMock = installFetch(async () => {
      const next = sequence.shift();
      if (!next) throw new Error("unexpected extra request");
      return next;
    });
    const { model, tracker } = await runtimeWithTracker();

    await expect(
      generateText({ model, prompt: "ping", maxRetries: 0 }),
    ).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(tracker.snapshot().provider_requests).toBe(2);
  });

  it("captures bounded Retry-After telemetry without a hidden retry", async () => {
    const sequence = [iamResponse("token-one"), apiError(429, "999999")];
    const fetchMock = installFetch(async () => {
      const next = sequence.shift();
      if (!next) throw new Error("unexpected extra request");
      return next;
    });
    const { model, tracker } = await runtimeWithTracker();

    await expect(
      generateText({ model, prompt: "ping", maxRetries: 0 }),
    ).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(tracker.snapshot()).toEqual({
      provider_requests: 2,
      retry_after_seconds: 86_400,
    });
  });

  it("sanitizes transport exceptions instead of exposing account values", async () => {
    const fetchMock = installFetch(async () => {
      throw new Error(`${API_KEY} ${PROJECT_ID} eu-de bearer-secret`);
    });
    const { model, tracker } = await runtimeWithTracker();
    let caught: unknown;
    try {
      await generateText({ model, prompt: "ping", maxRetries: 0 });
    } catch (error) {
      caught = error;
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(tracker.snapshot().provider_requests).toBe(1);
    expect(caught).toMatchObject({ code: "provider_unavailable" });
    const rendered = String(caught);
    expect(rendered).not.toContain(API_KEY);
    expect(rendered).not.toContain(PROJECT_ID);
    expect(rendered).not.toContain("eu-de");
    expect(rendered).not.toContain("bearer-secret");
  });
});
