"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { consumeAIStream } from "@/lib/ai-move-stream";
import { api } from "@/lib/api";
import {
  parseSimulationState,
  type SimulationConfig,
  type SimulationState,
} from "@/lib/admin-simulation";

export type SimulationRunnerPhase =
  | "configuring"
  | "starting"
  | "running"
  | "paused"
  | "finished"
  | "stopped"
  | "error";

export type SimulationSpeed = 0.5 | 1 | 2;

const SPEED_DELAY_MS: Record<SimulationSpeed, number> = {
  0.5: 2000,
  1: 1000,
  2: 500,
};

export function useSimulationRunner(token: string | null) {
  const [phase, setPhase] = useState<SimulationRunnerPhase>("configuring");
  const [state, setState] = useState<SimulationState | null>(null);
  const [speed, setSpeed] = useState<SimulationSpeed>(1);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const clearPending = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const applyState = useCallback((next: SimulationState) => {
    setState(next);
    if (next.game_over) {
      setPhase(next.game_end_reason === "simulation_stopped" ? "stopped" : "finished");
    }
  }, []);

  const runTurn = useCallback(
    async (current: SimulationState): Promise<SimulationState> => {
      if (!token) throw new Error("Admin authentication is required.");
      const controller = new AbortController();
      abortRef.current = controller;
      const response = await fetch(
        `/api/admin/simulate/${encodeURIComponent(current.game_id)}/turn`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ expected_move_count: current.move_count }),
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "The simulation turn could not start.");
      }
      const terminal = await consumeAIStream(response, {
        onCandidate: () => {},
        onStatus: setStatus,
      });
      abortRef.current = null;
      if (terminal.kind !== "done") {
        throw new Error(
          terminal.kind === "no_terminal"
            ? "The simulation turn ended without a result."
            : terminal.message,
        );
      }
      const embedded = terminal.data.state;
      const next = embedded
        ? parseSimulationState(embedded)
        : await api.admin.getSimulation(token, current.game_id);
      activeRef.current = false;
      applyState(next);
      return next;
    },
    [applyState, token],
  );

  useEffect(() => {
    if (phase !== "running" || !state || state.game_over || activeRef.current) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      activeRef.current = true;
      void runTurn(state)
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") return;
          setError(reason instanceof Error ? reason.message : "Simulation failed.");
          setPhase("error");
        })
        .finally(() => {
          activeRef.current = false;
        });
    }, SPEED_DELAY_MS[speed]);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, [phase, runTurn, speed, state]);

  useEffect(() => clearPending, [clearPending]);

  const start = useCallback(
    async (config: SimulationConfig) => {
      if (!token) throw new Error("Admin authentication is required.");
      clearPending();
      setError(null);
      setStatus("Preparing the seeded match...");
      setPhase("starting");
      try {
        const created = await api.admin.createSimulation(token, config);
        setState(created);
        setPhase("running");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Could not start simulation.");
        setPhase("error");
      }
    },
    [clearPending, token],
  );

  const restore = useCallback(
    async (gameId: string) => {
      if (!token) return;
      try {
        const restored = await api.admin.getSimulation(token, gameId);
        setState(restored);
        setPhase(
          restored.game_over
            ? restored.game_end_reason === "simulation_stopped"
              ? "stopped"
              : "finished"
            : "paused",
        );
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Could not restore simulation.");
        setPhase("error");
      }
    },
    [token],
  );

  const pause = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setPhase("paused");
  }, []);

  const resume = useCallback(() => {
    setError(null);
    setPhase("running");
  }, []);

  const step = useCallback(async () => {
    if (!state || activeRef.current || state.game_over) return;
    setPhase("paused");
    activeRef.current = true;
    try {
      await runTurn(state);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Simulation failed.");
      setPhase("error");
    } finally {
      activeRef.current = false;
    }
  }, [runTurn, state]);

  const stop = useCallback(async () => {
    if (!token || !state) return;
    clearPending();
    try {
      const stopped = await api.admin.stopSimulation(token, state.game_id);
      applyState(stopped);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not stop simulation.");
      setPhase("error");
    }
  }, [applyState, clearPending, state, token]);

  return {
    phase,
    state,
    speed,
    status,
    error,
    start,
    restore,
    pause,
    resume,
    step,
    stop,
    setSpeed,
  };
}
