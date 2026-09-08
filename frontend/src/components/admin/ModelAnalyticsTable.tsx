"use client";

import { useState } from "react";

import { sortAnalyticsModels, type AnalyticsSortKey } from "@/lib/admin-analytics";
import type { AdminAnalyticsModel } from "@/lib/types";
import styles from "./admin.module.css";

const COLUMNS: Array<{ key: AnalyticsSortKey; label: string }> = [
  { key: "catalog", label: "Model & Provider" }, { key: "wins", label: "Games / Seats" },
  { key: "win_rate_pct", label: "Win Rate" }, { key: "avg_score", label: "Avg Score" },
  { key: "avg_spread", label: "Avg Spread" }, { key: "provider_candidate_pct", label: "Provider Authorship" },
  { key: "avg_attempt_latency_ms", label: "Latency" }, { key: "avg_provider_requests_per_turn", label: "Requests / turn" },
];

const measured = (value: number | null, suffix = "") => value == null ? "— Not measured" : `${value}${suffix}`;

export function ModelAnalyticsTable({ models }: { models: AdminAnalyticsModel[] }) {
  const [sort, setSort] = useState<AnalyticsSortKey>("catalog");
  const [direction, setDirection] = useState<"ascending" | "descending">("ascending");
  const choose = (key: AnalyticsSortKey) => { setDirection(key === sort && direction === "ascending" ? "descending" : "ascending"); setSort(key); };
  const rows = sortAnalyticsModels(models, sort, direction);
  return <section className={`${styles.panel} mt-5 p-5`}><div className="mb-4"><p className="text-xs font-black uppercase tracking-[.2em] text-amber-400">Comparison matrix</p><h2 className="mt-1 text-2xl font-black text-amber-50">Model Performance</h2></div><div className={styles.tableScroll} role="region" aria-label="Scrollable model analytics comparison" tabIndex={0}><table className={styles.analyticsTable}><thead><tr>{COLUMNS.map((column) => <th key={column.key} aria-sort={sort === column.key ? direction : "none"}><button type="button" onClick={() => choose(column.key)}>{column.label}</button></th>)}</tr></thead><tbody>{rows.map((model) => <tr key={model.key} data-featured={model.is_current_flagship ? "flagship" : model.model_id === "engine/cpu" ? "cpu" : undefined}><td><strong>{model.display_name}</strong><small>{model.provider} · {model.model_id}</small>{model.is_current_flagship ? <span className={styles.metricBadge}>Flagship</span> : null}{model.model_id === "engine/cpu" ? <span className={styles.cpuBadge}>CPU Master</span> : null}{!model.is_selectable && model.model_id !== "engine/cpu" ? <small>Not currently selectable</small> : null}</td><td>{model.games_played} / {model.seat_appearances}</td><td>{measured(model.win_rate_pct, "%")}<small>{model.wins} / {model.completed_seats} wins</small>{model.win_rate_pct != null ? <span className={styles.progress}><i style={{ width: `${model.win_rate_pct}%` }} /></span> : null}</td><td>{measured(model.avg_score)}</td><td>{measured(model.avg_spread)}</td><td>{model.provider === "engine" ? "N/A" : measured(model.provider_candidate_pct, "%")}</td><td>{measured(model.avg_attempt_latency_ms, " ms")}<small>{model.measured_attempts} attempts</small></td><td>{measured(model.avg_provider_requests_per_turn)}</td></tr>)}</tbody></table></div></section>;
}
