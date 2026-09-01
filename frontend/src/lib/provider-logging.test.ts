import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PROVIDER_FAILURE_MESSAGE_MAX_LENGTH,
  recordProviderFailure,
} from "./provider-logging";

const SYNTHETIC_CREDENTIAL_SENTINEL =
  "sk-synthLOCALFAKEONLY_9f3a2c1b0e7d4a689f3a2c1b0e7d4a68";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("recordProviderFailure", () => {
  it("records provider, phase, status, and error class", () => {
    const write = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const record = recordProviderFailure({
      provider: "openrouter",
      phase: "provider_http",
      status: 401,
      error: new TypeError("synthetic provider rejection"),
    });
    expect(record.provider).toBe("openrouter");
    expect(record.phase).toBe("provider_http");
    expect(record.status).toBe(401);
    expect(record.errorClass).toBe("TypeError");
    expect(write).toHaveBeenCalled();
  });

  it("redacts a synthetic credential sentinel from the emitted record", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const record = recordProviderFailure({
      provider: "groq",
      phase: "provider_transport",
      error: new Error(`upstream rejected ${SYNTHETIC_CREDENTIAL_SENTINEL}`),
    });
    const serialized = JSON.stringify(record);
    expect(serialized).not.toContain(SYNTHETIC_CREDENTIAL_SENTINEL);
    expect(record.message).not.toContain(SYNTHETIC_CREDENTIAL_SENTINEL);
  });

  it("truncates messages longer than the bounded length", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const longMessage = "x".repeat(PROVIDER_FAILURE_MESSAGE_MAX_LENGTH + 80);
    const record = recordProviderFailure({
      provider: "mistral",
      phase: "generate_text",
      error: new Error(longMessage),
    });
    expect(record.message.length).toBe(PROVIDER_FAILURE_MESSAGE_MAX_LENGTH);
  });

  it("emits only the bounded record shape with no headers, bodies, or stack", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const error = new Error("synthetic failure");
    error.stack = "Error: synthetic failure\n    at secret.ts:1:1";
    const record = recordProviderFailure({
      provider: "nvidia-nim",
      phase: "provider_http",
      status: 503,
      error,
    });
    expect(Object.keys(record).sort()).toEqual(
      ["errorClass", "message", "phase", "provider", "status"].sort(),
    );
    const serialized = JSON.stringify(record);
    expect(serialized).not.toContain("stack");
    expect(serialized).not.toContain("Authorization");
    expect(serialized).not.toContain("secret.ts");
    expect(record).not.toHaveProperty("headers");
    expect(record).not.toHaveProperty("requestBody");
    expect(record).not.toHaveProperty("responseBody");
    expect(record).not.toHaveProperty("stack");
  });

  it("redacts a stubbed provider credential environment value from the record", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const stubbed = "hyphen-joined-groq-key";
    vi.stubEnv("GROQ_API_KEY", stubbed);
    const record = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(`upstream rejected ${stubbed}`),
    });
    expect(record.message).not.toContain(stubbed);
    expect(JSON.stringify(record)).not.toContain(stubbed);
  });

  it("redacts hyphen and punctuation bearer forms and sub-24-character credential-shaped runs", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const record = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(
        "denied bearer-secret Bearer:token bearer_token Xy9kLm2Qp8Rv4NtA",
      ),
    });
    expect(record.message).not.toContain("bearer-secret");
    expect(record.message).not.toContain("Bearer:token");
    expect(record.message).not.toContain("bearer_token");
    expect(record.message).not.toContain("Xy9kLm2Qp8Rv4NtA");
  });

  it("preserves the three observed benign diagnostic messages", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const generic = recordProviderFailure({
      provider: "openrouter",
      phase: "generate_text",
      error: new Error("generic SDK failure"),
    });
    const limited = recordProviderFailure({
      provider: "openrouter",
      phase: "generate_text",
      error: new Error("rate limited"),
    });
    const http = recordProviderFailure({
      provider: "ibm-watsonx",
      phase: "provider_http",
      status: 503,
      error: new Error("HTTP 503"),
    });
    expect(generic.message).toBe("generic SDK failure");
    expect(limited.message).toBe("rate limited");
    expect(http.message).toBe("HTTP 503");
  });

  it("does not redact ordinary text when a credential env value is absent, empty, whitespace, placeholder, or short", () => {
    vi.spyOn(process.stderr, "write").mockImplementation(() => true);
    const ordinary = "generic SDK failure";

    const absent = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(ordinary),
    });
    expect(absent.message).toBe(ordinary);

    vi.stubEnv("GROQ_API_KEY", "");
    const empty = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(ordinary),
    });
    expect(empty.message).toBe(ordinary);

    vi.stubEnv("GROQ_API_KEY", "   ");
    const whitespace = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(ordinary),
    });
    expect(whitespace.message).toBe(ordinary);

    vi.stubEnv("GROQ_API_KEY", "your-api-key");
    const placeholder = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(ordinary),
    });
    expect(placeholder.message).toBe(ordinary);

    vi.stubEnv("GROQ_API_KEY", "SDK");
    const short = recordProviderFailure({
      provider: "groq",
      phase: "generate_text",
      error: new Error(ordinary),
    });
    expect(short.message).toBe(ordinary);
  });
});

describe("provider-logging client import guard", () => {
  it("is not imported by client modules", () => {
    const srcRoot = path.resolve(__dirname, "..");
    const offenders: string[] = [];

    function walk(dir: string): void {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.tsx?$/.test(entry.name) || entry.name.endsWith(".test.ts")) {
          continue;
        }
        const source = fs.readFileSync(full, "utf8");
        if (!/from\s+["'](?:@\/lib\/provider-logging|\.\/provider-logging)["']/.test(source)) {
          continue;
        }
        const rel = path.relative(srcRoot, full).replaceAll("\\", "/");
        const isClientDirective = /^\s*["']use client["']/.test(source);
        const isClientTree =
          rel.startsWith("components/") ||
          rel.startsWith("hooks/") ||
          /(^|\/)page\.tsx$/.test(rel) ||
          /(^|\/)layout\.tsx$/.test(rel);
        if (isClientDirective || isClientTree) {
          offenders.push(rel);
        }
      }
    }

    walk(srcRoot);
    expect(offenders).toEqual([]);
  });
});
