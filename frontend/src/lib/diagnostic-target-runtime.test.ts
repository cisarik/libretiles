import { afterEach, describe, expect, it, vi } from "vitest";
import { CREDENTIAL_ENV_NAMES } from "./provider-logging";
import {
  DiagnosticEgressDeniedError,
  DIAGNOSTIC_EGRESS_ENV,
  resolveDiagnosticEgressMode,
} from "./diagnostic-egress";
import {
  getDiagnosticLanguageRuntime,
  parseDiagnosticRuntimeSpec,
} from "./diagnostic-target-runtime";

const TARGET_ID = "00000000-0000-0000-0000-0000000000aa";
const BASE_URL = "https://rival.example.com/api/v1";

function runtimeSpec() {
  return {
    target_id: TARGET_ID,
    provider: `diagnostic-target/${TARGET_ID}`,
    model_id: "vendor/target-model",
    base_url: BASE_URL,
    credential_env_name: "OPENROUTER_API_KEY",
  };
}

type TargetFetchOptions = {
  policy: unknown;
  tracker: unknown;
  provider: unknown;
  resolveAddresses: unknown;
};

const createTargetFetchMock = vi.hoisted(() =>
  vi.fn(() => (async () => new Response("{}")) as typeof fetch),
);

vi.mock("./diagnostic-target-fetch", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./diagnostic-target-fetch")>();
  return {
    ...actual,
    createDiagnosticTargetFetch: createTargetFetchMock,
  };
});

afterEach(() => {
  createTargetFetchMock.mockClear();
  vi.unstubAllEnvs();
});

describe("diagnostic egress gate", () => {
  it("denies without an explicit live grant", () => {
    expect(resolveDiagnosticEgressMode({} as NodeJS.ProcessEnv)).toBe("deny");
    expect(
      resolveDiagnosticEgressMode({
        [DIAGNOSTIC_EGRESS_ENV]: "live",
      } as unknown as NodeJS.ProcessEnv),
    ).toBe("deny");
    expect(
      resolveDiagnosticEgressMode({
        [DIAGNOSTIC_EGRESS_ENV]: "live",
        LIBRETILES_AI_PLAY_LIVE: "1",
      } as unknown as NodeJS.ProcessEnv),
    ).toBe("live");
  });
});

describe("parseDiagnosticRuntimeSpec", () => {
  it("accepts the exact five-field backend shape", () => {
    const spec = parseDiagnosticRuntimeSpec(runtimeSpec());
    expect(spec).toEqual(runtimeSpec());
  });

  it("fails closed on extra fields, wrong types, and wrong provider identity", () => {
    expect(parseDiagnosticRuntimeSpec(null)).toBeNull();
    expect(parseDiagnosticRuntimeSpec({ ...runtimeSpec(), extra: 1 })).toBeNull();
    expect(parseDiagnosticRuntimeSpec({ ...runtimeSpec(), target_id: "not-a-uuid" })).toBeNull();
    expect(parseDiagnosticRuntimeSpec({ ...runtimeSpec(), provider: "openrouter" })).toBeNull();
    expect(parseDiagnosticRuntimeSpec({ ...runtimeSpec(), base_url: "http://rival.example.com" })).toBeNull();
    expect(
      parseDiagnosticRuntimeSpec({ ...runtimeSpec(), credential_env_name: "DJANGO_SECRET_KEY" }),
    ).toBeNull();
    expect(parseDiagnosticRuntimeSpec({ ...runtimeSpec(), model_id: "" })).toBeNull();
  });
});

describe("getDiagnosticLanguageRuntime", () => {
  it("denies before any credential lookup when egress policy denies", async () => {
    const env = {} as NodeJS.ProcessEnv;
    await expect(
      getDiagnosticLanguageRuntime({ runtime: runtimeSpec(), env }),
    ).rejects.toBeInstanceOf(DiagnosticEgressDeniedError);
    expect(createTargetFetchMock).not.toHaveBeenCalled();
  });

  it("reports missing credentials only after the egress gate passes", async () => {
    const env = {
      [DIAGNOSTIC_EGRESS_ENV]: "live",
      LIBRETILES_AI_PLAY_LIVE: "1",
    } as unknown as NodeJS.ProcessEnv;
    await expect(
      getDiagnosticLanguageRuntime({ runtime: runtimeSpec(), env }),
    ).rejects.toMatchObject({ code: "provider_auth_failed" });
    expect(createTargetFetchMock).not.toHaveBeenCalled();
  });

  it("builds the sibling runtime over the validated policy and bound fetch", async () => {
    const env = {
      [DIAGNOSTIC_EGRESS_ENV]: "live",
      LIBRETILES_AI_PLAY_LIVE: "1",
      OPENROUTER_API_KEY: "sk-test-diagnostic-credential-1234567890",
    } as unknown as NodeJS.ProcessEnv;
    const result = await getDiagnosticLanguageRuntime({ runtime: runtimeSpec(), env });
    expect(result.model).toBeDefined();
    expect(result.tracker.snapshot().provider_requests).toBe(0);
    expect(createTargetFetchMock).toHaveBeenCalledTimes(1);
    const call = (createTargetFetchMock.mock.calls as unknown as TargetFetchOptions[][])[0][0];
    expect(call.policy).toEqual({ hostname: "rival.example.com", canonicalBaseURL: BASE_URL });
    expect(call.provider).toBe(`diagnostic-target/${TARGET_ID}`);
    expect(call.tracker).toBe(result.tracker);
  });

  it("refuses credential env names outside the closed set", async () => {
    const env = {
      [DIAGNOSTIC_EGRESS_ENV]: "live",
      LIBRETILES_AI_PLAY_LIVE: "1",
      DJANGO_SECRET_KEY: "x".repeat(60),
    } as unknown as NodeJS.ProcessEnv;
    await expect(
      getDiagnosticLanguageRuntime({
        runtime: { ...runtimeSpec(), credential_env_name: "DJANGO_SECRET_KEY" },
        env,
      }),
    ).rejects.toMatchObject({ code: "provider_auth_failed" });
    expect(createTargetFetchMock).not.toHaveBeenCalled();
  });

  it("keeps the closed credential env set equal to the provider-logging export", () => {
    expect(CREDENTIAL_ENV_NAMES.length).toBeGreaterThan(0);
    expect(CREDENTIAL_ENV_NAMES).not.toContain("DJANGO_SECRET_KEY");
  });
});
