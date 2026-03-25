import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/catalog/prompts/`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json([], { status: 200 });
    }

    const prompts = await res.json();
    return NextResponse.json(prompts);
  } catch {
    return NextResponse.json([], { status: 200 });
  }
}
