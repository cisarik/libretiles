"use client";

import { useEffect } from "react";

import { useGameStore } from "@/hooks/useGameStore";
import { useSimulationRunner } from "@/hooks/useSimulationRunner";
import { SimulationArena } from "./SimulationArena";
import { SimulationSetupForm } from "./SimulationSetupForm";
import styles from "./admin.module.css";

export function SimulationPlayground() {
  const token = useGameStore((state) => state.token);
  const runner = useSimulationRunner(token);
  const restore = runner.restore;

  useEffect(() => {
    const gameId = new URLSearchParams(window.location.search).get("game");
    if (gameId) void restore(gameId);
  }, [restore]);

  return (
    <main className="mt-4 pb-12">
      <section className={`${styles.panel} ${styles.playgroundHero}`}>
        <p className="text-xs font-black uppercase tracking-[.25em] text-amber-400">Admin laboratory · deterministic match runner</p>
        <h1 className="mt-3 max-w-4xl text-4xl font-black tracking-tight text-amber-50 sm:text-6xl">Simulation Playground</h1>
        <p className="mt-4 max-w-3xl text-stone-300">Launch CPU Master and free-rival matches, inspect every committed board transition, pause on any position, and hand the finished game directly to Replay Studio.</p>
      </section>
      {!runner.state ? (
        token ? <SimulationSetupForm token={token} disabled={runner.phase === "starting"} onStart={runner.start} /> : <p className={`${styles.panel} mt-4 p-5 text-red-200`}>Admin authentication is required.</p>
      ) : (
        <SimulationArena state={runner.state} phase={runner.phase} speed={runner.speed} status={runner.status} onPause={runner.pause} onResume={runner.resume} onStep={runner.step} onStop={runner.stop} onSpeed={runner.setSpeed} />
      )}
      {runner.error ? <p className="mt-4 rounded-xl border border-red-400/30 bg-red-950/50 p-4 text-red-100" role="alert">{runner.error}</p> : null}
    </main>
  );
}
