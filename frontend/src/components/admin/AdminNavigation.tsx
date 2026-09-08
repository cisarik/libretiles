"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import styles from "./admin.module.css";

export function adminNavigationState(pathname: string) {
  const replay = pathname.match(/^\/admin\/replay\/([^/]+)/);
  return {
    games: pathname === "/admin",
    playground: pathname.startsWith("/admin/playground"),
    analytics: pathname.startsWith("/admin/analytics"),
    replay: Boolean(replay),
    replayId: replay?.[1]?.replaceAll("-", "").slice(0, 12) ?? null,
  };
}

export function AdminNavigation() {
  const pathname = usePathname();
  const state = adminNavigationState(pathname);
  const active = (selected: boolean) => selected ? { "aria-current": "page" as const, className: styles.activeNav } : {};
  return <nav className={styles.nav} aria-label="Admin navigation">
    <Link href="/admin" {...active(state.games)}>Games List</Link>
    <Link href="/admin/playground" {...active(state.playground)}>Simulation Playground</Link>
    <Link href="/admin/analytics" {...active(state.analytics)}>Model Analytics</Link>
    {state.replay ? <span className={styles.activeNav} aria-current="page">Replay Studio · {state.replayId}</span> : <span title="Open a game from Games List">Replay Studio</span>}
    <Link className={styles.back} href="/play">← Back to Game</Link>
  </nav>;
}
