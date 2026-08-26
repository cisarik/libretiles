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
    let caught: unknown;
    try {
      await runtimeWithTracker();
    } catch (error) {
      caught = error;
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
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
    const fetchMock = installFetch(async () =>
      iamResponse("absolute-expiry-token", { expiration }),
    );
    await runtimeWithTracker();
    await runtimeWithTracker();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("IBM IAM cache lifecycle", () => {
  it("shares one in-flight IAM exchange across concurrent runtime construction", async () => {
    let resolveIam: ((response: Response) => void) | undefined;
    const pendingIam = new Promise<Response>((resolve) => {
      resolveIam = resolve;
    });
    const fetchMock = installFetch(async () => pendingIam);

    const first = runtimeWithTracker();
    const second = runtimeWithTracker();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    resolveIam?.(iamResponse("shared-token"));
    const [firstRuntime, secondRuntime] = await Promise.all([first, second]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      firstRuntime.tracker.snapshot().provider_requests +
        secondRuntime.tracker.snapshot().provider_requests,
    ).toBe(1);
  });

  it("reuses a cached token before the early-refresh threshold", async () => {
    const fetchMock = installFetch(async () => iamResponse("cached-token"));
    const first = await runtimeWithTracker();
    const second = await runtimeWithTracker();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first.tracker.snapshot().provider_requests).toBe(1);
    expect(second.tracker.snapshot().provider_requests).toBe(0);
  });

  it("refreshes once the cached token is within 60 seconds of expiry", async () => {
    let nowMs = NOW_MS;
    __ibmWatsonxRuntimeTestOnly.setNow(() => nowMs);
    let tokenNumber = 0;
    const fetchMock = installFetch(async () => {
      tokenNumber += 1;
      return iamResponse(`token-${tokenNumber}`);
    });

    await runtimeWithTracker();
    nowMs += 3_541_000;
    await runtimeWithTracker();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears a failed singleflight so the next acquisition can recover", async () => {
    let call = 0;
    const fetchMock = installFetch(async () => {
      call += 1;
      return call === 1 ? apiError(503) : iamResponse("recovered-token");
    });

    const failed = runtimeWithTracker();
    await expect(failed).rejects.toMatchObject({
      code: "provider_unavailable",
    });
    const recovered = await runtimeWithTracker();
    expect(recovered.model).not.toBeTypeOf("string");
    if (typeof recovered.model !== "string") {
      expect(recovered.model.modelId).toBe(IBM_WATSONX_MODEL_ID);
    }
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(recovered.tracker.snapshot().provider_requests).toBe(1);
  });
});

describe("IBM inference retry and accounting", () => {
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
    let caught: unknown;
    try {
      await runtimeWithTracker();
    } catch (error) {
      caught = error;
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(caught).toMatchObject({ code: "provider_unavailable" });
    const rendered = String(caught);
    expect(rendered).not.toContain(API_KEY);
    expect(rendered).not.toContain(PROJECT_ID);
    expect(rendered).not.toContain("eu-de");
    expect(rendered).not.toContain("bearer-secret");
  });
});
