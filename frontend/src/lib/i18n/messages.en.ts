import { pluralEn } from "./plural";

export const enText = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "human and AI.",
  "landing.lead":
    "Open-source wordplay with live matchmaking, sharp AI rivals, premium board chrome, and a history surface ready for your next board.",
  "landing.card.ai.title": "AI duels",
  "landing.card.ai.body": "Model-aware premium games",
  "landing.card.queue.title": "Live queue",
  "landing.card.queue.body": "Realtime sync and chat",
  "landing.card.saved.title": "Saved boards",
  "landing.card.saved.body": "Resume AI or human games",
  "landing.footnote": "Open source • Collins Scrabble Words 2019 • 279,496 valid words",
  "auth.eyebrow": "Account",
  "auth.heading.login": "Sign in",
  "auth.heading.register": "Create account",
  "auth.tab.login": "Sign In",
  "auth.tab.register": "Register",
  "auth.field.username": "Username",
  "auth.field.password": "Password",
  "a11y.chatInput": "Chat message",
  "a11y.dialog.profile": "Profile",
  "a11y.dialog.games": "Saved games",
  "a11y.dialog.blank": "Choose a letter",
  "a11y.dialog.rival": "Rival unavailable",
  "a11y.status.turn": "Turn status",
  "a11y.status.aiThinking": "AI progress",
  "a11y.rackBlank": "Blank tile",
  "auth.submit.loading": "Signing in...",
  "auth.submit.login": "Play now",
  "auth.submit.register": "Create account & play",
  "meta.title": "Libre Tiles — Web Libre Tiles with AI and Live Multiplayer",
  "meta.description":
    "Open-source Libre Tiles with AI rivals, live human matches, chat, and polished drag-and-drop play.",
  "error.checkFields": "Please check the submitted fields.",
  "error.invalidCredentials": "Invalid username or password",
  "error.sessionExpired": "Your session expired. Please sign in again.",
  "error.forbidden": "You do not have permission to do that.",
  "error.notFound": "Not found.",
  "error.conflict": "This action conflicts with the current game state.",
  "error.throttled.unknown": "Too many requests. Please wait and try again.",
  "error.throttled.oneMinute": "Too many requests. Try again in about a minute.",
  "error.unavailable": "The service is temporarily unavailable. Please try again.",
  "error.generic": "Something went wrong. Please try again.",
  "settings.timeout.title": "AI Thinking Time",
  "settings.timeout.30": "Fast board read",
  "settings.timeout.60": "Balanced search",
  "settings.timeout.120": "Default thinking time",
  "settings.timeout.180": "Tournament pace",
  "settings.timeout.300": "Longest think",
  "settings.steps.title": "Search Steps",
  "settings.steps.10": "Quick tools",
  "settings.steps.20": "More tries",
  "settings.steps.30": "Focused search",
  "settings.steps.50": "Default search depth",
  "settings.steps.80": "Max pressure",
  "settings.board.title": "Board Surface",
  "settings.board.description":
    "Saved on this device and used in the game board.",
  "settings.board.wood": "Wood",
  "settings.board.woodDesc": "Classic walnut grain",
  "settings.board.black": "Black",
  "settings.board.blackDesc": "Glossy night lacquer",
  "settings.board.green": "Green",
  "settings.board.greenDesc": "Dark tournament felt",
  "settings.board.active": "Active",
  "settings.toggle.on": "On",
  "settings.toggle.off": "Off",
  "settings.shiny.title": "Shiny Effect",
  "settings.shiny.description":
    "Turn the live sheen off when you want a lighter GPU load.",
  "settings.shiny.onDesc": "Animated board sheen",
  "settings.shiny.offDesc": "Lower GPU load",
  "settings.premium.title": "Premium Look",
  "settings.premium.description":
    "Interactive amber spotlight for the game header and rack panel.",
  "settings.premium.onDesc": "Premium interactive panels",
  "settings.premium.offDesc": "Classic dark surfaces",
  "settings.backToGame": "Back to game",
  "settings.error.newGame": "Could not start a fresh game right now.",
  "settings.warn.accountSync":
    "Account sync is unavailable right now. Settings still work locally on this device.",
  "settings.warn.rivalRepair":
    "A free rival is selected on this device. Account preference could not be repaired yet.",
  "settings.uiLanguage.title": "Interface language",
  "settings.uiLanguage.description":
    "Menus, buttons, and messages. Changes immediately, on this device only.",
  // Interface-language names are endonyms, identical in every catalog, so a
  // user who accidentally selected a language they cannot read can still find
  // their own language. Do not translate these four strings back into exonyms.
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "picker.search": "Search",
  "picker.noMatch": "No match",
  "picker.uiLanguageLabel": "Interface language",
  "picker.gameVariantLabel": "Game variant",
  "settings.gameVariant.title": "Game variant",
  "settings.gameVariant.description":
    "Tiles, bag, and lexicon. Applies to NEW games only and never changes a running game. This is not the interface language.",
  "settings.gameVariant.english": "English",
  "settings.gameVariant.slovak": "Slovak",
  "settings.gameVariant.czech": "Czech",
  "settings.gameVariant.polish": "Polish",
  "settings.rival.title": "Your rival",
  "settings.rival.description":
    "The administrator picks the rival for new games.",
  "nav.settings": "Settings",
  "nav.account": "Account",
  "profile.subtitle": "Account details and password security in one place.",
  "profile.email": "Email",
  "profile.noEmail": "No email set",
  "profile.memberSince": "Member since",
  "profile.password.subtitle":
    "Update your login password without leaving the game.",
  "profile.password.footnote":
    "Stronger passwords make multiplayer accounts safer.",
  "profile.field.current": "Current password",
  "profile.field.new": "New password",
  "profile.field.confirm": "Confirm new password",
  "profile.ph.current": "Current password",
  "profile.ph.new": "At least 8 characters",
  "profile.ph.confirm": "Repeat new password",
  "profile.submit": "Update password",
  "profile.submitting": "Updating...",
  "profile.error.allFields": "Fill in all password fields.",
  "profile.error.mismatch": "New passwords do not match.",
  "play.title": "Choose the next board",
  "play.lead":
    "Start a premium AI duel, jump into the live queue, or reopen one of your saved boards.",
  "play.ai.eyebrow": "AI Match",
  "play.ai.title": "Play the house",
  "play.ai.body":
    "Use the current AI rival and keep the animated opening draw.",
  "play.ai.preparing": "Preparing game...",
  "play.rival.unavailable": "No rival available",
  "play.humanQueue.eyebrow": "Human Queue",
  "play.humanQueue.title": "Find a live opponent",
  "play.humanQueue.body":
    "Join the first waiting player. If nobody is there, your board waits in the room.",
  "play.humanQueue.joining": "Joining queue...",
  "play.saved.eyebrow": "Saved boards",
  "play.saved.title": "Resume where you left off",
  "play.saved.note":
    "AI and human games share one premium history surface.",
  "play.error.catalogEmpty":
    "The rival catalog is empty. Seed the free catalog to play AI matches.",
  "play.error.catalogUnavailable":
    "The rival catalog is temporarily unavailable. Try again in a moment.",
  "play.error.variantUnavailable":
    "No playable game variant is available. Game creation is blocked until a playable variant can be loaded.",
  "play.error.startAi": "Could not start an AI game.",
  "play.error.joinQueue": "Could not join the human queue.",
  "play.error.loadGames": "Unable to load your games.",
  "history.filter.ai": "AI",
  "history.filter.human": "Human",
  "history.filter.all": "All",
  "history.sort.recent": "Recent",
  "history.refresh": "Refresh",
  "history.loading": "Loading games",
  "history.empty.title": "No games in this filter yet",
  "history.empty.body":
    "Start a new board and it will show up here with premium paging, result badges, and quick resume links.",
  "history.noneYet": "No saved boards yet",
  "history.unknownDate": "Unknown",
  "history.col.rival": "Rival",
  "history.col.mode": "Mode",
  "history.col.result": "Result",
  "history.col.score": "Score",
  "history.col.moves": "Moves",
  "history.col.updated": "Updated",
  "history.outcome.waiting": "Waiting",
  "history.outcome.active": "In progress",
  "history.outcome.won": "Won",
  "history.outcome.lost": "Lost",
  "history.outcome.draw": "Draw",
  "history.outcome.gaveUp": "Gave up",
  "history.outcome.abandoned": "Abandoned",
  "history.outcome.unknown": "Unknown",
  "history.mode.ai": "AI duel",
  "history.mode.human": "Human duel",
  "history.hint.waitingRoom": "Waiting room",
  "history.hint.boardReady": "Board ready",
  "history.endReason.bagEmpty": "Bag and rack empty",
  "history.endReason.noMoves": "No moves available",
  "history.endReason.sixZero": "Six scoreless turns",
  "history.endReason.gaveUp": "Resigned",
  "history.endReason.queueCancelled": "Queue cancelled",
  "history.open": "Open",
  "history.current": "Current",
  "history.prev": "Previous",
  "history.next": "Next",
  "history.modal.subtitle":
    "Review past boards, switch between AI and human games, and jump back in fast.",
  "queue.title": "Waiting for an opponent",
  "queue.body":
    "Your board is ready. The match starts as soon as another player joins.",
  "queue.leave": "Leave queue",
  "queue.leaving": "Leaving queue...",
  "queue.error.dropped": "Realtime connection dropped.",
  "queue.error.enter": "Could not enter the waiting room.",
  "queue.error.leave": "Could not leave the queue.",
  "draw.eyebrow": "Starting draw",
  "draw.title": "Who opens the board",
  "draw.subtitle": "Whoever draws the tile closer to A starts. A blank always wins.",
  "draw.side.you": "You",
  "draw.side.ai": "AI",
  "draw.pending": "Drawing tiles from the bag...",
  "draw.blankCaption": "blank",
  "draw.result.youStart": "You start",
  "draw.result.aiStart": "AI starts",
  "draw.reason.blankYou": "Your blank wins the draw.",
  "draw.reason.blankAi": "The AI drew the blank.",
  "draw.reason.bothBlank": "Both tiles are blanks, so you start.",
  "controls.play": "Play",
  "controls.pass": "Pass",
  "controls.exchange": "Exchange",
  "controls.confirmExchange": "Confirm exchange",
  "controls.cancel": "Cancel",
  "board.pts": "PTS",
  "board.pinchToZoom": "Pinch to zoom",
  "board.dragToPan": "Drag to pan",
  "board.hide": "Hide",
  "board.reset": "Reset",
  "rack.empty": "No tiles on rack",
  "blank.chooseLetter": "Choose a letter for blank tile",
  "chat.title": "Game Chat",
  "chat.empty": "No messages yet.",
  "chat.you": "You",
  "chat.unavailable": "Chat unavailable",
  "chat.placeholder": "Say something",
  "chat.send": "Send",
  "game.lexicon.collins2019": "Not in Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Not in the Slovak lexicon",
  "game.lexicon.czech": "Not in the Czech lexicon",
  "game.lexicon.polish": "Not in the Polish lexicon",
  "game.lexicon.unknown": "Not in the game lexicon",
  "game.blocker.auth.title": "Rival authentication failed",
  "game.blocker.auth.body":
    "This free rival could not authenticate. Switch to another free rival or retry later.",
  "game.blocker.rate.title": "Rival is rate limited",
  "game.blocker.rate.body":
    "This free rival is rate limited. Switch to another free rival or retry later.",
  "game.blocker.unavail.title": "Rival is unavailable",
  "game.blocker.unavail.body":
    "This free rival is temporarily unavailable. Switch to another free rival or retry later.",
  "game.blocker.badge.auth": "Authentication",
  "game.blocker.badge.rate": "Rate Limited",
  "game.blocker.badge.unavail": "Unavailable",
  "game.blocker.close": "Close",
  "game.blocker.openSettings": "Open settings",
  "game.toast.invalidPlacement": "Invalid Placement",
  "game.toast.invalidWords": "Invalid words",
  "game.toast.moveRejected": "Move rejected",
  "game.toast.exchangeRejected": "Exchange rejected",
  "game.toast.passRejected": "Pass rejected",
  "game.toast.chatOffline": "Chat is offline",
  "game.toast.aiPasses": "AI passes",
  "game.toast.aiExchanged": "AI exchanged tiles",
  "game.toast.aiExchangedBody": "AI refreshed the rack and spent the turn.",
  "game.toast.aiPassedBody": "Couldn't find a valid move - your turn!",
  "game.aiPlayedFor.before": "AI played for",
  "game.aiPlayedFor.points": "pts",
  "game.aWord": "a word",
  "game.status.selectExchange": "Select tiles to exchange",
  "game.status.aiMoveReady": "AI move ready",
  "game.status.aiThinking": "AI is thinking",
  "game.status.yourTurn": "Your turn",
  "game.status.waitingForAi": "Waiting for the AI",
  "game.opponentFallback": "Opponent",
  "game.waitingSlot": "Waiting",
  "game.sessionExpired": "Session expired",
  "game.lastError": "Last error:",
  "game.newGame": "New Game",
  "game.starting": "Starting...",
  "game.victory": "Victory!",
  "game.draw": "Draw!",
  "game.gameOver": "Game Over",
  "game.giveUp.ai": "Give up this game? The AI will be declared the winner.",
  "game.giveUp.human":
    "Give up this game? Your opponent will be declared the winner.",
  "game.gaveUp": "You gave up the game.",
  "game.error.giveUp": "Could not give up this game",
  "game.error.newGame": "Could not start a new game",
  "game.error.loadGames": "Unable to load games.",
  "game.password.updated": "Password updated.",
  "game.password.failed": "Unable to update password.",
  "game.ai.noRival": "No eligible free rival is available.",
  "game.ai.timeout": "AI thinking time ran out.",
  "game.ai.moveFailed": "AI move failed",
  "game.ws.syncFailed": "Realtime sync failed",
  "game.ws.connectFailed": "Realtime connection failed",
  "game.ws.authExpired":
    "Realtime authentication expired. Refresh the page to reconnect.",
  "game.ws.invalidSession":
    "This realtime session is not valid. Refresh the page to reconnect.",
  "game.ws.unavailable":
    "The realtime service is unavailable. Please try again.",
  "board.zoomNoun": "zoom",
  "header.giveUp": "Give up",
  "header.givingUp": "Giving up...",
  "header.giveUpTooltip": "Give up current game",
  "header.logout": "Logout",
  "header.loggingOut": "Logging out...",
  "header.backToBoards": "Back to boards",
  "header.profile": "Profile",
  "header.games": "Games",
  "overlay.aiThinking": "AI Thinking",
  "overlay.searching": "Searching for moves...",
  "overlay.best": "Best",
  "overlay.bestBadge": "BEST",
  "overlay.filtering":
    "Filtering weak or invalid lines before showing a serious move...",
} as const;

export const enFn = {
  "a11y.rackTile": (p: { letter: string; points: number }) =>
    `Tile ${p.letter}, ${p.points} ${pluralEn(p.points, "point", "points")}`,
  "overlay.stats.tried": (p: { count: number }) => `${p.count} tried`,
  "overlay.stats.valid": (p: { count: number }) => `${p.count} valid`,
  "overlay.stats.rejected": (p: { count: number }) => `${p.count} rejected`,
  "error.throttled.minutes": (p: { minutes: number }) =>
    `Too many requests. Try again in about ${p.minutes} minutes.`,
  "draw.reason.closer": (p: { winner: string; loser: string }) =>
    `${p.winner} is closer to A than ${p.loser}.`,
  "controls.tilesSelected": (p: { count: number }) =>
    `${p.count} tile${p.count !== 1 ? "s" : ""} selected`,
  "game.ai.exploring": (p: { model: string }) =>
    `Exploring legal words with ${p.model}...`,
  "game.ai.attempt": (p: { index: number; total: number; label: string }) =>
    `Attempt ${p.index}/${p.total} · ${p.label}`,
  "game.toast.aiPlayedWord": (p: { word: string }) => `AI played ${p.word}`,
  "game.status.opponentPlaying": (p: { name: string }) => `${p.name} is playing`,
  "game.toast.invalidWordHeading": (p: { count: number }) =>
    `Invalid Word${p.count > 1 ? "s" : ""}!`,
  "game.ai.routeFailed": (p: { status: number }) =>
    `AI route failed (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p: { status: number }) =>
    `AI route failed (${p.status}) before the stream started.`,
  "game.ai.routeFailedWithPreview": (p: { status: number; preview: string }) =>
    `AI route failed (${p.status}): ${p.preview}`,
  "play.humanQueue.queueFor": (p: { variant: string }) => `${p.variant} queue`,
  "queue.room": (p: { code: string }) => `Room ${p.code}`,
  "history.pageOf": (p: { page: number; total: number }) =>
    `Page ${p.page} of ${p.total}`,
  "history.showing": (p: { from: number; to: number; total: number }) =>
    `Showing ${p.from}-${p.to} of ${p.total} games`,
  "picker.flagAlt": (p: { language: string }) => `${p.language} flag`,
} as const;

export type TextKey = keyof typeof enText;
export type FnKey = keyof typeof enFn;

export type AiPassKind = "pass" | "exchange";

export function lexiconRejectionKey(
  lexiconId: string | null | undefined,
): TextKey {
  switch (lexiconId) {
    case "collins2019":
      return "game.lexicon.collins2019";
    case "slovak":
      return "game.lexicon.slovak";
    case "czech":
      return "game.lexicon.czech";
    case "polish":
      return "game.lexicon.polish";
    default:
      return "game.lexicon.unknown";
  }
}

export function aiPassBodyKey(input: {
  passKind?: AiPassKind;
}): TextKey {
  return input.passKind === "exchange"
    ? "game.toast.aiExchangedBody"
    : "game.toast.aiPassedBody";
}
