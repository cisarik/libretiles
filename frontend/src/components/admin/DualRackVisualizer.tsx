"use client";

import { Tile } from "@/components/tiles/Tile";
import type { AdminReplayPlayer } from "@/lib/types";
import { PREMIUM_PANEL_STYLE, handlePremiumSurfacePointer } from "@/lib/premiumSurface";
import styles from "./admin.module.css";

export function playerLabel(player: AdminReplayPlayer | undefined, slot: number): string {
  if (!player) return `Player ${slot}`;
  if (player.is_ai) return player.model_display_name || player.model_id || "CPU bot";
  return player.username || `Player ${slot}`;
}

export function DualRackVisualizer({ players, racks, scores, actingSlot, currentPlyIndex, tilePoints, premium, live = false }: { players: AdminReplayPlayer[]; racks: [string[] | null, string[] | null]; scores: [number | null, number | null]; actingSlot: number | null; currentPlyIndex: number; tilePoints: Record<string, number>; premium: boolean; live?: boolean }) {
  return <div className="grid gap-3 lg:grid-cols-2">{([0, 1] as const).map((slot) => {
    const player = players.find((item) => item.slot === slot);
    const rack = racks[slot];
    const active = actingSlot === slot;
    const activeCopy = live ? (currentPlyIndex === 0 ? "Next to play" : "Thinking") : (currentPlyIndex === 0 ? "Starting player" : "Played this ply");
    return <section key={slot} className={`${styles.panel} p-4 ${active ? "ring-2 ring-amber-400" : ""}`} style={premium ? PREMIUM_PANEL_STYLE : undefined} onMouseMove={premium ? handlePremiumSurfacePointer : undefined} aria-label={`Player ${slot} rack`}><div className="flex items-start justify-between gap-3"><div><div className="text-xs font-black uppercase tracking-[.18em] text-amber-400">Player {slot}{active ? ` · ${activeCopy}` : ""}</div><h2 className="mt-1 font-black text-stone-100">{playerLabel(player, slot)}</h2></div><div className="text-right"><div className="text-2xl font-black text-amber-200">{scores[slot] ?? "?"}</div><div className="text-xs text-stone-500">{rack === null ? "? tiles" : `${rack.length} tiles`}</div></div></div>{rack === null ? <p className="mt-4 text-sm text-stone-400">Rack unavailable</p> : rack.length === 0 ? <p className="mt-4 text-sm text-stone-400">Empty rack</p> : <div className={`${styles.rackTiles} mt-4`}>{rack.map((token, index) => <div key={`${index}-${token}`} className={token === "?" ? styles.blank : ""} aria-label={token === "?" ? "Blank tile, zero points" : `${token}, ${tilePoints[token] ?? 0} points`}><Tile letter={token} isBlank={token === "?"} size="rack" hoverable={false} tilePoints={{ ...tilePoints, "?": 0 }} /></div>)}</div>}</section>;
  })}</div>;
}
