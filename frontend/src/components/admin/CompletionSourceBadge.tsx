import { asAiCompletionSource } from "@/lib/types";

const BADGES = {
  provider_candidate: ["Provider candidate", "border-emerald-400/40 bg-emerald-950/60 text-emerald-200"],
  backend_ranked_candidate: ["Backend ranked candidate", "border-amber-400/40 bg-amber-950/60 text-amber-200"],
  repair_candidate: ["Repair candidate", "border-indigo-400/40 bg-indigo-950/60 text-indigo-200"],
  backend_witness_rescue: ["Backend legal rescue", "border-blue-400/40 bg-blue-950/60 text-blue-200"],
  genuine_no_move_exchange: ["No legal move: exchange", "border-stone-400/40 bg-stone-800 text-stone-200"],
  genuine_no_move_pass: ["No legal move: pass", "border-stone-400/40 bg-stone-800 text-stone-200"],
} as const;

export function CompletionSourceBadge({ source }: { source: unknown }) {
  const parsed = asAiCompletionSource(source);
  const [label, className] = parsed
    ? BADGES[parsed]
    : ["Unknown source", "border-stone-500/40 bg-stone-900 text-stone-300"];
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-black ${className}`}>{label}</span>;
}
