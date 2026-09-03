import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { buildSecurityHeaders } from "@/lib/security-headers";

function isApiPath(pathname: string): boolean {
  return pathname === "/api" || pathname.startsWith("/api/");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const headers = buildSecurityHeaders(
    {
      isDevelopment: process.env.NODE_ENV === "development",
      configuredApiUrl: process.env.NEXT_PUBLIC_API_URL,
      requestHostname: request.nextUrl.hostname,
    },
    nonce,
  );

  let response: NextResponse;
  if (isApiPath(request.nextUrl.pathname)) {
    response = NextResponse.next();
  } else {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set(
      "Content-Security-Policy",
      headers["Content-Security-Policy"],
    );
    response = NextResponse.next({
      request: { headers: requestHeaders },
    });
  }

  for (const [name, value] of Object.entries(headers)) {
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
