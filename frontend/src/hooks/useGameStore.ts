import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  detectBrowserLocale,
  isLocale,
  writeLocaleCookie,
  type Locale,
} from "@/lib/i18n/locales";
import {
  isSupportedStateSchemaVersion,
  WIRE_STATE_SCHEMA_VERSION,
} from "@/lib/types";
import type {
  GameState,
  Placement,
  MoveResult,
  StartingDraw,
  AICandidate,
  AiFallbackAttempt,
  AiTurnTelemetry,
} from "@/lib/types";
import { isSyntacticallyValidSlug } from "@/lib/variants";

interface PendingTile extends Placement {
  rackIndex: number;
}

export type BoardTheme = "wood" | "black" | "green";

export type SelectedVariantSlug = string;

interface GameStore {
  // Auth
  token: string | null;
  setToken: (token: string | null) => void;
  refreshToken: string | null;
  setRefreshToken: (token: string | null) => void;
  clearAuth: () => void;

  // AI model selection (empty string = unresolved; pages resolve from catalog row 1)
  selectedModelId: string;
  setSelectedModelId: (id: string) => void;

  // Game language for new AI games and queue joins (session snapshot owns live play)
  selectedVariantSlug: SelectedVariantSlug;
  setSelectedVariantSlug: (slug: SelectedVariantSlug) => void;

  // Interface locale (null = never chosen; first-visit detection may set it once)
  uiLocale: Locale | null;
  setUiLocale: (locale: Locale) => void;

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
  premiumLookEnabled: boolean;
  setPremiumLookEnabled: (enabled: boolean) => void;

  // AI candidates (live during thinking)
  aiCandidates: AICandidate[];
  addAICandidate: (candidate: AICandidate) => void;
  clearAICandidates: () => void;

  // AI live status
  aiStatusMessage: string | null;
  setAIStatusMessage: (message: string | null) => void;

  // Structured fallback progress (ordered pills, failures, active attempt)
  aiFallbackAttempts: AiFallbackAttempt[];
  aiFallbackActiveIndex: number | null;
  setAIFallbackAttempts: (attempts: AiFallbackAttempt[]) => void;
  setAIFallbackActiveIndex: (index: number | null) => void;
  markAIFallbackFailed: (index: number) => void;
  clearAIFallbackProgress: () => void;

  // Transient turn telemetry (never persisted)
  aiTurnTelemetry: AiTurnTelemetry | null;
  patchAITurnTelemetry: (patch: AiTurnTelemetry) => void;

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
      refreshToken: null,
      setRefreshToken: (refreshToken) => set({ refreshToken }),
      clearAuth: () => set({ token: null, refreshToken: null }),

      selectedModelId: "",
      setSelectedModelId: (selectedModelId) => set({ selectedModelId }),

      selectedVariantSlug: "english",
      setSelectedVariantSlug: (selectedVariantSlug) => set({ selectedVariantSlug }),

      uiLocale: null,
      setUiLocale: (locale) => {
        writeLocaleCookie(locale);
        set({ uiLocale: locale });
      },

      gameState: null,
      // The SINGLE ingress choke point for every game-state payload, REST and
      // websocket alike, which is why play/page.tsx and waiting/[id]/page.tsx
      // need no guard of their own. A payload whose wire version this client
      // cannot render is REFUSED here rather than mis-rendered: a guard that
      // refuses is loud, a wrong board is silent.
      setGameState: (gameState) => {
        if (!isSupportedStateSchemaVersion(gameState?.state_schema_version)) {
          console.error(
            "libretiles: refusing a game state with unsupported " +
              `state_schema_version ${JSON.stringify(gameState?.state_schema_version)}; ` +
              `this client renders ${WIRE_STATE_SCHEMA_VERSION}`,
          );
          return;
        }
        set({ gameState });
      },

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

      aiTimeout: 120,
      setAITimeout: (aiTimeout) => set({ aiTimeout }),
      aiMaxSteps: 50,
      setAIMaxSteps: (aiMaxSteps) => set({ aiMaxSteps }),
      boardTheme: "wood",
      setBoardTheme: (boardTheme) => set({ boardTheme }),
      boardShineEnabled: true,
      setBoardShineEnabled: (boardShineEnabled) => set({ boardShineEnabled }),
      premiumLookEnabled: true,
      setPremiumLookEnabled: (premiumLookEnabled) => set({ premiumLookEnabled }),

      aiCandidates: [],
      addAICandidate: (candidate) =>
        set((s) => ({ aiCandidates: [...s.aiCandidates, candidate] })),
      clearAICandidates: () => set({ aiCandidates: [] }),

      aiStatusMessage: null,
      setAIStatusMessage: (aiStatusMessage) => set({ aiStatusMessage }),

      aiFallbackAttempts: [],
      aiFallbackActiveIndex: null,
      setAIFallbackAttempts: (aiFallbackAttempts) =>
        set({ aiFallbackAttempts, aiFallbackActiveIndex: null }),
      setAIFallbackActiveIndex: (aiFallbackActiveIndex) =>
        set({ aiFallbackActiveIndex }),
      markAIFallbackFailed: (index) =>
        set((s) => ({
          aiFallbackAttempts: s.aiFallbackAttempts.map((attempt, i) =>
            i === index ? { ...attempt, status: "failed" as const } : attempt,
          ),
        })),
      clearAIFallbackProgress: () =>
        set({
          aiFallbackAttempts: [],
          aiFallbackActiveIndex: null,
          aiTurnTelemetry: null,
        }),

      aiTurnTelemetry: null,
      patchAITurnTelemetry: (patch) =>
        set((s) => ({
          aiTurnTelemetry: { ...s.aiTurnTelemetry, ...patch },
        })),

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
          aiFallbackAttempts: [],
          aiFallbackActiveIndex: null,
          aiTurnTelemetry: null,
          aiCountdown: 0,
          lastMoveResult: null,
          phase: "idle",
          blankPickerOpen: false,
          blankPickerTarget: null,
        }),
    }),
    {
      name: "libretiles-store",
      version: 6,
      migrate: (persistedState, version) => {
        const incoming = { ...((persistedState ?? {}) as Record<string, unknown>) };
        if (version < 1) {
          delete incoming.localAIContextLength;
          delete incoming.localAIReloadAfterTurn;
        }
        if (version < 2) {
          if (incoming.selectedVariantSlug !== "english" && incoming.selectedVariantSlug !== "slovak") {
            incoming.selectedVariantSlug = "english";
          }
        }
        if (version < 3) {
          if (!isLocale(incoming.uiLocale)) {
            incoming.uiLocale = null;
          }
        }
        if (version < 4) {
          if (!isSyntacticallyValidSlug(incoming.selectedVariantSlug)) {
            incoming.selectedVariantSlug = "english";
          }
        }
        if (version < 5) {
          delete incoming.selectedPromptId;
        }
        if (version < 6) {
          // NOTHING TO MIGRATE, and this branch exists to say so rather than
          // leave the version bump unexplained. The bump accompanies wire
          // `state_schema_version` 4, which belongs to the GAME-STATE payload;
          // this store persists PREFERENCES only (see `partialize` below), so
          // no persisted key changed shape or meaning.
        }
        return incoming as unknown as GameStore;
      },
      onRehydrateStorage: () => () => {
        if (typeof navigator === "undefined") return;
        const languages =
          navigator.languages && navigator.languages.length > 0
            ? Array.from(navigator.languages)
            : navigator.language
              ? [navigator.language]
              : [];
        adoptBrowserLocaleIfUnset(languages);
      },
      storage: createJSONStorage(() =>
        typeof window !== "undefined" ? localStorage : {
          getItem: () => null,
          setItem: () => {},
          removeItem: () => {},
        },
      ),
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        selectedModelId: state.selectedModelId,
        selectedVariantSlug: state.selectedVariantSlug,
        uiLocale: state.uiLocale,
        aiTimeout: state.aiTimeout,
        aiMaxSteps: state.aiMaxSteps,
        boardTheme: state.boardTheme,
        boardShineEnabled: state.boardShineEnabled,
        premiumLookEnabled: state.premiumLookEnabled,
      }),
    },
  ),
);

export function adoptBrowserLocaleIfUnset(languages: readonly string[]): Locale {
  const current = useGameStore.getState().uiLocale;
  if (isLocale(current)) return current;
  const detected = detectBrowserLocale(languages);
  useGameStore.getState().setUiLocale(detected);
  return detected;
}
