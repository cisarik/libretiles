import type { AdminDiagnosticPly } from "@/lib/types";

function measured(value: string | number | boolean | null): string {
  if (value === null) return "Not measured";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function ReplayEngineDetails({ diagnostic }: { diagnostic: AdminDiagnosticPly | null }) {
  if (!diagnostic) return <p className="text-sm text-stone-400">No diagnostic run linked to this move.</p>;
  const rows: Array<[string, string | number | boolean | null]> = [
    ["Model authored", diagnostic.model_authored], ["First validation valid", diagnostic.first_validate_valid],
    ["Valid candidate count", diagnostic.valid_candidate_count], ["Model legal score", diagnostic.model_legal_score],
    ["Ranked best score", diagnostic.ranked_best_score], ["Ranked search complete", diagnostic.ranked_search_complete],
    ["Playability status", diagnostic.playability_status], ["Assist mode", diagnostic.assist_mode],
    ["Score authority", diagnostic.score_authority], ["Runtime mode", diagnostic.executed_runtime_mode],
    ["Terminal cause", diagnostic.terminal_cause], ["Runner wall time (ms)", diagnostic.wall_clock_ms],
  ];
  return <dl className="grid gap-2 sm:grid-cols-2">{rows.map(([label, value]) => <div key={label} className="rounded-lg border border-stone-700/60 bg-black/25 p-3"><dt className="text-xs font-black uppercase tracking-[.12em] text-stone-500">{label}</dt><dd className="mt-1 font-bold text-stone-100">{measured(value)}</dd></div>)}</dl>;
}
