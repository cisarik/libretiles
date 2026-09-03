import { NextRequest, NextResponse } from "next/server";
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { config, proxy } from "./proxy";

const NEXT_NONCE_VALUE = /^[A-Za-z0-9+/_-]+={0,2}$/;

function pageRequest(path: string): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`);
}

function cspOf(response: Response): string {
  const csp = response.headers.get("Content-Security-Policy");
  expect(csp).toBeTruthy();
  return csp as string;
}

function scriptSrcSources(csp: string): string[] {
  const match = csp
    .split(";")
    .map((part) => part.trim())
    .find((part) => part === "script-src" || part.startsWith("script-src "));
  expect(match, "missing CSP directive script-src").toBeDefined();
  return (match as string).split(/\s+/).slice(1);
}

function nonceFromCsp(csp: string): string {
  const nonces = scriptSrcSources(csp)
    .map((source) => source.match(/^'nonce-([A-Za-z0-9+/_-]+={0,2})'$/))
    .filter((matched): matched is RegExpMatchArray => matched !== null)
    .map((matched) => matched[1]);
  expect(nonces).toHaveLength(1);
  return nonces[0];
}

type NextInit = {
  request?: { headers?: Headers };
};

describe("proxy matcher (AC-PROXY-MATCH, decision-lock)", () => {
  it("matches rendered pages and API routes, and excludes static assets and prefetch", () => {
    expect(unstable_doesMiddlewareMatch({ config, url: "/" })).toBe(true);
    expect(unstable_doesMiddlewareMatch({ config, url: "/api/models" })).toBe(
      true,
    );
    expect(
      unstable_doesMiddlewareMatch({ config, url: "/_next/static/x.js" }),
    ).toBe(false);
    expect(unstable_doesMiddlewareMatch({ config, url: "/_next/image" })).toBe(
      false,
    );
    expect(unstable_doesMiddlewareMatch({ config, url: "/favicon.ico" })).toBe(
      false,
    );
    expect(
      unstable_doesMiddlewareMatch({
        config,
        url: "/",
        headers: { purpose: "prefetch" },
      }),
    ).toBe(false);
  });
});

describe("proxy nonce propagation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("forwards request CSP equal to the response CSP on rendered pages (AC-PROXY-PROPAGATE)", () => {
    const nextSpy = vi.spyOn(NextResponse, "next");
    const response = proxy(pageRequest("/"));
    expect(nextSpy).toHaveBeenCalledTimes(1);
    const init = nextSpy.mock.calls[0][0] as NextInit | undefined;
    expect(init?.request?.headers).toBeInstanceOf(Headers);
    const forwarded = init!.request!.headers!.get("Content-Security-Policy");
    const responseCsp = cspOf(response);
    expect(forwarded).toBe(responseCsp);
    expect(nonceFromCsp(responseCsp)).toMatch(NEXT_NONCE_VALUE);
    expect(scriptSrcSources(responseCsp)).not.toContain("'unsafe-inline'");
    expect(init!.request!.headers!.get("x-nonce")).toBeNull();
    expect(response.headers.get("x-nonce")).toBeNull();
    for (const [name] of response.headers) {
      expect(name.toLowerCase()).not.toBe("x-nonce");
    }
  });

  it("sets response CSP on API routes without a request-header override (AC-PROXY-API)", () => {
    const nextSpy = vi.spyOn(NextResponse, "next");
    const response = proxy(pageRequest("/api/models"));
    expect(nextSpy).toHaveBeenCalledTimes(1);
    expect(nextSpy.mock.calls[0]).toEqual([]);
    const responseCsp = cspOf(response);
    expect(nonceFromCsp(responseCsp)).toMatch(NEXT_NONCE_VALUE);
    expect(scriptSrcSources(responseCsp)).not.toContain("'unsafe-inline'");
  });

  it("mints a fresh nonce per invocation (AC-NONCE-FRESH)", () => {
    const nextSpy = vi.spyOn(NextResponse, "next");
    const first = proxy(pageRequest("/"));
    const firstInit = nextSpy.mock.calls[0][0] as NextInit | undefined;
    const firstResponseCsp = cspOf(first);
    expect(firstInit?.request?.headers?.get("Content-Security-Policy")).toBe(
      firstResponseCsp,
    );
    const firstNonce = nonceFromCsp(firstResponseCsp);
    expect(firstNonce).toMatch(NEXT_NONCE_VALUE);

    nextSpy.mockClear();

    const second = proxy(pageRequest("/"));
    const secondInit = nextSpy.mock.calls[0][0] as NextInit | undefined;
    const secondResponseCsp = cspOf(second);
    expect(secondInit?.request?.headers?.get("Content-Security-Policy")).toBe(
      secondResponseCsp,
    );
    const secondNonce = nonceFromCsp(secondResponseCsp);
    expect(secondNonce).toMatch(NEXT_NONCE_VALUE);
    expect(secondNonce).not.toBe(firstNonce);
  });
});
