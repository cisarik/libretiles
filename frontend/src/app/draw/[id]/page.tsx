"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Board } from "@/components/board/Board";
import { Tile } from "@/components/tiles/Tile";
import { useGameStore } from "@/hooks/useGameStore";

type DrawStage = "board" | "flip" | "compare" | "result" | "rack";

function StartTile({
  letter,
  revealed,
  isWinner,
  label,
  side,
}: {
  letter: string;
  revealed: boolean;
  isWinner: boolean;
  label: string;
  side: "left" | "right";
}) {
  const displayLetter = letter === "?" ? "★" : letter;

  return (
    <div className="flex flex-col items-center gap-3">
      <motion.div
        initial={{ opacity: 0, y: 36, rotate: side === "left" ? -8 : 8, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, rotate: 0, scale: 1 }}
        transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        className="relative h-28 w-24 sm:h-32 sm:w-28"
        style={{ perspective: "1000px" }}
      >
        <motion.div
          animate={{ rotateY: revealed ? 180 : 0, y: isWinner && revealed ? [-1, -7, -4] : 0 }}
          transition={{
            rotateY: { duration: 0.68, ease: [0.22, 1, 0.36, 1] },
            y: { duration: 0.62, delay: 0.26, ease: [0.22, 1, 0.36, 1] },
          }}
          className="relative h-full w-full"
          style={{ transformStyle: "preserve-3d" }}
        >
          <div
            className="absolute inset-0 rounded-[1.25rem] border border-amber-500/24 bg-gradient-to-br from-stone-800 via-stone-900 to-black shadow-[0_24px_44px_rgba(0,0,0,0.46)]"
            style={{ backfaceVisibility: "hidden" }}
          >
            <div className="absolute inset-2 rounded-[1rem] border border-white/5 bg-white/[0.03]" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-10 w-10 rounded-2xl border border-amber-200/10 bg-amber-100/6" />
            </div>
          </div>

          <div
            className={`absolute inset-0 rounded-[1.25rem] border shadow-[0_24px_44px_rgba(0,0,0,0.42)]
              ${isWinner
                ? "border-amber-300/60 bg-gradient-to-br from-amber-50 via-[#fff3ce] to-amber-200"
                : "border-stone-200/65 bg-gradient-to-br from-stone-100 via-[#f5efe1] to-stone-200"}`}
            style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          >
            <div className="absolute inset-[7px] rounded-[1rem] border border-black/5" />
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`text-[3rem] font-black leading-none ${isWinner ? "text-amber-800" : "text-stone-700"}`}>
                {displayLetter}
              </span>
            </div>
          </div>
        </motion.div>

        {isWinner && revealed && (
          <motion.div
            initial={{ opacity: 0, scale: 0.7 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, delay: 0.25 }}
            className="absolute -inset-4 -z-10 rounded-[1.6rem] bg-amber-400/20 blur-2xl"
          />
        )}
      </motion.div>

      <span className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-400">
        {label}
      </span>
    </div>
  );
}

function describeResult(humanTile: string, aiTile: string, humanFirst: boolean) {
  if (humanTile === "?" || aiTile === "?") {
    return humanFirst ? "Blank wins the draw." : "AI drew the blank.";
  }

  return humanFirst
    ? `${humanTile} is closer to A than ${aiTile}.`
    : `${aiTile} is closer to A than ${humanTile}.`;
}

export default function DrawPage() {
  const params = useParams();
  const router = useRouter();
  const gameId = params.id as string;

  const startingDraw = useGameStore((s) => s.startingDraw);
  const setStartingDraw = useGameStore((s) => s.setStartingDraw);
  const startingRack = useGameStore((s) => s.startingRack);
  const selectedModelId = useGameStore((s) => s.selectedModelId);

  const [stage, setStage] = useState<DrawStage>("board");

  const humanTile = startingDraw?.human_tile ?? "?";
  const aiTile = startingDraw?.ai_tile ?? "?";
  const humanFirst = startingDraw?.human_first ?? true;
  const revealed = stage !== "board";

  const rackSlots = useMemo(
    () => Array.from({ length: 7 }, (_, index) => startingRack?.[index] ?? ""),
    [startingRack],
  );

  useEffect(() => {
    if (!startingDraw) {
      router.replace(`/game/${gameId}`);
      return;
    }

    const timers = [
      window.setTimeout(() => setStage("flip"), 820),
      window.setTimeout(() => setStage("compare"), 1900),
      window.setTimeout(() => setStage("result"), 3000),
      window.setTimeout(() => setStage("rack"), 3720),
      window.setTimeout(() => {
        setStartingDraw(null);
        router.replace(`/game/${gameId}`);
      }, 5600),
    ];

    return () => {
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
    };
  }, [gameId, router, setStartingDraw, startingDraw]);

  return (
    <div className="min-h-screen overflow-hidden bg-[#040404] text-stone-100">
      <motion.div
        initial={{ opacity: 1 }}
        animate={{ opacity: 0 }}
        transition={{ duration: 0.68, ease: [0.22, 1, 0.36, 1] }}
        className="pointer-events-none fixed inset-0 z-[80] bg-black"
      />

      <div className="mx-auto flex min-h-screen max-w-[1080px] flex-col items-center justify-center gap-5 px-4 py-5 sm:gap-6 sm:px-5">
        <motion.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.18 }}
          className="text-center"
        >
          <div className="text-[0.7rem] uppercase tracking-[0.34em] text-stone-500">
            Starting Draw
          </div>
          <h1 className="mt-2 text-2xl font-black tracking-tight text-stone-50 sm:text-3xl">
            Deciding who opens the board
          </h1>
          <p className="mt-2 text-sm text-stone-400">
            Closest tile to A starts. Fresh rack already loaded.
          </p>
          <div className="mt-3 inline-flex items-center rounded-full border border-white/8 bg-white/[0.03] px-4 py-1.5 font-mono text-[0.72rem] text-stone-400">
            {selectedModelId}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.985, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-[940px]"
        >
          <div className="relative">
            <Board dragPreview={null} isDraggingTile={false} />

            <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-4">
              <div className="flex w-full max-w-[680px] flex-col items-center gap-6 sm:gap-8">
                <div className="flex items-center gap-6 sm:gap-12">
                  <StartTile
                    letter={humanTile}
                    revealed={revealed}
                    isWinner={humanFirst}
                    label="You"
                    side="left"
                  />

                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.35, delay: 0.45 }}
                    className="rounded-full border border-white/8 bg-black/24 px-4 py-2 text-sm font-black uppercase tracking-[0.3em] text-stone-500 sm:px-5"
                  >
                    VS
                  </motion.div>

                  <StartTile
                    letter={aiTile}
                    revealed={revealed}
                    isWinner={!humanFirst}
                    label="AI"
                    side="right"
                  />
                </div>

                <AnimatePresence mode="wait">
                  {stage === "result" || stage === "rack" ? (
                    <motion.div
                      key="result"
                      initial={{ opacity: 0, y: 18, scale: 0.94 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -10 }}
                      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
                      className="rounded-[1.4rem] border border-white/10 bg-black/36 px-6 py-4 text-center shadow-[0_26px_50px_rgba(0,0,0,0.34)] backdrop-blur-md"
                    >
                      <div className={`text-lg font-black sm:text-xl ${humanFirst ? "text-amber-300" : "text-sky-300"}`}>
                        {humanFirst ? "You start this game" : "AI opens this game"}
                      </div>
                      <p className="mt-2 text-sm text-stone-300">
                        {describeResult(humanTile, aiTile, humanFirst)}
                      </p>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="pre-result"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-center text-sm text-stone-500"
                    >
                      Tiles drawn from the bag...
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: stage === "rack" ? 1 : 0.48, y: stage === "rack" ? 0 : 18 }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-[940px] rounded-[1.9rem] border border-white/8 bg-stone-950/56 px-5 py-4 shadow-[0_22px_54px_rgba(0,0,0,0.28)] backdrop-blur-sm"
        >
          <div className="mb-3 text-center text-[0.7rem] font-semibold uppercase tracking-[0.34em] text-stone-500">
            Opening Rack
          </div>
          <div className="flex justify-center gap-2 sm:gap-2.5">
            {rackSlots.map((letter, index) => (
              <motion.div
                key={`${letter || "slot"}-${index}`}
                initial={{ opacity: 0, y: 16, scale: 0.94 }}
                animate={{
                  opacity: stage === "rack" ? 1 : 0.8,
                  y: stage === "rack" ? 0 : 12,
                  scale: 1,
                }}
                transition={{
                  duration: 0.24,
                  delay: stage === "rack" ? index * 0.045 : 0,
                  ease: [0.22, 1, 0.36, 1],
                }}
              >
                <Tile
                  letter={letter}
                  isBlank={letter === "?"}
                  size="lg"
                  hoverable={false}
                />
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
