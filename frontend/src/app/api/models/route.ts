/**
 * Models API Route — proxies the Django catalog for the frontend.
 *
 * Returns the list of active AI models configured by admin in Django.
 * The frontend calls this instead of Django directly to avoid CORS
 * complexity and to keep the Django URL server-side only.
 */

import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/catalog/models/`, {
      next: { revalidate: 60 },
    });

    if (!res.ok) {
      return NextResponse.json([], { status: 200 });
    }

    const models = await res.json();
    return NextResponse.json(models);
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}
