const DEFAULT_API_BASE = "http://localhost:8000";

const REQUIRED_RESPONSE_HEADERS = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cross-Origin-Opener-Policy": "same-origin",
} as const;

export type SecurityHeaderContext = {
  isDevelopment: boolean;
  configuredApiUrl: string | undefined;
  requestHostname: string | undefined;
};

function isLoopbackHostname(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

/**
 * Mirror of resolveApiBase() using the request hostname instead of window.
 * Do not change resolveApiBase(); this copy exists so CSP can be unit-tested.
 */
export function resolveConnectApiBase(
  configuredApiUrl: string | undefined,
  requestHostname: string | undefined,
): string {
  const configuredBase = trimTrailingSlash(
    configuredApiUrl || DEFAULT_API_BASE,
  );

  if (!requestHostname || isLoopbackHostname(requestHostname)) {
    return configuredBase;
  }

  try {
    const configuredUrl = new URL(configuredBase);
    if (!isLoopbackHostname(configuredUrl.hostname)) {
      return configuredBase;
    }
    configuredUrl.hostname = requestHostname;
    return trimTrailingSlash(configuredUrl.toString());
  } catch {
    return configuredBase;
  }
}

function httpAndWsOrigins(apiBase: string): {
  httpOrigin: string;
  wsOrigin: string;
} {
  try {
    const url = new URL(apiBase);
    const httpOrigin = url.origin;
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return { httpOrigin, wsOrigin: `${url.protocol}//${url.host}` };
  } catch {
    return {
      httpOrigin: "http://localhost:8000",
      wsOrigin: "ws://localhost:8000",
    };
  }
}

const NONCE_GRAMMAR = /^[A-Za-z0-9+/_-]+={0,2}$/;

function assertNonceGrammar(nonce: string): void {
  if (!NONCE_GRAMMAR.test(nonce)) {
    throw new Error("CSP nonce does not match the Next.js nonce grammar");
  }
}

export function buildContentSecurityPolicy(
  context: SecurityHeaderContext,
  nonce: string,
): string {
  assertNonceGrammar(nonce);
  const apiBase = resolveConnectApiBase(
    context.configuredApiUrl,
    context.requestHostname,
  );
  const { httpOrigin, wsOrigin } = httpAndWsOrigins(apiBase);
  const scriptSrc = [
    "'self'",
    `'nonce-${nonce}'`,
    "'strict-dynamic'",
    ...(context.isDevelopment ? ["'unsafe-eval'"] : []),
  ].join(" ");

  const directives = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self' ${httpOrigin} ${wsOrigin}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ];
  if (!context.isDevelopment) {
    directives.push("upgrade-insecure-requests");
  }
  return directives.join("; ");
}

export function buildSecurityHeaders(
  context: SecurityHeaderContext,
  nonce: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Security-Policy": buildContentSecurityPolicy(context, nonce),
    ...REQUIRED_RESPONSE_HEADERS,
  };
  if (!context.isDevelopment) {
    headers["Strict-Transport-Security"] =
      "max-age=31536000; includeSubDomains";
  }
  return headers;
}
