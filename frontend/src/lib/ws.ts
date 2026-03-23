import { resolveApiBase } from "@/lib/api";

export function buildGameWebSocketUrl(gameId: string, ticket: string): string {
  const apiBase = resolveApiBase();
  const apiUrl = new URL(apiBase);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = `/ws/game/${gameId}/`;
  apiUrl.search = `ticket=${encodeURIComponent(ticket)}`;
  return apiUrl.toString();
}
