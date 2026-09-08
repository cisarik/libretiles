"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { safeAdminCallback } from "@/lib/admin-access";
import { useGameStore } from "@/hooks/useGameStore";
import styles from "@/components/admin/admin.module.css";

function AdminLoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const setToken = useGameStore((state) => state.setToken);
  const setRefreshToken = useGameStore((state) => state.setRefreshToken);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const tokens = await api.login({ username, password });
      const profile = await api.me(tokens.access);
      if (profile.is_staff !== true) { setError("This account does not have staff access."); return; }
      setToken(tokens.access); setRefreshToken(tokens.refresh);
      router.replace(safeAdminCallback(params.get("next")));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Sign-in failed."); }
    finally { setLoading(false); }
  };
  return <main className="flex min-h-screen items-center justify-center p-4"><form onSubmit={submit} className={`${styles.panel} w-full max-w-md p-7`}><div className="text-xs font-black uppercase tracking-[.3em] text-amber-400">Libre Tiles Operations</div><h1 className="mt-3 text-3xl font-black text-amber-100">Admin sign in</h1><label className="mt-6 block text-sm text-stone-300">Username<input className="mt-2 w-full rounded-xl border border-stone-700 bg-black/40 px-4 py-3" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label><label className="mt-4 block text-sm text-stone-300">Password<input type="password" className="mt-2 w-full rounded-xl border border-stone-700 bg-black/40 px-4 py-3" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>{error ? <p role="alert" className="mt-4 text-rose-300">{error}</p> : null}<button className={`${styles.button} mt-6 w-full`} disabled={loading}>{loading ? "Verifying..." : "Enter admin console"}</button></form></main>;
}

export default function AdminLoginPage() { return <Suspense fallback={<div className="p-8">Loading sign in...</div>}><AdminLoginForm /></Suspense>; }
