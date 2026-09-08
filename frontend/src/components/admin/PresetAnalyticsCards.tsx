import type { AdminAnalyticsPreset } from "@/lib/types";
import styles from "./admin.module.css";

export function PresetAnalyticsCards({ presets }: { presets: AdminAnalyticsPreset[] }) {
  return <section className="mt-5"><p className="text-xs font-black uppercase tracking-[.2em] text-amber-400">Prompt strategy</p><h2 className="mt-1 text-2xl font-black text-amber-50">Preset Comparison</h2><div className={`${styles.metricGrid} mt-4`}>{presets.map((preset) => <article className={`${styles.panel} p-5`} key={`${preset.prompt_id}-${preset.name}`}><h3 className="text-xl font-black text-stone-100">{preset.name}</h3><strong className="mt-4 block text-3xl text-amber-200">{preset.win_rate_pct == null ? "—" : `${preset.win_rate_pct}%`}</strong><p className="text-sm text-stone-400">{preset.wins} wins · {preset.completed_seats} completed seats</p><p className="mt-3 text-sm text-stone-300">Average score: {preset.avg_score ?? "Not measured"}</p><p className="mt-2 text-xs text-stone-500">Historical preset identity; prompt content version is not verified.</p></article>)}</div></section>;
}
