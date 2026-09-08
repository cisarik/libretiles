"use client";

import { useEffect, useState } from "react";

import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import type { AdminAnalyticsResponse, AdminAnalyticsSource, VariantSummary } from "@/lib/types";
import { DeploymentRecommendationCard } from "./DeploymentRecommendationCard";
import { ModelAnalyticsTable } from "./ModelAnalyticsTable";
import { PresetAnalyticsCards } from "./PresetAnalyticsCards";
import styles from "./admin.module.css";

export function AdminAnalyticsDashboard() {
  const token = useGameStore((state) => state.token);
  const [data, setData] = useState<AdminAnalyticsResponse | null>(null);
  const [variants, setVariants] = useState<VariantSummary[]>([]);
  const [days, setDays] = useState(30);
  const [source, setSource] = useState<AdminAnalyticsSource>("all");
  const [variant, setVariant] = useState("all");
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!token) return;
    let active = true;
    void Promise.all([api.admin.getAnalytics(token, { days, source, variant_slug: variant }), api.getVariants(token)]).then(([analytics, variantRows]) => { if (active) { setData(analytics); setVariants(variantRows.filter((row) => row.readiness === "playable")); setError(null); } }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Analytics could not be loaded."); });
    return () => { active = false; };
  }, [days, revision, source, token, variant]);
  const leader = data?.models.filter((row) => row.win_rate_pct != null).sort((a, b) => (b.win_rate_pct ?? -1) - (a.win_rate_pct ?? -1))[0];
  const scored = data?.models.filter((row) => row.avg_score != null) ?? [];
  const averageScore = scored.length ? Math.round(scored.reduce((sum, row) => sum + (row.avg_score ?? 0), 0) / scored.length * 10) / 10 : null;
  return <main className="mt-4 pb-12"><section className={`${styles.panel} ${styles.analyticsHero}`}><p className="text-xs font-black uppercase tracking-[.25em] text-amber-400">Evidence console · stored games only</p><h1 className="mt-3 text-4xl font-black text-amber-50 sm:text-6xl">Model Analytics</h1><p className="mt-4 max-w-3xl text-stone-300">Compare free rivals, prompt strategies, tool authorship, and measured turn economics without making a provider call.</p><div className={`${styles.filterBar} mt-6`}><label>Period<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>7d</option><option value={30}>30d</option><option value={90}>90d</option><option value={365}>All</option></select></label><label>Source<select value={source} onChange={(event) => setSource(event.target.value as AdminAnalyticsSource)}><option value="all">All</option><option value="gameplay">Gameplay</option><option value="playground">Playground</option><option value="diagnostic">Diagnostic</option></select></label><label>Variant<select value={variant} onChange={(event) => setVariant(event.target.value)}><option value="all">All variants</option>{variants.map((row) => <option value={row.slug} key={row.slug}>{row.display_name}</option>)}</select></label><button className={styles.button} type="button" onClick={() => setRevision((value) => value + 1)}>Refresh</button></div></section>{error ? <section className={`${styles.panel} mt-5 p-6 text-rose-200`} role="alert"><h2 className="font-black">Analytics unavailable</h2><p>{error}</p><button className={`${styles.button} mt-3`} onClick={() => setRevision((value) => value + 1)}>Retry</button></section> : null}{data ? <><section className={`${styles.metricGrid} mt-5`}>{[["Total Games Played", data.summary.total_games], ["Total Plies Replayed", data.summary.total_plies], ["Top Win-Rate Model", leader?.display_name ?? "Not measured"], ["Average Score", averageScore ?? "Not measured"]].map(([label, value]) => <article className={`${styles.panel} p-5`} key={label}><span className="text-xs font-black uppercase tracking-[.14em] text-stone-400">{label}</span><strong className="mt-3 block text-3xl text-amber-100">{value}</strong></article>)}</section><ModelAnalyticsTable models={data.models} /><PresetAnalyticsCards presets={data.presets} /><DeploymentRecommendationCard recommendations={data.recommendations} /><details className={`${styles.panel} mt-5 p-5`}><summary className="cursor-pointer font-black text-amber-100">Coverage & limitations</summary><p className="mt-3 text-sm text-stone-300">Unknown runtime moves: {data.coverage.unknown_runtime_moves} · unknown completion source: {data.coverage.unknown_completion_source_moves}</p><ul className="mt-2 text-sm text-stone-400">{data.coverage.limitations.map((item) => <li key={item}>{item.replaceAll("_", " ")}</li>)}</ul></details></> : !error ? <p className={`${styles.panel} mt-5 p-6 text-stone-300`} aria-busy="true">Loading analytics...</p> : null}</main>;
}
