import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ProviderRequestTracker } from "./openai-compatible";
import {
  MAX_REQUEST_BODY_BYTES,
  MAX_RESPONSE_BODY_BYTES,
  assertAllAddressesAllowed,
  addressAllowed,
  buildRequestOptions,
  createDiagnosticTargetFetch,
  parseTargetBaseURL,
  validateTargetBaseURLAgainstHost,
  type DiagnosticTransport,
  type ResolveAddresses,
  type TargetURLPolicy,
} from "./diagnostic-target-fetch";

const FIXTURE = JSON.parse(
  readFileSync(
    join(
      dirname(fileURLToPath(import.meta.url)),
      "../../../backend/tests/fixtures/diagnostic_ssrf_cases.json",
    ),
    "utf8",
  ),
) as {
  url_policy_rejects: Array<{ input: string; reason: string }>;
  ip_policy_rejects: string[];
  ip_policy_accepts: string[];
  allowed_hostnames_seed: string[];
};

const HOST = "rival.example.com";
const POLICY: TargetURLPolicy = { hostname: HOST, canonicalBaseURL: `https://${HOST}/api/v1` };

function trackerSpy(): ProviderRequestTracker & { requests: number } {
  let requests = 0;
  return {
    get requests() {
      return requests;
    },
    noteProviderRequest() {
      requests += 1;
    },
    recordUsage() {},
    recordRetryAfter() {},
    snapshot() {
      return { provider_requests: requests };
    },
  } as ProviderRequestTracker & { requests: number };
}

function okTransport(status = 200): DiagnosticTransport & { calls: number } {
  const transport = vi.fn(async () => ({
    status,
    headers: { "content-type": "application/json" },
    arrayBuffer: async () => new TextEncoder().encode("{}").buffer as ArrayBuffer,
  })) as unknown as DiagnosticTransport & { calls: number };
  Object.defineProperty(transport, "calls", {
    get: () => (transport as unknown as ReturnType<typeof vi.fn>).mock.calls.length,
  });
  return transport;
}

function fetchOptions(overrides: Partial<Parameters<typeof createDiagnosticTargetFetch>[0]> = {}) {
  const tracker = trackerSpy();
  return {
    tracker,
    options: {
      policy: POLICY,
      tracker,
      provider: "diagnostic-target/00000000-0000-0000-0000-0000000000aa",
      resolveAddresses: (async () => ["8.8.8.8"]) as ResolveAddresses,
      ...overrides,
    },
  };
}

function postInit(body: unknown = "{}", overrides: RequestInit = {}): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
    ...overrides,
  };
}

const CHAT_URL = `https://${HOST}/api/v1/chat/completions`;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("diagnostic target URL policy (shared SSRF fixture)", () => {
  it("rejects every shared vector", () => {
    for (const { input, reason } of FIXTURE.url_policy_rejects) {
      expect(() => parseTargetBaseURL(input), reason).toThrow();
    }
  });

  it("accepts a canonical https base and strips the default port", () => {
    const parsed = parseTargetBaseURL(`https://${HOST}/api/v1`);
    expect(parsed.hostname).toBe(HOST);
    expect(parsed.canonicalBaseURL).toBe(`https://${HOST}/api/v1`);
    const explicit = parseTargetBaseURL(`https://${HOST}:443/api/v1`);
    expect(explicit.canonicalBaseURL).toBe(`https://${HOST}/api/v1`);
  });

  it("requires exact hostname equality with the allowed host", () => {
    expect(() =>
      validateTargetBaseURLAgainstHost(`https://${HOST}/api/v1`, "other.example.com"),
    ).toThrow();
    expect(() =>
      validateTargetBaseURLAgainstHost(`https://${HOST}.evil.invalid/api/v1`, HOST),
    ).toThrow();
    expect(
      validateTargetBaseURLAgainstHost(`https://${HOST}/api/v1`, HOST).hostname,
    ).toBe(HOST);
  });
});

describe("diagnostic target IP policy (shared SSRF fixture)", () => {
  it("rejects every shared private/special vector", () => {
    for (const address of FIXTURE.ip_policy_rejects) {
      expect(addressAllowed(address), address).toBe(false);
    }
  });

  it("accepts every shared public unicast address", () => {
    for (const address of FIXTURE.ip_policy_accepts) {
      expect(addressAllowed(address), address).toBe(true);
    }
  });

  it("refuses the whole name when any address is disallowed", () => {
    expect(() => assertAllAddressesAllowed(["8.8.8.8", "10.0.0.1"])).toThrow();
    expect(() => assertAllAddressesAllowed([])).toThrow();
    expect(() => assertAllAddressesAllowed(["::ffff:10.0.0.1"])).toThrow();
  });
});

describe("diagnostic target request policy", () => {
  it("POSTs only to exactly <canonical base>/chat/completions", async () => {
    const transport = okTransport();
    const { tracker, options } = fetchOptions({ transport });
    const fetchFn = createDiagnosticTargetFetch(options);
    const response = await fetchFn(CHAT_URL, postInit());
    expect(response.status).toBe(200);
    expect(tracker.requests).toBe(1);
    for (const wrong of [
      `https://${HOST}/api/v1/chat/completions/extra`,
      `https://${HOST}/api/v1/completions`,
      `https://${HOST}/api/v2/chat/completions`,
      `${CHAT_URL}?x=1`,
    ]) {
      await expect(fetchFn(wrong, postInit())).rejects.toThrow();
    }
    expect(tracker.requests).toBe(1);
  });

  it("refuses non-POST methods before dispatch", async () => {
    const transport = okTransport();
    const { tracker, options } = fetchOptions({ transport });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, { method: "GET" })).rejects.toThrow();
    expect(tracker.requests).toBe(0);
    expect(transport.calls).toBe(0);
  });

  it("refuses redirects without following Location", async () => {
    const transport = vi.fn(async () => ({
      status: 302,
      headers: { location: "https://evil.invalid/steal" },
      arrayBuffer: async () => new TextEncoder().encode("").buffer as ArrayBuffer,
    })) as unknown as DiagnosticTransport;
    const { options } = fetchOptions({ transport });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, postInit())).rejects.toThrow(/redirect/i);
  });

  it("refuses compressed responses", async () => {
    const transport = vi.fn(async () => ({
      status: 200,
      headers: { "content-encoding": "br" },
      arrayBuffer: async () => new TextEncoder().encode("{}").buffer as ArrayBuffer,
    })) as unknown as DiagnosticTransport;
    const { options } = fetchOptions({ transport });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, postInit())).rejects.toThrow(/compress/i);
  });

  it("caps the request body at 1 MiB and the response body at 2 MiB", async () => {
    const bigBody = "x".repeat(MAX_REQUEST_BODY_BYTES + 1);
    const { tracker, options } = fetchOptions({ transport: okTransport() });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, postInit(bigBody))).rejects.toThrow(/request body/i);
    expect(tracker.requests).toBe(0);

    const hugeTransport = vi.fn(async () => ({
      status: 200,
      headers: {},
      arrayBuffer: async () => new ArrayBuffer(MAX_RESPONSE_BODY_BYTES + 1),
    })) as unknown as DiagnosticTransport;
    const capped = createDiagnosticTargetFetch(
      fetchOptions({ transport: hugeTransport }).options,
    );
    await expect(capped(CHAT_URL, postInit())).rejects.toThrow(/response body/i);
  });

  it("increments the tracker only after policy checks, immediately before dispatch", async () => {
    const order: string[] = [];
    const tracker = trackerSpy();
    const transport = vi.fn(async () => {
      order.push(`dispatch:${tracker.requests}`);
      return {
        status: 200,
        headers: {},
        arrayBuffer: async () => new TextEncoder().encode("{}").buffer as ArrayBuffer,
      };
    }) as unknown as DiagnosticTransport;
    const fetchFn = createDiagnosticTargetFetch({
      policy: POLICY,
      tracker,
      provider: "diagnostic-target/x",
      resolveAddresses: async () => {
        order.push("dns");
        return ["8.8.8.8"];
      },
      transport,
    });
    await fetchFn(CHAT_URL, postInit());
    expect(order).toEqual(["dns", "dispatch:1"]);
  });

  it("refuses the request before dispatch when DNS yields a private address", async () => {
    const transport = okTransport();
    const { tracker, options } = fetchOptions({
      transport,
      resolveAddresses: async () => ["8.8.8.8", "169.254.169.254"],
    });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, postInit())).rejects.toThrow();
    expect(tracker.requests).toBe(0);
    expect(transport.calls).toBe(0);
  });

  it("refuses the request when DNS resolution times out", async () => {
    const { tracker, options } = fetchOptions({
      resolveAddresses: async () => {
        throw new Error("dns timeout");
      },
    });
    const fetchFn = createDiagnosticTargetFetch(options);
    await expect(fetchFn(CHAT_URL, postInit())).rejects.toThrow();
    expect(tracker.requests).toBe(0);
  });
});

describe("bound node https transport (mocked module)", () => {
  it("binds the validated address through a non-reusing agent with no redirects", async () => {
    const options = buildRequestOptions(new URL(CHAT_URL), "93.184.216.34", 4);
    expect(options.method).toBe("POST");
    expect(options.servername).toBe(HOST);
    expect(options.agent).toBeDefined();
    expect(typeof options.lookup).toBe("function");
    const lookup = options.lookup as NonNullable<typeof options.lookup>;
    let foreignError: unknown = null;
    lookup(
      HOST,
      { all: false },
      (error, address, family) => {
        expect(error).toBeNull();
        expect(address).toBe("93.184.216.34");
        expect(family).toBe(4);
      },
    );
    lookup(
      "evil.example.com",
      { all: false },
      (error) => {
        foreignError = error;
      },
    );
    expect(foreignError).not.toBeNull();
  });
});
