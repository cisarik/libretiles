"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useGameStore } from "@/hooks/useGameStore";
import styles from "./admin.module.css";

type GateState = "checking" | "staff" | "denied" | "error";

export function AdminAccessGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const token = useGameStore((state) => state.token);
  const [state, setState] = useState<GateState>("checking");
  const [verifiedIdentity, setVerifiedIdentity] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (pathname === "/admin/login") return;
    let active = true;
    const verify = async () => {
      await Promise.resolve();
      if (!active) return;
      setState("checking");
      if (!useGameStore.persist.hasHydrated()) {
        await Promise.race([
          new Promise<void>((resolve) => useGameStore.persist.onFinishHydration(() => resolve())),
          new Promise<void>((resolve) => setTimeout(resolve, 300)),
        ]);
      }
      const currentToken = useGameStore.getState().token;
      if (!active) return;
      if (!currentToken) {
        router.replace(`/admin/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      try {
        const profile = await api.me(currentToken);
        if (active) {
          setVerifiedIdentity(`${currentToken}:${pathname}`);
          setState(profile.is_staff === true ? "staff" : "denied");
        }
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) router.replace(`/admin/login?next=${encodeURIComponent(pathname)}`);
        else if (error instanceof ApiError && error.status === 403) setState("denied");
        else setState("error");
      }
    };
    void verify();
    return () => { active = false; };
  }, [attempt, pathname, router, token]);

  if (pathname === "/admin/login") return children;
  if (state === "staff" && verifiedIdentity === `${token}:${pathname}`) return children;
  if (state === "denied") return <GateMessage title="403 - Staff access required" body="This console is restricted to staff accounts." />;
  if (state === "error") return <GateMessage title="Admin verification failed" body="The server could not verify this session." retry={() => setAttempt((value) => value + 1)} />;
  return <main className={styles.shell} aria-busy="true"><div className={`${styles.panel} p-8 text-stone-300`}>Verifying staff access...</div></main>;
}

function GateMessage({ title, body, retry }: { title: string; body: string; retry?: () => void }) {
  return <main className={`${styles.shell} flex min-h-[75vh] items-center justify-center`}><section className={`${styles.panel} max-w-lg p-8 text-center`}><h1 className="text-2xl font-black text-amber-200">{title}</h1><p className="mt-3 text-stone-300">{body}</p><div className="mt-6 flex justify-center gap-3">{retry ? <button className={styles.button} onClick={retry}>Retry</button> : null}<Link className={styles.button} href="/play">Back to Game</Link></div></section></main>;
}
