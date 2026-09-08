const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function simulationBackendRequest(
  path: string,
  token: string,
  body?: unknown,
): Promise<{ status: number; data: Record<string, unknown> }> {
  const response = await fetch(`${BACKEND_URL}${path}`, {
    method: body === undefined ? "GET" : "POST",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const raw = await response.text();
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    data = { detail: "The simulation backend returned a non-JSON response." };
  }
  return {
    status: response.status,
    data:
      typeof data === "object" && data !== null && !Array.isArray(data)
        ? (data as Record<string, unknown>)
        : {},
  };
}

export function simulationSse(data: Record<string, unknown>): string {
  return `data: ${JSON.stringify(data)}\n\n`;
}
