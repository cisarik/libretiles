"use client";

import { useDraggable } from "@dnd-kit/core";
import { motion, AnimatePresence } from "framer-motion";
import { Tile } from "./Tile";
import { useGameStore } from "@/hooks/useGameStore";

function DraggableTile({
  letter,
  index,
  isExchangeMode,
  isSelected,
  onSelect,
}: {
  letter: string;
  index: number;
  isExchangeMode: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `rack-${index}`,
    data: { letter, index, origin: "rack" },
    disabled: isExchangeMode,
  });

  return (
    <motion.div
      ref={setNodeRef}
      {...(isExchangeMode ? {} : { ...listeners, ...attributes })}
      layout
      initial={{ scale: 0, y: 20 }}
      animate={{ scale: 1, y: 0 }}
      exit={{ scale: 0, y: -20 }}
      transition={{ type: "spring", stiffness: 400, damping: 25, delay: index * 0.05 }}
      onClick={isExchangeMode ? onSelect : undefined}
      className={isDragging ? "opacity-0" : ""}
      style={{ touchAction: isExchangeMode ? "auto" : "none" }}
    >
      <Tile
        letter={letter}
        isSelected={isSelected}
        isDragging={isDragging}
        size="lg"
      />
    </motion.div>
  );
}

export function TileRack() {
  const gameState = useGameStore((s) => s.gameState);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const toggleExchangeSelection = useGameStore((s) => s.toggleExchangeSelection);
  const pendingTiles = useGameStore((s) => s.pendingTiles);

  const fullRack = gameState?.my_rack ?? [];
  const usedIndices = new Set(pendingTiles.map((t) => t.rackIndex));
  const visibleRack = fullRack
    .map((letter, i) => ({ letter, index: i }))
    .filter(({ index }) => !usedIndices.has(index));

  return (
    <div className="flex items-center justify-center gap-1.5 p-3 bg-stone-900/60 backdrop-blur-sm rounded-xl shadow-xl shadow-black/30">
      <AnimatePresence mode="popLayout">
        {visibleRack.map(({ letter, index }) => (
          <DraggableTile
            key={`${index}-${letter}`}
            letter={letter}
            index={index}
            isExchangeMode={exchangeMode}
            isSelected={exchangeSelected.has(index)}
            onSelect={() => toggleExchangeSelection(index)}
          />
        ))}
      </AnimatePresence>
      {visibleRack.length === 0 && (
        <span className="text-stone-500 text-sm italic">No tiles on rack</span>
      )}
    </div>
  );
}
