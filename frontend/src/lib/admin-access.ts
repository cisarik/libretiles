const REPLAY_PATH = /^\/admin\/replay\/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ADMIN_PATHS = new Set(["/admin", "/admin/playground", "/admin/analytics"]);

export function safeAdminCallback(value: string | null | undefined): string {
  if (!value || value.includes("\\") || value.startsWith("//")) return "/admin";
  if (value.includes("?") || value.includes("#") || value === "/admin/login") return "/admin";
  return ADMIN_PATHS.has(value) || REPLAY_PATH.test(value) ? value : "/admin";
}
