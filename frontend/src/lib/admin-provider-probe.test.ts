import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ADMIN_PROBE_LIVE_SENTINEL,
  ADMIN_PROBE_MAX_HTTP_DISPATCHES,
  installAdminProbeFetchGuard,
  parseAdminProbeCommand,
  runAdminProviderProbe,
} from "./admin-provider-probe";

const mocks = vi.hoisted(() => ({
  probeProviderCapability: vi.fn(),
}));

vi.mock("./provider-capability", () => ({
  probeProviderCapability: mocks.probeProviderCapability,
}));

afterEach(() => {
  mocks.probeProviderCapability.mockReset();
  vi.unstubAllGlobals();
});

describe("admin provider probe", () => {
  it("returns a simulated fake PASS without constructing a runtime", async () => {
    const result = await runAdminProviderProbe(
      {
        version: 1,
        mode: "fake",
        provider: "groq",
        model: "openai/gpt-oss-120b",
      },
      { [ADMIN_PROBE_LIVE_SENTINEL]: "1" },
    );

    expect(result).toEqual({
      version: 1,
      executed_runtime_mode: "fake",
      provider: "groq",
      model: "openai/gpt-oss-120b",
      status: "pass",
      latency_ms: 0,
      outbound_count: 0,
      reason_code: "simulated",
    });
    expect(mocks.probeProviderCapability).not.toHaveBeenCalled();
  });

  it("refuses live mode when the sentinel is not exactly 1", async () => {
    const result = await runAdminProviderProbe(
      {
        version: 1,
        mode: "live",
        provider: "groq",
        model: "openai/gpt-oss-120b",
      },
      { [ADMIN_PROBE_LIVE_SENTINEL]: "true" },
    );

    expect(result.reason_code).toBe("live_disabled");
    expect(result.outbound_count).toBe(0);
    expect(mocks.probeProviderCapability).not.toHaveBeenCalled();
  });

  it("forwards not_configured live results with zero outbound count", async () => {
    mocks.probeProviderCapability.mockResolvedValue({
      provider: "groq",
      model: "openai/gpt-oss-120b",
      status: "not_configured",
      latency_ms: 3,
      outbound_count: 0,
    });

    const result = await runAdminProviderProbe(
      {
        version: 1,
        mode: "live",
        provider: "groq",
        model: "openai/gpt-oss-120b",
      },
      { [ADMIN_PROBE_LIVE_SENTINEL]: "1" },
    );

    expect(result.status).toBe("not_configured");
    expect(result.reason_code).toBe("not_configured");
    expect(result.outbound_count).toBe(0);
  });

  it("rejects unexpected diagnostic target fields", () => {
    expect(() =>
      parseAdminProbeCommand(
        JSON.stringify({
          version: 1,
          mode: "fake",
          provider: "groq",
          model: "openai/gpt-oss-120b",
          diagnostic_target_id: "not-allowed",
        }),
      ),
    ).toThrow("malformed_output");
  });

  it("blocks a fifth fetch before dispatch", async () => {
    const original = globalThis.fetch;
    let realCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        realCalls += 1;
        return new Response("{}", { status: 200 });
      }),
    );
    const guard = installAdminProbeFetchGuard(ADMIN_PROBE_MAX_HTTP_DISPATCHES);
    try {
      for (let index = 0; index < 4; index += 1) {
        await globalThis.fetch("https://example.invalid/probe");
      }
      await expect(globalThis.fetch("https://example.invalid/probe")).rejects.toMatchObject({
        name: "RequestLimitError",
      });
      expect(realCalls).toBe(4);
      expect(guard.dispatched()).toBe(4);
      expect(guard.limited()).toBe(true);
    } finally {
      guard.restore();
      globalThis.fetch = original;
    }
  });
});
