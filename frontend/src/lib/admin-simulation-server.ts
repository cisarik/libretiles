const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/**
 * Fixed public error contract for the simulation proxy. Raw backend `detail`
 * strings, nested objects, HTML, headers, and exception text are never
 * forwarded; only the HTTP status class selects the public message.
 */
const SIMULATION_ERROR_DETAILS: Record<
  number,
  { detail: string; code?: string }
> = {
  400: { detail: "The simulation request was invalid." },
  401: { detail: "Authentication credentials were invalid or expired." },
  403: { detail: "Staff access is required." },
  404: { detail: "Not found." },
  409: {
    detail: "The simulation state changed. Reload and retry.",
    code: "state_conflict",
  },
  429: { detail: "Too many simulation requests. Retry later." },
};

const UNAVAILABLE_DETAIL = "The simulation backend is unavailable.";

export function projectedSimulationError(status: number): {
  status: number;
  detail: string;
  code?: string;
} {
  if (status >= 500) {
    return { status: 503, detail: UNAVAILABLE_DETAIL };
  }
  const known = SIMULATION_ERROR_DETAILS[status];
  if (known) return { status, ...known };
  if (status >= 400 && status < 500) {
    return { status, detail: SIMULATION_ERROR_DETAILS[400].detail };
  }
  return { status: 503, detail: UNAVAILABLE_DETAIL };
}

export async function simulationBackendRequest(
  path: string,
  token: string,
  body?: unknown,
): Promise<{ status: number; data: Record<string, unknown> }> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { status: 503, data: {} };
  }
  const raw = await response.text();
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    data = null;
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