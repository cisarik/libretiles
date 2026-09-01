import { describe, expect, it } from "vitest";
import { buildSecurityHeaders } from "./security-headers";

const REQUIRED_HEADER_NAMES = [
  "Content-Security-Policy",
  "X-Content-Type-Options",
  "Referrer-Policy",
  "X-Frame-Options",
  "Permissions-Policy",
  "Cross-Origin-Opener-Policy",
] as const;

function cspFrom(headers: Record<string, string>): string {
  const csp = headers["Content-Security-Policy"];
  expect(csp).toBeDefined();
  return csp;
}

function directiveSources(csp: string, name: string): string[] {
  const match = csp
    .split(";")
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name} `));
  expect(match, `missing CSP directive ${name}`).toBeDefined();
  return (match as string).split(/\s+/).slice(1);
}

describe("buildSecurityHeaders", () => {
  it("emits every required security header", () => {
    const headers = buildSecurityHeaders({
      isDevelopment: true,
      configuredApiUrl: undefined,
      requestHostname: "localhost",
    });
    for (const name of REQUIRED_HEADER_NAMES) {
      expect(headers[name], `missing header ${name}`).toBeTruthy();
    }
  });

  it("locks the required CSP directives", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: true,
        configuredApiUrl: undefined,
        requestHostname: "localhost",
      }),
    );
    expect(directiveSources(csp, "default-src")).toEqual(["'self'"]);
    expect(directiveSources(csp, "frame-ancestors")).toEqual(["'none'"]);
    expect(directiveSources(csp, "object-src")).toEqual(["'none'"]);
    expect(directiveSources(csp, "base-uri")).toEqual(["'self'"]);
    expect(directiveSources(csp, "form-action")).toEqual(["'self'"]);
  });

  it("allows a configured non-loopback https API origin and its wss counterpart", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: false,
        configuredApiUrl: "https://api.libretiles.example",
        requestHostname: "play.libretiles.example",
      }),
    );
    const connectSrc = directiveSources(csp, "connect-src");
    expect(connectSrc).toContain("'self'");
    expect(connectSrc).toContain("https://api.libretiles.example");
    expect(connectSrc).toContain("wss://api.libretiles.example");
  });

  it("defaults connect-src to localhost HTTP and WS when NEXT_PUBLIC_API_URL is unset", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: true,
        configuredApiUrl: undefined,
        requestHostname: "localhost",
      }),
    );
    const connectSrc = directiveSources(csp, "connect-src");
    expect(connectSrc).toContain("http://localhost:8000");
    expect(connectSrc).toContain("ws://localhost:8000");
  });

  it("rewrites loopback API origins onto a non-loopback request host", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: true,
        configuredApiUrl: "http://localhost:8000",
        requestHostname: "192.168.10.25",
      }),
    );
    const connectSrc = directiveSources(csp, "connect-src");
    expect(connectSrc).toContain("http://192.168.10.25:8000");
    expect(connectSrc).toContain("ws://192.168.10.25:8000");
  });

  it("omits Strict-Transport-Security in development and emits it in production", () => {
    const development = buildSecurityHeaders({
      isDevelopment: true,
      configuredApiUrl: undefined,
      requestHostname: "localhost",
    });
    const production = buildSecurityHeaders({
      isDevelopment: false,
      configuredApiUrl: "https://api.libretiles.example",
      requestHostname: "play.libretiles.example",
    });
    expect(development["Strict-Transport-Security"]).toBeUndefined();
    expect(production["Strict-Transport-Security"]).toBeTruthy();
  });

  it("omits upgrade-insecure-requests in development", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: true,
        configuredApiUrl: undefined,
        requestHostname: "localhost",
      }),
    );
    expect(csp).not.toMatch(/upgrade-insecure-requests/);
  });

  it("does not allow unsafe-eval in production script-src", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: false,
        configuredApiUrl: "https://api.libretiles.example",
        requestHostname: "play.libretiles.example",
      }),
    );
    expect(directiveSources(csp, "script-src")).not.toContain("'unsafe-eval'");
  });

  it("emits every required security header in production", () => {
    const headers = buildSecurityHeaders({
      isDevelopment: false,
      configuredApiUrl: "https://api.libretiles.example",
      requestHostname: "play.libretiles.example",
    });
    for (const name of REQUIRED_HEADER_NAMES) {
      expect(headers[name], `missing header ${name}`).toBeTruthy();
    }
  });

  it("locks the required CSP directives in production", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: false,
        configuredApiUrl: "https://api.libretiles.example",
        requestHostname: "play.libretiles.example",
      }),
    );
    expect(directiveSources(csp, "default-src")).toEqual(["'self'"]);
    expect(directiveSources(csp, "frame-ancestors")).toEqual(["'none'"]);
    expect(directiveSources(csp, "object-src")).toEqual(["'none'"]);
    expect(directiveSources(csp, "base-uri")).toEqual(["'self'"]);
    expect(directiveSources(csp, "form-action")).toEqual(["'self'"]);
  });

  it("emits upgrade-insecure-requests in production", () => {
    const csp = cspFrom(
      buildSecurityHeaders({
        isDevelopment: false,
        configuredApiUrl: "https://api.libretiles.example",
        requestHostname: "play.libretiles.example",
      }),
    );
    expect(csp).toMatch(/upgrade-insecure-requests/);
  });
});
