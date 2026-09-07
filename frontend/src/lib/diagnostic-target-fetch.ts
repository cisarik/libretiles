/**
 * Diagnostic-only OpenAI-compatible target transport (S7).
 *
 * One URL policy shared with the Python module
 * ``backend/game/diagnostic_targets.py`` (plan D2), consumed negative vectors
 * shared through ``backend/tests/fixtures/diagnostic_ssrf_cases.json``.
 *
 * Request time: POST only to exactly ``<canonical base>/chat/completions``,
 * fresh all-address DNS per provider request, every resolved address checked
 * against the public-unicast IP policy, and a bound ``node:https`` transport
 * with a dedicated non-reusing agent whose custom lookup returns ONLY the
 * validated address (no re-resolution, no redirects, no proxy, no ambient
 * agent). All security tests mock the resolver and transport.
 *
 * FAKE MODE ONLY in this slice: the worker never reaches live dispatch.
 */

import * as dns from "node:dns";
import * as https from "node:https";
import type { LookupFunction } from "node:net";
import type { ProviderRequestTracker } from "./openai-compatible";
import { recordProviderFailure } from "./provider-logging";

export const MAX_REQUEST_BODY_BYTES = 1_048_576;
export const MAX_RESPONSE_BODY_BYTES = 2_097_152;
export const DNS_TIMEOUT_MS = 2_000;
export const CONNECT_TIMEOUT_MS = 10_000;
const CHAT_COMPLETIONS_SUFFIX = "/chat/completions";

export class DiagnosticTargetFetchError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "DiagnosticTargetFetchError";
    this.code = code;
  }
}

export type TargetURLPolicy = {
  hostname: string;
  canonicalBaseURL: string;
};

export type ResolveAddresses = (hostname: string) => Promise<string[]>;

export type DiagnosticTransportResponse = {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  arrayBuffer: () => Promise<ArrayBuffer>;
};

export type DiagnosticTransport = (request: {
  url: URL;
  headers: Record<string, string>;
  body: Uint8Array;
  address: string;
  family: 4 | 6;
  signal: AbortSignal | null | undefined;
}) => Promise<DiagnosticTransportResponse>;

const HOST_LABEL_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const ASCII_NETLOC_PATTERN = /^[\x21-\x7e]+$/;
const IPV4_CANDIDATE_PATTERN = /^[0-9.]+$/;

function refuse(code: string, message: string): never {
  throw new DiagnosticTargetFetchError(code, message);
}

export function validateCanonicalHostname(host: string): string {
  if (!host) refuse("hostname_invalid", "hostname is empty");
  if (host.length > 253) {
    refuse("hostname_invalid", "hostname exceeds 253 characters");
  }
  if (!ASCII_NETLOC_PATTERN.test(host)) {
    refuse("hostname_invalid", "hostname carries non-ASCII characters");
  }
  if (host.includes("%")) {
    refuse("hostname_invalid", "hostname carries a percent-escape");
  }
  if (host !== host.toLowerCase()) {
    refuse("hostname_not_canonical", "hostname must already be canonical lowercase");
  }
  if (host.endsWith(".")) {
    refuse("hostname_trailing_dot", "hostname ends with a dot");
  }
  if (host.includes(":")) {
    refuse("hostname_invalid", "hostname is an IPv6 literal");
  }
  if (IPV4_CANDIDATE_PATTERN.test(host)) {
    refuse("hostname_ip_literal", "hostname is an IPv4 literal");
  }
  const labels = host.split(".");
  if (labels.length < 2) {
    refuse("hostname_single_label", "hostname needs at least two labels");
  }
  for (const label of labels) {
    if (!label) refuse("hostname_empty_label", "hostname carries an empty label");
    if (label.startsWith("xn--")) {
      refuse("hostname_punycode", "punycode labels are refused");
    }
    if (!HOST_LABEL_PATTERN.test(label)) {
      refuse("hostname_invalid", "hostname label is not canonical LDH");
    }
  }
  return host;
}

export function parseTargetBaseURL(raw: string): TargetURLPolicy {
  const trimmed = raw ?? "";
  if (!trimmed.trim()) refuse("url_empty", "base_url is empty");
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    refuse("url_unparseable", "base_url is not a URL");
  }
  if (url.protocol !== "https:") {
    refuse("scheme_not_https", "base_url must use HTTPS");
  }
  const schemeIndex = trimmed.indexOf("://");
  const afterScheme = schemeIndex === -1 ? "" : trimmed.slice(schemeIndex + 3);
  const authority = afterScheme.split(/[/?#]/)[0] ?? "";
  if (!authority) refuse("url_no_host", "base_url carries no host");
  if (authority.includes("@")) refuse("url_userinfo", "base_url carries userinfo");
  if (authority.includes("%")) {
    refuse("url_percent_escape_host", "base_url host carries a percent-escape");
  }
  if (!ASCII_NETLOC_PATTERN.test(authority)) {
    refuse("url_non_ascii_host", "base_url host carries non-ASCII characters");
  }
  let hostPart = authority;
  if (hostPart.endsWith(":443")) {
    hostPart = hostPart.slice(0, -4);
  } else if (hostPart.includes(":")) {
    refuse("url_non_default_port", "only the implicit or :443 port is allowed");
  }
  if (hostPart !== hostPart.toLowerCase()) {
    refuse("url_non_canonical_host", "base_url host must already be canonical lowercase");
  }
  if (url.search) refuse("url_query", "base_url must not carry a query");
  if (url.hash) refuse("url_fragment", "base_url must not carry a fragment");
  const pathStart = afterScheme.indexOf("/");
  const rawPath =
    pathStart === -1 ? "/" : (afterScheme.slice(pathStart).split(/[?#]/)[0] ?? "/");
  if (rawPath.includes("%")) {
    refuse("url_percent_escape_path", "base_url path carries a percent-escape");
  }
  for (const segment of rawPath.split("/")) {
    if (segment === "." || segment === "..") {
      refuse("url_dot_path_segment", "base_url path carries a dot segment");
    }
  }
  const hostname = validateCanonicalHostname(url.hostname);
  const path = url.pathname === "/" ? "" : url.pathname;
  return { hostname, canonicalBaseURL: `https://${hostname}${path}` };
}

export function validateTargetBaseURLAgainstHost(
  raw: string,
  expectedHostname: string,
): TargetURLPolicy {
  const parsed = parseTargetBaseURL(raw);
  if (parsed.hostname !== validateCanonicalHostname(expectedHostname)) {
    refuse(
      "hostname_mismatch",
      "base_url host must equal the referenced allowed host exactly",
    );
  }
  return parsed;
}

/** The shared public-unicast IP policy. Any special range is refused. */
export function addressAllowed(address: string): boolean {
  const v4 = parseIPv4(address);
  if (v4 !== null) return !refusedIPv4(v4);
  const v6 = parseIPv6(address);
  if (v6 !== null) return !refusedIPv6(v6);
  return false;
}

function parseIPv4(input: string): [number, number, number, number] | null {
  const parts = input.split(".");
  if (parts.length !== 4) return null;
  const octets: number[] = [];
  for (const part of parts) {
    if (!/^(?:0|[1-9][0-9]{0,2})$/.test(part)) return null;
    const value = Number(part);
    if (value > 255) return null;
    octets.push(value);
  }
  return [octets[0], octets[1], octets[2], octets[3]];
}

function refusedIPv4(octets: [number, number, number, number]): boolean {
  const [o1, o2, o3] = octets;
  const inRanges: Array<(o1: number, o2: number, o3: number) => boolean> = [
    (a) => a === 0,
    (a) => a === 10,
    (a, b) => a === 100 && b >= 64 && b <= 127,
    (a) => a === 127,
    (a, b) => a === 169 && b === 254,
    (a, b) => a === 172 && b >= 16 && b <= 31,
    (a, b, c) => a === 192 && b === 0 && c === 0,
    (a, b, c) => a === 192 && b === 0 && c === 2,
    (a, b, c) => a === 192 && b === 88 && c === 99,
    (a, b) => a === 192 && b === 168,
    (a, b) => a === 198 && (b === 18 || b === 19),
    (a, b, c) => a === 198 && b === 51 && c === 100,
    (a, b, c) => a === 203 && b === 0 && c === 113,
    (a) => a >= 224 && a <= 239,
    (a) => a >= 240,
    (a, b, c) => a === 168 && b === 63 && c === 129 && octets[3] === 16,
  ];
  return inRanges.some((matches) => matches(o1, o2, o3));
}

function parseIPv6(input: string): number[] | null {
  const trimmed = input.trim();
  if (!trimmed || trimmed.includes("%")) return null;
  let head: string;
  let tail: string | null = null;
  const doubleColon = trimmed.split("::");
  if (doubleColon.length > 2) return null;
  if (doubleColon.length === 2) {
    head = doubleColon[0];
    tail = doubleColon[1];
  } else {
    head = trimmed;
  }
  const parseGroups = (text: string): { groups: number[]; v4Tail: number[] | null } | null => {
    if (text === "") return { groups: [], v4Tail: null };
    const pieces = text.split(":");
    if (pieces[pieces.length - 1].includes(".")) {
      const v4 = pieces.pop() as string;
      const parsedV4 = parseIPv4(v4);
      if (parsedV4 === null) return null;
      const v4Tail = [
        (parsedV4[0] << 8) | parsedV4[1],
        (parsedV4[2] << 8) | parsedV4[3],
      ];
      return { groups: pieces.map(parseGroup), v4Tail };
    }
    return { groups: pieces.map(parseGroup), v4Tail: null };
  };
  const parseGroup = (piece: string): number => {
    if (!/^[0-9a-fA-F]{1,4}$/.test(piece)) return -1;
    return parseInt(piece, 16);
  };
  const headParsed = parseGroups(head);
  if (headParsed === null || headParsed.groups.some((g) => g < 0)) return null;
  const groups = [...headParsed.groups];
  let v4Tail: number[] | null = headParsed.v4Tail;
  if (tail !== null) {
    const tailParsed = parseGroups(tail);
    if (tailParsed === null || tailParsed.groups.some((g) => g < 0)) return null;
    if (tailParsed.v4Tail !== null) v4Tail = tailParsed.v4Tail;
    groups.push(...tailParsed.groups);
  }
  if (v4Tail !== null) groups.push(...v4Tail);
  const fill = 8 - groups.length;
  if (fill < 0 || (tail === null && fill !== 0) || (tail !== null && fill < 1)) return null;
  const full = tail === null ? groups : [...groups.slice(0, headParsed.groups.length), ...Array<number>(fill).fill(0), ...groups.slice(headParsed.groups.length)];
  if (full.length !== 8 || full.some((g) => g < 0 || g > 0xffff)) return null;
  return full;
}

function refusedIPv6(groups: number[]): boolean {
  const g0 = groups[0];
  if (g0 < 0x2000 || g0 > 0x3fff) return true;
  const g1 = groups[1];
  if (g0 === 0x2001 && g1 <= 0x01ff) return true;
  if (g0 === 0x2001 && g1 === 0x0db8) return true;
  if (g0 === 0x2002) return true;
  if (g0 === 0x3fff && g1 <= 0x0fff) return true;
  return false;
}

export function assertAllAddressesAllowed(addresses: string[]): string[] {
  if (!addresses || addresses.length === 0) {
    refuse("dns_refused", "no address resolved for the diagnostic target host");
  }
  for (const address of addresses) {
    if (!addressAllowed(address)) {
      refuse(
        "dns_refused",
        "an address resolved for the diagnostic target host is not allowed",
      );
    }
  }
  return [...addresses];
}

export function createValidatingResolver(resolve: ResolveAddresses): ResolveAddresses {
  return async (hostname: string) => {
    let addresses: string[];
    try {
      addresses = await resolve(hostname);
    } catch {
      refuse("dns_refused", "resolving the diagnostic target host failed");
    }
    return assertAllAddressesAllowed(addresses ?? []);
  };
}

export function createNodeResolver(): ResolveAddresses {
  return async (hostname: string) => {
    const resolver = new dns.promises.Resolver({ timeout: DNS_TIMEOUT_MS, tries: 1 });
    const settled = await Promise.allSettled([
      resolver.resolve4(hostname),
      resolver.resolve6(hostname),
    ]);
    const addresses: string[] = [];
    let anyResolved = false;
    for (const outcome of settled) {
      if (outcome.status === "fulfilled") {
        anyResolved = true;
        for (const address of outcome.value) {
          if (!addresses.includes(address)) addresses.push(address);
        }
      }
    }
    if (!anyResolved) {
      refuse("dns_refused", "resolving the diagnostic target host failed");
    }
    return addresses;
  };
}

export function assertChatCompletionsURL(raw: string, policy: TargetURLPolicy): URL {
  const expected = policy.canonicalBaseURL + CHAT_COMPLETIONS_SUFFIX;
  if (raw !== expected) {
    refuse(
      "chat_url_mismatch",
      "provider requests go POST-only to exactly <canonical base>/chat/completions",
    );
  }
  return new URL(raw);
}

export function buildRequestOptions(
  url: URL,
  address: string,
  family: 4 | 6,
  headers: Record<string, string> = {},
): https.RequestOptions {
  const lookup: LookupFunction = (hostname, _options, callback) => {
    if (hostname !== url.hostname) {
      callback(
        new DiagnosticTargetFetchError(
          "lookup_mismatch",
          "lookup hostname left the validated policy",
        ),
        "",
        0,
      );
      return;
    }
    callback(null, address, family);
  };
  return {
    method: "POST",
    hostname: url.hostname,
    port: url.port ? Number(url.port) : 443,
    path: `${url.pathname}${url.search}`,
    servername: url.hostname,
    family,
    lookup,
    agent: new https.Agent({ keepAlive: false, maxSockets: 1, lookup }),
    timeout: CONNECT_TIMEOUT_MS,
    headers: {
      ...headers,
      ...(Object.keys(headers).some((key) => key.toLowerCase() === "content-length")
        ? {}
        : {}),
    },
  };
}

function concatChunks(chunks: Uint8Array[]): Uint8Array {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

export function createNodeHttpsTransport(): DiagnosticTransport {
  return async ({ url, headers, body, address, family, signal }) => {
    const options = buildRequestOptions(url, address, family, {
      ...headers,
      "Content-Length": String(body.byteLength),
    });
    return await new Promise<DiagnosticTransportResponse>((resolve, reject) => {
      let settled = false;
      const settle = (action: () => void) => {
        if (settled) return;
        settled = true;
        action();
      };
      const chunks: Uint8Array[] = [];
      let total = 0;
      const request = https.request(options, (response) => {
        const status = response.statusCode ?? 0;
        response.on("data", (chunk: Buffer) => {
          total += chunk.length;
          if (total > MAX_RESPONSE_BODY_BYTES) {
            response.destroy();
            request.destroy();
            settle(() =>
              reject(
                new DiagnosticTargetFetchError(
                  "response_body_too_large",
                  "response body exceeded the 2 MiB cap",
                ),
              ),
            );
            return;
          }
          chunks.push(new Uint8Array(chunk));
        });
        response.on("end", () => {
          const captured = chunks;
          settle(() =>
            resolve({
              status,
              headers: response.headers,
              arrayBuffer: async () => concatChunks(captured).buffer as ArrayBuffer,
            }),
          );
        });
        response.on("error", (error) => settle(() => reject(error)));
      });
      request.on("timeout", () => {
        request.destroy(
          new DiagnosticTargetFetchError(
            "connect_timeout",
            "provider connection exceeded the connect timeout",
          ),
        );
      });
      request.on("error", (error) => settle(() => reject(error)));
      const abort = () => {
        request.destroy(
          new DiagnosticTargetFetchError(
            "attempt_aborted",
            "the remaining attempt deadline elapsed",
          ),
        );
      };
      if (signal) {
        if (signal.aborted) {
          abort();
          return;
        }
        signal.addEventListener("abort", abort, { once: true });
      }
      request.write(Buffer.from(body));
      request.end();
    });
  };
}

function encodeRequestBody(body: unknown): Uint8Array {
  if (body === undefined || body === null) return new Uint8Array(0);
  if (typeof body === "string") return new TextEncoder().encode(body);
  if (body instanceof Uint8Array) return body;
  if (body instanceof ArrayBuffer) return new Uint8Array(body);
  refuse(
    "request_body_unsupported",
    "the request body must be a bounded string or bytes",
  );
}

function flattenHeaders(headers: Headers | undefined): Record<string, string> {
  const flat: Record<string, string> = {};
  if (!headers) return flat;
  headers.forEach((value, key) => {
    flat[key.toLowerCase()] = value;
  });
  return flat;
}

function headerValue(
  headers: Record<string, string | string[] | undefined>,
  name: string,
): string | null {
  const direct = headers[name];
  if (typeof direct === "string") return direct;
  if (Array.isArray(direct) && direct.length > 0) return direct[0];
  return null;
}

function responseHeaderRecord(
  headers: Record<string, string | string[] | undefined>,
): Record<string, string> {
  const flat: Record<string, string> = {};
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined) continue;
    flat[key] = Array.isArray(value) ? value.join(", ") : value;
  }
  return flat;
}

export type DiagnosticTargetFetchOptions = {
  policy: TargetURLPolicy;
  tracker: ProviderRequestTracker;
  provider: string;
  resolveAddresses: ResolveAddresses;
  transport?: DiagnosticTransport;
};

export function createDiagnosticTargetFetch(
  options: DiagnosticTargetFetchOptions,
): typeof globalThis.fetch {
  const transport = options.transport ?? createNodeHttpsTransport();
  return async (input, init) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (method !== "POST") {
      refuse("method_not_post", "provider requests are POST-only");
    }
    const raw =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    let chatURL: URL;
    let body: Uint8Array;
    try {
      chatURL = assertChatCompletionsURL(raw, options.policy);
      body = encodeRequestBody(init?.body);
      if (body.byteLength > MAX_REQUEST_BODY_BYTES) {
        refuse(
          "request_body_too_large",
          "request body exceeded the 1 MiB cap",
        );
      }
      const addresses = await options.resolveAddresses(options.policy.hostname);
      const validated = assertAllAddressesAllowed(addresses);
      const address = validated[0];
      const family: 4 | 6 = address.includes(":") ? 6 : 4;
      options.tracker.noteProviderRequest();
      const response = await transport({
        url: chatURL,
        headers: flattenHeaders(
          init?.headers instanceof Headers
            ? init.headers
            : new Headers((init?.headers ?? undefined) as HeadersInit | undefined),
        ),
        body,
        address,
        family,
        signal: init?.signal ?? null,
      });
      if (response.status >= 300 && response.status < 400) {
        refuse("redirect_refused", "redirect responses are refused, never followed");
      }
      const encoding = headerValue(response.headers, "content-encoding");
      if (encoding !== null && encoding.trim() !== "" && encoding.trim() !== "identity") {
        refuse(
          "compressed_response_refused",
          "compressed responses are refused; identity encoding only",
        );
      }
      const bytes = await response.arrayBuffer();
      if (bytes.byteLength > MAX_RESPONSE_BODY_BYTES) {
        refuse("response_body_too_large", "response body exceeded the 2 MiB cap");
      }
      return new Response(bytes, {
        status: response.status,
        headers: responseHeaderRecord(response.headers),
      });
    } catch (error) {
      recordProviderFailure({
        provider: options.provider,
        phase: "provider_transport",
        status: null,
        error,
      });
      if (error instanceof DiagnosticTargetFetchError) throw error;
      throw new DiagnosticTargetFetchError(
        "provider_transport_failed",
        "the diagnostic target transport failed",
      );
    }
  };
}
