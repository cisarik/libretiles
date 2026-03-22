import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type {
  GameState,
  Placement,
  MoveResult,
  StartingDraw,
  AICandidate,
} from "@/lib/types";

interface PendingTile extends Placement {
  rackIndex: number;
}

export type BoardTheme = "wood" | "black" | "green";

interface GameStore {
  // Auth
  token: string | null;
  setToken: (token: string | null) => void;
  creditBalance: string | null;
  setCreditBalance: (balance: string | null) => void;

  // AI model selection
  selectedModelId: string;
  setSelectedModelId: (id: string) => void;

  // Game state
  gameState: GameState | null;
  setGameState: (state: GameState) => void;

  // Starting draw
  startingDraw: StartingDraw | null;
  setStartingDraw: (draw: StartingDraw | null) => void;
  startingRack: string[] | null;
  setStartingRack: (rack: string[] | null) => void;

  // Pending tiles (placed on board but not submitted)
  pendingTiles: PendingTile[];
  addPendingTile: (tile: PendingTile) => void;
  removePendingTile: (row: number, col: number) => void;
  clearPendingTiles: () => void;

  // Exchange mode
  exchangeMode: boolean;
  exchangeSelected: Set<number>;
  setExchangeMode: (active: boolean) => void;
  toggleExchangeSelection: (index: number) => void;
  clearExchangeSelection: () => void;

  // AI thinking
  aiThinking: boolean;
  setAIThinking: (thinking: boolean) => void;

  // AI timeout (persisted)
  aiTimeout: number;
  setAITimeout: (seconds: number) => void;
  aiMaxSteps: number;
  setAIMaxSteps: (steps: number) => void;
  boardTheme: BoardTheme;
  setBoardTheme: (theme: BoardTheme) => void;
  boardShineEnabled: boolean;
  setBoardShineEnabled: (enabled: boolean) => void;

  // AI candidates (live during thinking)
  aiCandidates: AICandidate[];
  addAICandidate: (candidate: AICandidate) => void;
  clearAICandidates: () => void;

  // AI live status
  aiStatusMessage: string | null;
  setAIStatusMessage: (message: string | null) => void;

  // AI countdown (seconds remaining)
  aiCountdown: number;
  setAICountdown: (seconds: number) => void;

  // Last move result
  lastMoveResult: MoveResult | null;
  setLastMoveResult: (result: MoveResult | null) => void;

  // Game phase
  phase: "idle" | "drawing" | "playing" | "exchange" | "ai_thinking" | "game_over";
  setPhase: (phase: GameStore["phase"]) => void;

  // Blank picker
  blankPickerOpen: boolean;
  blankPickerTarget: { row: number; col: number; rackIndex: number } | null;
  openBlankPicker: (row: number, col: number, rackIndex: number) => void;
  closeBlankPicker: () => void;

  resetGameUi: () => void;
}

export const useGameStore = create<GameStore>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => set({ token }),
      creditBalance: null,
      setCreditBalance: (creditBalance) => set({ creditBalance }),

      selectedModelId: process.env.NEXT_PUBLIC_DEFAULT_MODEL || "openai/gpt-5.4",
      setSelectedModelId: (selectedModelId) => set({ selectedModelId }),

      gameState: null,
      setGameState: (gameState) => set({ gameState }),

      startingDraw: null,
      setStartingDraw: (startingDraw) => set({ startingDraw }),
      startingRack: null,
      setStartingRack: (startingRack) => set({ startingRack }),

      pendingTiles: [],
      addPendingTile: (tile) =>
        set((s) => ({
          pendingTiles: [
            ...s.pendingTiles.filter(
              (t) =>
                t.rackIndex !== tile.rackIndex &&
                (t.row !== tile.row || t.col !== tile.col),
            ),
            tile,
          ],
        })),
      removePendingTile: (row, col) =>
        set((s) => ({
          pendingTiles: s.pendingTiles.filter((t) => t.row !== row || t.col !== col),
        })),
      clearPendingTiles: () => set({ pendingTiles: [] }),

      exchangeMode: false,
      exchangeSelected: new Set(),
      setExchangeMode: (active) =>
        set({ exchangeMode: active, exchangeSelected: new Set() }),
      toggleExchangeSelection: (index) =>
        set((s) => {
          const next = new Set(s.exchangeSelected);
          if (next.has(index)) next.delete(index);
          else next.add(index);
          return { exchangeSelected: next };
        }),
      clearExchangeSelection: () => set({ exchangeSelected: new Set() }),

      aiThinking: false,
      setAIThinking: (aiThinking) => set({ aiThinking }),

      aiTimeout: 30,
      setAITimeout: (aiTimeout) => set({ aiTimeout }),
      aiMaxSteps: 30,
      setAIMaxSteps: (aiMaxSteps) => set({ aiMaxSteps }),
      boardTheme: "wood",
      setBoardTheme: (boardTheme) => set({ boardTheme }),
      boardShineEnabled: true,
      setBoardShineEnabled: (boardShineEnabled) => set({ boardShineEnabled }),

      aiCandidates: [],
      addAICandidate: (candidate) =>
        set((s) => ({ aiCandidates: [...s.aiCandidates, candidate] })),
      clearAICandidates: () => set({ aiCandidates: [] }),

      aiStatusMessage: null,
      setAIStatusMessage: (aiStatusMessage) => set({ aiStatusMessage }),

      aiCountdown: 0,
      setAICountdown: (aiCountdown) => set({ aiCountdown }),

      lastMoveResult: null,
      setLastMoveResult: (lastMoveResult) => set({ lastMoveResult }),

      phase: "idle",
      setPhase: (phase) => set({ phase }),

      blankPickerOpen: false,
      blankPickerTarget: null,
      openBlankPicker: (row, col, rackIndex) =>
        set({ blankPickerOpen: true, blankPickerTarget: { row, col, rackIndex } }),
      closeBlankPicker: () =>
        set({ blankPickerOpen: false, blankPickerTarget: null }),
      resetGameUi: () =>
        set({
          gameState: null,
          pendingTiles: [],
          exchangeMode: false,
          exchangeSelected: new Set(),
          aiThinking: false,
          aiCandidates: [],
          aiStatusMessage: null,
          aiCountdown: 0,
          lastMoveResult: null,
          phase: "idle",
          blankPickerOpen: false,
          blankPickerTarget: null,
        }),
    }),
    {
      name: "libretiles-store",
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? localStorage : {
          getItem: () => null,
          setItem: () => {},
          removeItem: () => {},
        },
      ),
      partialize: (state) => ({
        token: state.token,
        selectedModelId: state.selectedModelId,
        aiTimeout: state.aiTimeout,
        aiMaxSteps: state.aiMaxSteps,
        boardTheme: state.boardTheme,
        boardShineEnabled: state.boardShineEnabled,
      }),
    },
  ),
);
