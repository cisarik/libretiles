"use client";

import { useMemo, useRef } from "react";
import { useDraggable } from "@dnd-kit/core";
import { motion, AnimatePresence } from "framer-motion";
import { Tile } from "./Tile";
import { useGameStore } from "@/hooks/useGameStore";
import { isPlausibleRack } from "@/lib/rack";

const MOBILE_TAP_MOVE_TOLERANCE = 10;

function DraggableTile({
  letter,
  index,
  isExchangeMode,
  dragEnabled,
  interactionDisabled,
  isSelected,
  tileSize,
  onSelect,
}: {
  letter: string;
  index: number;
  isExchangeMode: boolean;
  dragEnabled: boolean;
  interactionDisabled: boolean;
  isSelected: boolean;
  tileSize: "sm" | "md" | "lg" | "rack";
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `rack-${index}`,
    data: { letter, index, origin: "rack" },
    disabled: isExchangeMode || interactionDisabled || !dragEnabled,
  });
  const touchGestureRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const selectEnabled = isExchangeMode || !interactionDisabled;

  return (
    <motion.div
      ref={setNodeRef}
      {...(isExchangeMode || interactionDisabled || !dragEnabled ? {} : { ...listeners, ...attributes })}
      layout="position"
      initial={{ scale: 0, y: 20 }}
      animate={{ scale: 1, y: 0 }}
      exit={{ scale: 0, y: -20 }}
      transition={{
        layout: { duration: 0.16, ease: [0.22, 1, 0.36, 1] },
        duration: 0.18,
        ease: [0.22, 1, 0.36, 1],
        delay: index * 0.03,
      }}
      onClick={isExchangeMode ? onSelect : undefined}
      onTouchStart={!dragEnabled && selectEnabled ? (event) => {
        const touch = event.touches[0];
        if (!touch) return;
        touchGestureRef.current = { x: touch.clientX, y: touch.clientY, moved: false };
      } : undefined}
      onTouchMove={!dragEnabled && selectEnabled ? (event) => {
        const gesture = touchGestureRef.current;
        const touch = event.touches[0];
        if (!gesture || !touch) return;
        if (Math.hypot(touch.clientX - gesture.x, touch.clientY - gesture.y) > MOBILE_TAP_MOVE_TOLERANCE) {
          gesture.moved = true;
        }
      } : undefined}
      onTouchEnd={!dragEnabled && selectEnabled ? (event) => {
        const gesture = touchGestureRef.current;
        touchGestureRef.current = null;
        const touch = event.changedTouches[0];
        if (!gesture || !touch) return;
        const traveled = Math.hypot(touch.clientX - gesture.x, touch.clientY - gesture.y);
        if (gesture.moved || traveled > MOBILE_TAP_MOVE_TOLERANCE) return;
        event.preventDefault();
        onSelect();
      } : undefined}
      onTouchCancel={!dragEnabled ? () => {
        touchGestureRef.current = null;
      } : undefined}
      className={`will-change-transform ${isDragging ? "opacity-0" : ""}`}
      style={{ touchAction: dragEnabled ? "none" : "manipulation" }}
    >
      <Tile
        letter={letter}
        isSelected={isSelected}
        isDragging={isDragging}
        size={tileSize}
        hoverable={false}
      />
    </motion.div>
  );
}

function TapSelectableTile({
  letter,
  index,
  isSelected,
  tileSize,
  onSelect,
}: {
  letter: string;
  index: number;
  isSelected: boolean;
  tileSize: "sm" | "md" | "lg" | "rack";
  onSelect: () => void;
}) {
  const suppressClickRef = useRef(false);

  return (
    <motion.button
      type="button"
      layout="position"
      initial={{ scale: 0, y: 20 }}
      animate={{ scale: 1, y: 0 }}
      exit={{ scale: 0, y: -20 }}
      transition={{
        layout: { duration: 0.16, ease: [0.22, 1, 0.36, 1] },
        duration: 0.18,
        ease: [0.22, 1, 0.36, 1],
        delay: index * 0.03,
      }}
      onTouchStart={(event) => {
        suppressClickRef.current = true;
        event.preventDefault();
        onSelect();
      }}
      onClick={(event) => {
        if (suppressClickRef.current) {
          suppressClickRef.current = false;
          event.preventDefault();
          return;
        }
        onSelect();
      }}
      onPointerDown={(event) => {
        if (event.pointerType !== "mouse") return;
        onSelect();
      }}
      onKeyDown={(event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        onSelect();
      }}
      className="shrink-0 appearance-none bg-transparent p-0 will-change-transform"
      style={{ touchAction: "manipulation" }}
      aria-pressed={isSelected}
    >
      <Tile
        letter={letter}
        isSelected={isSelected}
        layoutId={`rack-tile-${index}`}
        size={tileSize}
        hoverable={false}
      />
    </motion.button>
  );
}

interface TileRackProps {
  canPlaceByTap?: boolean;
  dragEnabled?: boolean;
  tileSize?: "sm" | "md" | "lg" | "rack";
  selectedRackTileIndex?: number | null;
  onRackTileSelect?: (tile: { letter: string; index: number }) => void;
}

export function TileRack({
  canPlaceByTap = false,
  dragEnabled = true,
  tileSize = "lg",
  selectedRackTileIndex = null,
  onRackTileSelect,
}: TileRackProps) {
  const gameState = useGameStore((s) => s.gameState);
  const startingRack = useGameStore((s) => s.startingRack);
  const exchangeMode = useGameStore((s) => s.exchangeMode);
  const exchangeSelected = useGameStore((s) => s.exchangeSelected);
  const toggleExchangeSelection = useGameStore((s) => s.toggleExchangeSelection);
  const pendingTiles = useGameStore((s) => s.pendingTiles);

  const fullRack = useMemo(() => {
    if (isPlausibleRack(gameState?.my_rack)) {
      return gameState.my_rack;
    }
    if (isPlausibleRack(startingRack)) {
      return startingRack;
    }
    return [];
  }, [gameState?.my_rack, startingRack]);

  const usedIndices = new Set(pendingTiles.map((t) => t.rackIndex));
  const visibleRack = fullRack
    .map((letter, i) => ({ letter, index: i }))
    .filter(({ index }) => !usedIndices.has(index));
  const rackHeightClass =
    tileSize === "lg"
      ? "min-h-[4.5rem]"
      : tileSize === "rack"
        ? "min-h-[3.7rem]"
      : tileSize === "md"
        ? "min-h-[3.9rem]"
        : "min-h-[3.3rem]";
  const rackGapClass =
    tileSize === "lg"
      ? "gap-2 sm:gap-2.5"
      : tileSize === "rack"
        ? "gap-1"
      : tileSize === "md"
        ? "gap-1.5 sm:gap-2"
        : "gap-1.5";

  return (
    <div className={`flex w-full items-center justify-center ${rackHeightClass} ${rackGapClass}`}>
      <AnimatePresence mode="popLayout">
        {visibleRack.map(({ letter, index }) => (
          dragEnabled ? (
            <DraggableTile
              key={`${index}-${letter}`}
              letter={letter}
              index={index}
              isExchangeMode={exchangeMode}
              dragEnabled={dragEnabled}
              interactionDisabled={!exchangeMode && !canPlaceByTap}
              isSelected={exchangeMode ? exchangeSelected.has(index) : selectedRackTileIndex === index}
              tileSize={tileSize}
              onSelect={() => {
                if (exchangeMode) {
                  toggleExchangeSelection(index);
                  return;
                }
                onRackTileSelect?.({ letter, index });
              }}
            />
          ) : (
            <TapSelectableTile
              key={`${index}-${letter}`}
              letter={letter}
              index={index}
              isSelected={exchangeMode ? exchangeSelected.has(index) : selectedRackTileIndex === index}
              tileSize={tileSize}
              onSelect={() => {
                if (exchangeMode) {
                  toggleExchangeSelection(index);
                  return;
                }
                if (!canPlaceByTap) return;
                onRackTileSelect?.({ letter, index });
              }}
            />
          )
        ))}
      </AnimatePresence>
      {visibleRack.length === 0 && (
        <span className="text-stone-500 text-sm italic">No tiles on rack</span>
      )}
    </div>
  );
}
