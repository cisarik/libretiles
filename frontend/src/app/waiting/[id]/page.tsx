"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";

import { useGameStore } from "@/hooks/useGameStore";
import { api } from "@/lib/api";
import { buildGameWebSocketUrl } from "@/lib/ws";
import type { GameState, WSTicketResponse } from "@/lib/types";

export default function WaitingPage() {
  const params = useParams();
  const router = useRouter();
  const gameId = params.id as string;

  const token = useGameStore((state) => state.token);
  const gameState = useGameStore((state) => state.gameState);
  const setGameState = useGameStore((state) => state.setGameState);

  const socketRef = useRef<WebSocket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    const authToken = token;
    if (!authToken) {
      router.replace("/");
      return;
    }
    const tokenValue: string = authToken;

    let active = true;

    async function connect() {
      try {
        const state = (await api.getGameState(tokenValue, gameId)) as GameState;
        if (!active) return;
        setGameState(state);
        if (state.status !== "waiting") {
          router.replace(`/game/${gameId}`);
          return;
        }

        const ticketResult = (await api.getWSTicket(tokenValue, gameId)) as WSTicketResponse;
        if (!active) return;

        const socket = new WebSocket(buildGameWebSocketUrl(gameId, ticketResult.ticket));
        socketRef.current = socket;

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as {
              type?: string;
              state?: GameState;
            };
            if (!data.state) return;
            setGameState(data.state);
            if (data.type === "match_found" || data.state.status !== "waiting") {
              router.replace(`/game/${gameId}`);
            }
          } catch {
            setError("Realtime connection dropped.");
          }
        };

        socket.onerror = () => {
          setError("Realtime connection failed.");
        };
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not enter the waiting room.");
      }
    }

    void connect();

    return () => {
      active = false;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [gameId, router, setGameState, token]);

  async function handleCancel() {
    if (!token || cancelling) return;
    setCancelling(true);
    try {
      await api.cancelHumanQueue(token, gameId);
      socketRef.current?.close();
      router.replace("/play");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not leave the queue.");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(145,176,214,0.14),transparent_26%),linear-gradient(180deg,#090d14,#040507)] text-stone-100">
      <div className="mx-auto flex min-h-screen max-w-[720px] flex-col items-center justify-center px-4 py-6 text-center">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="w-full rounded-[2rem] border border-white/10 bg-black/35 p-10 shadow-[0_24px_60px_rgba(0,0,0,0.36)] backdrop-blur-xl"
        >
          <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full border border-white/10 bg-white/[0.04]">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
              className="text-4xl"
            >
              ⌛
            </motion.div>
          </div>
          <div className="mt-8 text-[0.78rem] uppercase tracking-[0.34em] text-sky-300/72">
            Human Queue
          </div>
          <h1 className="mt-4 text-3xl font-black tracking-tight text-stone-50 sm:text-4xl">
            Waiting for an opponent
          </h1>
          <p className="mt-3 text-sm text-stone-400 sm:text-base">
            Your board is ready. The match starts as soon as another player joins.
          </p>
          {gameState && (
            <p className="mt-3 text-xs uppercase tracking-[0.26em] text-stone-500">
              Room {gameState.game_id.slice(0, 8)}
            </p>
          )}
          {error && (
            <p className="mt-5 text-sm text-rose-400">{error}</p>
          )}
          <button
            onClick={() => void handleCancel()}
            disabled={cancelling}
            className="mt-8 rounded-full border border-white/12 px-5 py-2.5 text-sm font-semibold text-stone-200 transition-colors hover:border-white/32 hover:text-stone-50 disabled:opacity-50"
          >
            {cancelling ? "Leaving queue..." : "Leave queue"}
          </button>
        </motion.div>
      </div>
    </div>
  );
}
