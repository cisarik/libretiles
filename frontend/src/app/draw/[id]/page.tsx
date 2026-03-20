"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useGameStore } from "@/hooks/useGameStore";

type Phase = "bag" | "flip" | "compare" | "result" | "redirect";
type Particle = { id: number; x: string; y: string };

function TileCard({
  letter,
  revealed,
  delay,
  isWinner,
  side,
}: {
  letter: string;
  revealed: boolean;
  delay: number;
  isWinner: boolean;
  side: "left" | "right";
}) {
  const display = letter === "?" ? "★" : letter;

  return (
    <div className="relative perspective-[600px]">
      <motion.div
        initial={{ y: -200, rotate: side === "left" ? -30 : 30, opacity: 0 }}
        animate={{ y: 0, rotate: 0, opacity: 1 }}
        transition={{
          type: "spring",
          stiffness: 200,
          damping: 15,
          delay,
        }}
        className="w-24 h-28 sm:w-28 sm:h-32"
      >
        <motion.div
          animate={{ rotateY: revealed ? 180 : 0 }}
          transition={{ duration: 0.6, delay: delay + 0.3 }}
          className="relative w-full h-full"
          style={{ transformStyle: "preserve-3d" }}
        >
          {/* Back face (tile back) */}
          <div
            className="absolute inset-0 rounded-xl bg-gradient-to-br from-amber-700 to-amber-900
              border-2 border-amber-600/50 shadow-xl flex items-center justify-center"
            style={{ backfaceVisibility: "hidden" }}
          >
            <div className="w-10 h-10 rounded-lg bg-amber-800/60 border border-amber-600/30" />
          </div>

          {/* Front face (letter) */}
          <div
            className={`absolute inset-0 rounded-xl border-2 shadow-xl flex items-center justify-center
              ${
                isWinner
                  ? "bg-gradient-to-br from-amber-100 to-amber-200 border-amber-400 shadow-amber-400/30"
                  : "bg-gradient-to-br from-stone-100 to-stone-200 border-stone-300"
              }`}
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <span
              className={`text-4xl sm:text-5xl font-black ${
                isWinner ? "text-amber-700" : "text-stone-700"
              }`}
            >
              {display}
            </span>
          </div>
        </motion.div>
      </motion.div>

      {/* Winner glow */}
      {isWinner && revealed && (
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: delay + 1.2 }}
          className="absolute -inset-3 rounded-2xl bg-amber-400/20 blur-xl -z-10"
        />
      )}
    </div>
  );
}

export default function DrawPage() {
  const params = useParams();
  const router = useRouter();
  const gameId = params.id as string;

  const startingDraw = useGameStore((s) => s.startingDraw);
  const selectedModelId = useGameStore((s) => s.selectedModelId);
  const [phase, setPhase] = useState<Phase>("bag");
  const [showResult, setShowResult] = useState(false);
  const [particles] = useState<Particle[]>(() =>
    Array.from({ length: 20 }, (_, id) => ({
      id,
      x: `${Math.random() * 100}vw`,
      y: `${Math.random() * 100}vh`,
    })),
  );

  const humanTile = startingDraw?.human_tile ?? "?";
  const aiTile = startingDraw?.ai_tile ?? "?";
  const humanFirst = startingDraw?.human_first ?? true;

  const humanVal = humanTile === "?" ? "" : humanTile;
  const aiVal = aiTile === "?" ? "" : aiTile;

  useEffect(() => {
    if (!startingDraw) {
      router.push(`/game/${gameId}`);
      return;
    }

    const timers = [
      window.setTimeout(() => setPhase("flip"), 800),
      window.setTimeout(() => setPhase("compare"), 2200),
      window.setTimeout(() => {
        setPhase("result");
        setShowResult(true);
      }, 3000),
      window.setTimeout(() => {
        setPhase("redirect");
        router.push(`/game/${gameId}`);
      }, 5000),
    ];

    return () => {
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
    };
  }, [startingDraw, gameId, router]);

  const revealed = phase !== "bag";

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 flex flex-col items-center justify-center p-4">
      {/* Title */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-10"
      >
        <h2 className="text-xl text-stone-400 font-medium">Starting Draw</h2>
        <p className="text-stone-500 text-sm mt-1">
          Closest to A goes first
        </p>
      </motion.div>

      {/* Tiles */}
      <div className="flex items-center gap-8 sm:gap-16">
        {/* Human tile */}
        <div className="flex flex-col items-center gap-3">
          <TileCard
            letter={humanTile}
            revealed={revealed}
            delay={0.2}
            isWinner={humanFirst}
            side="left"
          />
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5 }}
            className="text-stone-300 font-semibold text-sm"
          >
            You
          </motion.span>
        </div>

        {/* VS */}
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 300, delay: 0.4 }}
          className="text-stone-600 text-2xl font-bold"
        >
          vs
        </motion.div>

        {/* AI tile */}
        <div className="flex flex-col items-center gap-3">
          <TileCard
            letter={aiTile}
            revealed={revealed}
            delay={0.5}
            isWinner={!humanFirst}
            side="right"
          />
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.8 }}
            className="text-stone-300 font-semibold text-sm"
          >
            AI
          </motion.span>
        </div>
      </div>

      {/* Result announcement */}
      <AnimatePresence>
        {showResult && (
          <motion.div
            initial={{ opacity: 0, y: 30, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="mt-10 text-center"
          >
            <motion.div
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ repeat: Infinity, duration: 1.5 }}
              className={`text-2xl font-bold ${
                humanFirst ? "text-amber-300" : "text-sky-300"
              }`}
            >
              {humanFirst ? "You go first!" : "AI goes first!"}
            </motion.div>
            <div className="text-stone-500 text-sm mt-2">
              {humanTile === "?" ? "★ (blank)" : `"${humanTile}"`}
              {" vs "}
              {aiTile === "?" ? "★ (blank)" : `"${aiTile}"`}
              {" — "}
              {humanFirst
                ? `${humanVal || "blank"} is ${aiVal ? "closer to A" : "a blank (wins)"}`
                : `${aiVal || "blank"} is ${humanVal ? "closer to A" : "a blank (wins)"}`}
            </div>
            <div className="text-stone-600 text-xs mt-3 font-mono">
              {selectedModelId}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Particles background */}
      {showResult && (
        <div className="fixed inset-0 pointer-events-none overflow-hidden -z-10">
          {particles.map((particle, i) => (
            <motion.div
              key={particle.id}
              className={`absolute w-1.5 h-1.5 rounded-full ${
                humanFirst ? "bg-amber-400/40" : "bg-sky-400/40"
              }`}
              initial={{
                x: "50vw",
                y: "50vh",
                opacity: 0,
              }}
              animate={{
                x: particle.x,
                y: particle.y,
                opacity: [0, 0.6, 0],
                scale: [0, 1, 0],
              }}
              transition={{
                duration: 2,
                delay: i * 0.08,
                ease: "easeOut",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
