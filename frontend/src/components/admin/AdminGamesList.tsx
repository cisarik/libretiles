"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import type { AdminGameListParams, AdminGameListResponse, VariantSummary } from "@/lib/types";
import styles from "./admin.module.css";

const validMode = (value: string | null): AdminGameListParams["game_mode"] => value === "vs_ai" || value === "vs_human" ? value : "all";
const validStatus = (value: string | null): AdminGameListParams["status"] => value === "waiting" || value === "active" || value === "finished" || value === "abandoned" ? value : "all";

export function AdminGamesList() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = useGameStore((state) => state.token);
  const mode = validMode(searchParams.get("game_mode"));
  const status = validStatus(searchParams.get("status"));
  const variant = searchParams.get("variant_slug") ?? "";
  const search = (searchParams.get("search") ?? "").slice(0, 150);
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const [draftSearch, setDraftSearch] = useState(search);
  const [data, setData] = useState<AdminGameListResponse | null>(null);
  const [variants, setVariants] = useState<VariantSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  const navigate = (changes: Record<string, string | number>) => {
    const next = new URLSearchParams(searchParams.toString());
    Object.entries(changes).forEach(([key, value]) => value === "" || value === "all" || (key === "page" && value === 1) ? next.delete(key) : next.set(key, String(value)));
    router.replace(`/admin${next.size ? `?${next.toString()}` : ""}`);
  };
  useEffect(() => { setDraftSearch(search); }, [search]);
  useEffect(() => {
    if (!token) return;
    let active = true;
    void api.getVariants(token).then((items) => { if (active) setVariants(items); }).catch(() => undefined);
    return () => { active = false; };
  }, [token]);
  useEffect(() => {
    if (!token) return;
    let active = true; setLoading(true); setError("");
    void api.admin.listGames(token, { page, page_size: 20, game_mode: mode, status, variant_slug: variant, search }).then((result) => {
      if (!active) return; setData(result);
      if (result.page !== page) {
        const next = new URLSearchParams(searchParams.toString());
        if (result.page === 1) next.delete("page"); else next.set("page", String(result.page));
        router.replace(`/admin${next.size ? `?${next.toString()}` : ""}`);
      }
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Games could not be loaded."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [mode, page, retry, router, search, searchParams, status, token, variant]);
  const submitSearch = (event: FormEvent) => { event.preventDefault(); navigate({ search: draftSearch.trim().slice(0, 150), page: 1 }); };

  return <main className="mt-5"><header><div className="text-xs font-black uppercase tracking-[.3em] text-amber-400">Staff operations</div><h1 className="mt-2 text-4xl font-black text-amber-100">Games List</h1></header><form onSubmit={submitSearch} className={`${styles.panel} mt-5 grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_2fr_auto]`}><label className="text-sm text-stone-400">Mode<select className="mt-1 w-full rounded-lg border border-stone-700 bg-black/40 p-2 text-stone-100" value={mode} onChange={(event) => navigate({ game_mode: event.target.value, page: 1 })}><option value="all">All modes</option><option value="vs_ai">vs AI</option><option value="vs_human">vs Human</option></select></label><label className="text-sm text-stone-400">Variant<select className="mt-1 w-full rounded-lg border border-stone-700 bg-black/40 p-2 text-stone-100" value={variant} onChange={(event) => navigate({ variant_slug: event.target.value, page: 1 })}><option value="">All variants</option>{variants.map((item) => <option key={item.slug} value={item.slug}>{item.display_name}</option>)}{variant && !variants.some((item) => item.slug === variant) ? <option value={variant}>{variant}</option> : null}</select></label><label className="text-sm text-stone-400">Status<select className="mt-1 w-full rounded-lg border border-stone-700 bg-black/40 p-2 text-stone-100" value={status} onChange={(event) => navigate({ status: event.target.value, page: 1 })}><option value="all">All statuses</option><option value="active">Active</option><option value="waiting">Waiting</option><option value="finished">Finished</option><option value="abandoned">Abandoned</option></select></label><label className="text-sm text-stone-400">Game ID or username<input maxLength={150} className="mt-1 w-full rounded-lg border border-stone-700 bg-black/40 p-2 text-stone-100" value={draftSearch} onChange={(event) => setDraftSearch(event.target.value)} /></label><button className={`${styles.button} self-end`} type="submit">Search</button></form>{loading ? <State text="Loading recent games..." /> : error ? <State text={error} action={<button className={styles.button} onClick={() => setRetry((value) => value + 1)}>Retry</button>} /> : !data?.results.length ? <State text="No games match these filters." /> : <div className="mt-4 grid gap-3">{data.results.map((game) => <article key={game.game_id} className={`${styles.panel} grid gap-4 p-4 lg:grid-cols-[1.2fr_1fr_1fr_1.5fr_auto] lg:items-center`}><div><div className="font-mono text-sm font-black text-amber-200">{game.game_id.replaceAll("-", "").slice(0, 12)}</div><div className="mt-1 text-xs text-stone-500">{new Date(game.created_at).toLocaleString()}</div></div><div><div className="font-bold">{game.game_mode === "vs_ai" ? "vs AI" : "vs Human"}</div><div className="text-sm text-stone-400">{game.variant_slug}</div></div><div><span className="rounded-full border border-amber-300/20 px-2 py-1 text-xs font-black uppercase text-amber-200">{game.status}</span><div className="mt-2 text-xs text-stone-500">{game.move_count} moves</div></div><div>{game.slots.map((slot) => <div key={slot.slot} className="text-sm"><span className="text-stone-500">P{slot.slot}</span> {slot.username || slot.model_display_name || slot.model_id || "Open seat"} <strong className="text-amber-100">{slot.score}</strong></div>)}{game.is_diagnostic ? <div className="mt-2 text-xs font-black uppercase text-sky-300">Diagnostic · {game.diagnostic_run_count} runs</div> : null}</div><Link className={styles.button} href={`/admin/replay/${game.game_id}`}>View Replay</Link></article>)}</div>}<div className="mt-4 flex items-center justify-end gap-3"><button className={styles.button} disabled={!data || data.page <= 1} onClick={() => navigate({ page: page - 1 })}>Previous</button><span className="text-sm text-stone-300">Page {data?.page ?? page} of {data?.total_pages ?? "?"}</span><button className={styles.button} disabled={!data || data.page >= data.total_pages} onClick={() => navigate({ page: page + 1 })}>Next</button></div></main>;
}

function State({ text, action }: { text: string; action?: React.ReactNode }) { return <div className={`${styles.panel} mt-4 p-8 text-center text-stone-300`}><p>{text}</p>{action ? <div className="mt-4">{action}</div> : null}</div>; }
