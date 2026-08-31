import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { buildSecurityHeaders } from "@/lib/security-headers";

export function middleware(request: NextRequest) {
  const headers = buildSecurityHeaders({
    isDevelopment: process.env.NODE_ENV === "development",
    configuredApiUrl: process.env.NEXT_PUBLIC_API_URL,
    requestHostname: request.nextUrl.hostname,
  });

  const response = NextResponse.next();
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
