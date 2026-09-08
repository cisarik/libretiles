import type { AdminAnalyticsResponse } from "@/lib/types";
import styles from "./admin.module.css";

export function DeploymentRecommendationCard({ recommendations }: { recommendations: AdminAnalyticsResponse["recommendations"] }) {
  const rows = [
    ["Primary Flagship", recommendations.primary_flagship],
    ["High-Throughput Rival", recommendations.high_throughput_rival],
    ["Zero-Cost Offline Fallback", recommendations.offline_cpu],
    ["Strategic Preset", recommendations.strategic_preset],
  ] as const;
  return <section className={`${styles.recommendation} mt-5`}><p className="text-xs font-black uppercase tracking-[.22em] text-stone-950">VPS deployment recommendation</p><h2 className="mt-2 text-3xl font-black text-stone-950">Interview-ready operating stack</h2><div className={`${styles.recommendationGrid} mt-5`}>{rows.map(([label, row]) => <article key={label}><span>{label}</span><strong>{row.display_name ?? row.prompt_name ?? "Insufficient evidence"}</strong><small>{row.model_id ?? row.reason_codes.join(" · ")}</small></article>)}</div><div className="mt-5 border-t border-black/20 pt-4 text-sm font-semibold text-stone-800">{recommendations.reliability_notes.map((note) => <p key={note}>{note}</p>)}</div></section>;
}
