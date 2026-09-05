// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralDe } from "./plural";

// Frozen German game terminology (GLOSSARY D6), chosen once and reused everywhere:
// tile Stein · letter Buchstabe · rack Bank · blank Blanko · bag Beutel ·
// board Spielbrett (stem Brett in compounds) · pass Passen · points Punkte (Pkt.).
// `Blanko` appears in running text in its unambiguous compound form `Blankostein`,
// which fixes the article at `der` and keeps the tile distinct from `Buchstabe`.
// Register: informal `du` / `dein` throughout, error messages included.
// Control and action labels: infinitive, never imperative, across every control.
export const deText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "Mensch und AI.",
  "landing.lead":
    "Open-Source-Wortspiel mit Live-Matchmaking, starken AI-Gegnern, edler Brettoptik und einer Historie, die auf deine nächste Partie wartet.",
  "landing.card.ai.title": "AI-Duelle",
  "landing.card.ai.body": "Premium-Partien mit Modellauswahl",
  "landing.card.queue.title": "Live-Warteschlange",
  "landing.card.queue.body": "Echtzeit-Sync und Chat",
  "landing.card.saved.title": "Gespeicherte Partien",
  "landing.card.saved.body": "Partien gegen AI oder Menschen fortsetzen",
  "landing.footnote":
    "Open Source • Collins Scrabble Words 2019 • 279.496 gültige Wörter",
  "auth.eyebrow": "Konto",
  "auth.heading.login": "Anmelden",
  "auth.heading.register": "Konto erstellen",
  "auth.tab.login": "Anmelden",
  "auth.tab.register": "Registrieren",
  "auth.field.username": "Benutzername",
  "auth.field.password": "Passwort",
  "a11y.chatInput": "Chat-Nachricht",
  "a11y.dialog.profile": "Profil",
  "a11y.dialog.games": "Gespeicherte Partien",
  "a11y.dialog.blank": "Buchstabe wählen",
  "a11y.dialog.rival": "Gegner nicht verfügbar",
  "a11y.status.turn": "Zugstatus",
  "a11y.status.aiThinking": "AI-Fortschritt",
  "a11y.rackBlank": "Blankostein",
  "auth.submit.loading": "Melde an...",
  "auth.submit.login": "Jetzt spielen",
  "auth.submit.register": "Konto erstellen und spielen",
  "meta.title": "Libre Tiles — Wortspiel im Web mit AI und Live-Multiplayer",
  "meta.description":
    "Open-Source-Wortspiel mit AI-Gegnern, Live-Partien gegen Menschen, Chat und flüssigem Drag-and-Drop.",
  "error.checkFields": "Prüfe die eingegebenen Daten.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Benutzername oder Passwort ist falsch",
  "error.sessionExpired": "Deine Sitzung ist abgelaufen. Melde dich erneut an.",
  "error.forbidden": "Dafür hast du keine Berechtigung.",
  "error.notFound": "Nicht gefunden.",
  "error.conflict": "Diese Aktion passt nicht zum aktuellen Stand der Partie.",
  "error.throttled.unknown":
    "Zu viele Anfragen. Warte kurz und versuche es erneut.",
  "error.throttled.oneMinute":
    "Zu viele Anfragen. Versuche es in etwa einer Minute erneut.",
  "error.unavailable":
    "Der Dienst ist gerade nicht verfügbar. Versuche es erneut.",
  "error.generic": "Etwas ist schiefgelaufen. Versuche es erneut.",
  "settings.timeout.title": "Denkzeit der AI",
  "settings.timeout.30": "Schneller Blick aufs Brett",
  "settings.timeout.60": "Ausgewogene Suche",
  "settings.timeout.120": "Standard-Denkzeit",
  "settings.timeout.180": "Turniertempo",
  "settings.timeout.300": "Längste Denkzeit",
  "settings.steps.title": "Suchschritte",
  "settings.steps.10": "Schnelle Tools",
  "settings.steps.20": "Mehr Versuche",
  "settings.steps.30": "Fokussierte Suche",
  "settings.steps.50": "Standard-Suchtiefe",
  "settings.steps.80": "Maximaler Druck",
  "settings.board.title": "Brettoberfläche",
  "settings.board.description":
    "Auf diesem Gerät gespeichert und im Spielbrett verwendet.",
  "settings.board.wood": "Holz",
  "settings.board.woodDesc": "Klassische Nussbaummaserung",
  "settings.board.black": "Schwarz",
  "settings.board.blackDesc": "Glänzender Nachtlack",
  "settings.board.green": "Grün",
  "settings.board.greenDesc": "Dunkler Turnierfilz",
  "settings.board.active": "Aktiv",
  "settings.toggle.on": "Ein",
  "settings.toggle.off": "Aus",
  "settings.shiny.title": "Glanzeffekt",
  "settings.shiny.description":
    "Schalte den lebendigen Glanz aus, wenn du die GPU entlasten willst.",
  "settings.shiny.onDesc": "Animierter Brettglanz",
  "settings.shiny.offDesc": "Geringere GPU-Last",
  "settings.premium.title": "Premium-Look",
  "settings.premium.description":
    "Interaktives Bernsteinlicht für die Kopfzeile der Partie und die Bank.",
  "settings.premium.onDesc": "Interaktive Premium-Flächen",
  "settings.premium.offDesc": "Klassische dunkle Flächen",
  "settings.backToGame": "Zurück zur Partie",
  "settings.error.newGame":
    "Eine neue Partie konnte gerade nicht gestartet werden.",
  "settings.warn.accountSync":
    "Die Kontosynchronisierung ist gerade nicht verfügbar. Die Einstellungen wirken weiterhin lokal auf diesem Gerät.",
  "settings.warn.rivalRepair":
    "Auf diesem Gerät ist ein kostenloser Gegner ausgewählt. Die Einstellung im Konto konnte noch nicht repariert werden.",
  "settings.uiLanguage.title": "Oberflächensprache",
  "settings.uiLanguage.description":
    "Menüs, Schaltflächen und Meldungen. Gilt sofort und nur auf diesem Gerät.",
  // Endonyms, identical in every catalog. Do not turn them into German exonyms.
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "settings.uiLanguage.af": "Afrikaans",
  "settings.uiLanguage.da": "Dansk",
  "settings.uiLanguage.de": "Deutsch",
  "settings.uiLanguage.is": "Íslenska",
  "settings.uiLanguage.it": "Italiano",
  "settings.uiLanguage.nl": "Nederlands",
  "settings.uiLanguage.pt": "Português",
  "settings.uiLanguage.sv": "Svenska",
  "picker.search": "Suchen",
  "picker.noMatch": "Kein Treffer",
  "picker.uiLanguageLabel": "Oberflächensprache",
  "picker.gameVariantLabel": "Spielvariante",
  "settings.gameVariant.title": "Spielvariante",
  "settings.gameVariant.description":
    "Steine, Beutel und Lexikon. Gilt nur für NEUE Partien und ändert eine laufende Partie nie. Das ist nicht die Oberflächensprache.",
  // Game-variant names are translated exonyms, unlike the endonyms above.
  "settings.gameVariant.english": "Englisch",
  "settings.gameVariant.slovak": "Slowakisch",
  "settings.gameVariant.czech": "Tschechisch",
  "settings.gameVariant.polish": "Polnisch",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italienisch",
  "settings.gameVariant.dutch": "Niederländisch",
  "settings.gameVariant.german": "Deutsch",
  "settings.gameVariant.portuguese": "Portugiesisch",
  "settings.gameVariant.danish": "Dänisch",
  "settings.gameVariant.swedish": "Schwedisch",
  "settings.gameVariant.icelandic": "Isländisch",
  "settings.rival.title": "Dein Gegner",
  "settings.rival.description":
    "Den Gegner für neue Partien wählt der Administrator.",
  "nav.settings": "Einstellungen",
  "nav.account": "Konto",
  "profile.subtitle": "Kontodaten und Passwortsicherheit an einem Ort.",
  "profile.email": "E-Mail",
  "profile.noEmail": "Keine E-Mail hinterlegt",
  "profile.memberSince": "Mitglied seit",
  "profile.password.subtitle":
    "Ändere dein Passwort, ohne die Partie zu verlassen.",
  "profile.password.footnote":
    "Stärkere Passwörter schützen dein Konto in Partien gegen Menschen besser.",
  "profile.field.current": "Aktuelles Passwort",
  "profile.field.new": "Neues Passwort",
  "profile.field.confirm": "Neues Passwort bestätigen",
  "profile.ph.current": "Aktuelles Passwort",
  "profile.ph.new": "Mindestens 8 Zeichen",
  "profile.ph.confirm": "Neues Passwort wiederholen",
  "profile.submit": "Passwort ändern",
  "profile.submitting": "Ändere...",
  "profile.error.allFields": "Fülle alle Passwortfelder aus.",
  "profile.error.mismatch": "Die neuen Passwörter stimmen nicht überein.",
  "play.title": "Wähle deine nächste Partie",
  "play.lead":
    "Starte ein Premium-Duell gegen die AI, spring in die Live-Warteschlange oder öffne eine deiner gespeicherten Partien.",
  "play.ai.eyebrow": "AI-Partie",
  "play.ai.title": "Spiele gegen die AI",
  "play.ai.body":
    "Spiele gegen den aktuellen AI-Gegner, mit der animierten Auslosung zum Start.",
  "play.ai.preparing": "Bereite die Partie vor...",
  "play.rival.unavailable": "Kein Gegner verfügbar",
  "play.humanQueue.eyebrow": "Spieler-Warteschlange",
  "play.humanQueue.title": "Finde einen echten Gegner",
  "play.humanQueue.body":
    "Schließe dich dem ersten wartenden Spieler an. Ist niemand da, wartet deine Partie im Warteraum.",
  "play.humanQueue.joining": "Trete der Warteschlange bei...",
  "play.saved.eyebrow": "Gespeicherte Partien",
  "play.saved.title": "Mach dort weiter, wo du aufgehört hast",
  "play.saved.note":
    "Partien gegen die AI und gegen Menschen teilen eine gemeinsame Premium-Historie.",
  "play.error.catalogEmpty":
    "Der Gegnerkatalog ist leer. Fülle den kostenlosen Katalog, damit AI-Partien möglich sind.",
  "play.error.catalogUnavailable":
    "Der Gegnerkatalog ist gerade nicht verfügbar. Versuche es in einem Moment erneut.",
  "play.error.variantUnavailable":
    "Es ist keine spielbare Spielvariante verfügbar. Neue Partien sind blockiert, bis eine spielbare Variante geladen werden kann.",
  "play.error.startAi":
    "Die Partie gegen die AI konnte nicht gestartet werden.",
  "play.error.joinQueue":
    "Der Beitritt zur Spieler-Warteschlange ist fehlgeschlagen.",
  "play.error.loadGames": "Deine Partien konnten nicht geladen werden.",
  "history.filter.ai": "AI",
  "history.filter.human": "Menschen",
  "history.filter.all": "Alle",
  "history.sort.recent": "Neueste",
  "history.refresh": "Aktualisieren",
  "history.loading": "Lade Partien",
  "history.empty.title": "In diesem Filter gibt es noch keine Partien",
  "history.empty.body":
    "Starte eine neue Partie, und sie erscheint hier mit edler Seitennavigation, Ergebnisabzeichen und schnellen Links zum Weiterspielen.",
  "history.noneYet": "Noch keine gespeicherten Partien",
  "history.unknownDate": "Unbekannt",
  "history.col.rival": "Gegner",
  "history.col.mode": "Modus",
  "history.col.result": "Ergebnis",
  "history.col.score": "Punkte",
  "history.col.moves": "Züge",
  "history.col.updated": "Geändert",
  "history.outcome.waiting": "Wartet",
  "history.outcome.active": "Läuft",
  "history.outcome.won": "Gewonnen",
  "history.outcome.lost": "Verloren",
  "history.outcome.draw": "Unentschieden",
  "history.outcome.gaveUp": "Aufgegeben",
  "history.outcome.abandoned": "Verlassen",
  "history.outcome.unknown": "Unbekannt",
  "history.mode.ai": "AI-Duell",
  "history.mode.human": "Duell gegen Menschen",
  "history.hint.waitingRoom": "Warteraum",
  "history.hint.boardReady": "Partie bereit",
  "history.endReason.bagEmpty": "Beutel und Bank leer",
  "history.endReason.noMoves": "Kein Zug möglich",
  "history.endReason.sixZero": "Sechs Züge ohne Punkte",
  "history.endReason.gaveUp": "Partie aufgegeben",
  "history.endReason.queueCancelled": "Warteschlange abgebrochen",
  "history.open": "Öffnen",
  "history.current": "Aktuell",
  "history.prev": "Zurück",
  "history.next": "Weiter",
  "history.modal.subtitle":
    "Sieh dir alte Partien an, wechsle zwischen AI und Menschen und spring schnell zurück ins Spiel.",
  "queue.title": "Warte auf einen Gegner",
  "queue.body":
    "Deine Partie ist bereit. Sie startet, sobald ein anderer Spieler dazukommt.",
  "queue.leave": "Warteschlange verlassen",
  "queue.leaving": "Verlasse die Warteschlange...",
  "queue.error.dropped": "Die Echtzeitverbindung ist abgebrochen.",
  "queue.error.enter": "Der Warteraum konnte nicht betreten werden.",
  "queue.error.leave": "Die Warteschlange konnte nicht verlassen werden.",
  "draw.eyebrow": "Auslosung",
  "draw.title": "Wer die Partie eröffnet",
  "draw.subtitle":
    "Wer den Stein näher an A zieht, beginnt. Ein Blankostein gewinnt immer.",
  "draw.side.you": "Du",
  "draw.side.ai": "AI",
  "draw.pending": "Ziehe Steine aus dem Beutel...",
  "draw.blankCaption": "Blanko",
  "draw.result.youStart": "Du beginnst",
  "draw.result.aiStart": "Die AI beginnt",
  "draw.reason.blankYou": "Dein Blankostein gewinnt die Auslosung.",
  "draw.reason.blankAi": "Die AI hat den Blankostein gezogen.",
  "draw.reason.bothBlank": "Beide Steine sind Blankosteine, also beginnst du.",
  // `Passen` and `Tauschen` are different moves and stay different words.
  "controls.play": "Spielen",
  "controls.pass": "Passen",
  "controls.exchange": "Tauschen",
  "controls.confirmExchange": "Tausch bestätigen",
  "controls.cancel": "Abbrechen",
  "board.pts": "Pkt.",
  "board.pinchToZoom": "Zoom mit zwei Fingern",
  "board.dragToPan": "Ziehen zum Verschieben",
  "board.hide": "Ausblenden",
  "board.reset": "Reset",
  "rack.empty": "Keine Steine auf der Bank",
  "blank.chooseLetter": "Buchstabe für den Blankostein wählen",
  "chat.title": "Partie-Chat",
  "chat.empty": "Noch keine Nachrichten.",
  "chat.you": "Du",
  "chat.unavailable": "Chat nicht verfügbar",
  "chat.placeholder": "Schreib etwas",
  "chat.send": "Senden",
  "game.lexicon.collins2019": "Nicht in Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Nicht im slowakischen Lexikon",
  "game.lexicon.czech": "Nicht im tschechischen Lexikon",
  "game.lexicon.polish": "Nicht im polnischen Lexikon",
  // Eleven rows take the declined German language adjective. Afrikaans is the
  // exception: standard German has no established adjective for it, so that one
  // row takes the language name in a compound instead.
  "game.lexicon.afrikaans": "Nicht im Afrikaans-Lexikon",
  "game.lexicon.italian": "Nicht im italienischen Lexikon",
  "game.lexicon.dutch": "Nicht im niederländischen Lexikon",
  "game.lexicon.german": "Nicht im deutschen Lexikon",
  "game.lexicon.portuguese": "Nicht im portugiesischen Lexikon",
  "game.lexicon.danish": "Nicht im dänischen Lexikon",
  "game.lexicon.swedish": "Nicht im schwedischen Lexikon",
  "game.lexicon.icelandic": "Nicht im isländischen Lexikon",
  "game.lexicon.unknown": "Nicht im Spiellexikon",
  "game.blocker.auth.title": "Anmeldung des Gegners fehlgeschlagen",
  "game.blocker.auth.body":
    "Dieser kostenlose Gegner konnte sich nicht anmelden. Wechsle zu einem anderen kostenlosen Gegner oder versuche es später erneut.",
  "game.blocker.rate.title": "Gegner hat sein Limit erreicht",
  "game.blocker.rate.body":
    "Dieser kostenlose Gegner hat sein Limit erreicht. Wechsle zu einem anderen kostenlosen Gegner oder versuche es später erneut.",
  "game.blocker.unavail.title": "Gegner ist nicht verfügbar",
  "game.blocker.unavail.body":
    "Dieser kostenlose Gegner ist gerade nicht verfügbar. Wechsle zu einem anderen kostenlosen Gegner oder versuche es später erneut.",
  "game.blocker.badge.auth": "Anmeldung",
  "game.blocker.badge.rate": "Limit erreicht",
  "game.blocker.badge.unavail": "Nicht verfügbar",
  "game.blocker.close": "Schließen",
  "game.blocker.openSettings": "Einstellungen öffnen",
  "game.toast.invalidPlacement": "Ungültige Platzierung",
  "game.toast.invalidWords": "Ungültige Wörter",
  "game.toast.moveRejected": "Zug abgelehnt",
  "game.toast.exchangeRejected": "Tausch abgelehnt",
  "game.toast.passRejected": "Passen abgelehnt",
  "game.toast.chatOffline": "Chat ist offline",
  "game.toast.aiPasses": "Die AI passt",
  "game.toast.aiExchanged": "Die AI hat Steine getauscht",
  "game.toast.aiExchangedBody":
    "Die AI hat ihre Bank erneuert und den Zug verbraucht.",
  "game.toast.aiPassedBody": "Kein gültiger Zug gefunden – du bist am Zug!",
  // `game.aiPlayedFor.before` and `.points` render as `[before] {score} [points]`
  // with the score span FIXED in the middle, so no verb form can follow the number.
  // German perfect tense would put the participle after the score, which that call
  // site cannot express — hence the simple past `spielte` rather than `hat gespielt`.
  "game.aiPlayedFor.before": "Die AI spielte für",
  "game.aiPlayedFor.points": "Pkt.",
  "game.aWord": "ein Wort",
  "game.status.selectExchange": "Steine zum Tauschen wählen",
  "game.status.aiMoveReady": "AI-Zug ist bereit",
  "game.status.aiThinking": "Die AI denkt nach",
  "game.status.yourTurn": "Du bist am Zug",
  "game.status.waitingForAi": "Warte auf die AI",
  "game.opponentFallback": "Gegner",
  "game.waitingSlot": "Wartet",
  "game.sessionExpired": "Sitzung abgelaufen",
  "game.lastError": "Letzter Fehler:",
  "game.newGame": "Neue Partie",
  "game.starting": "Starte...",
  "game.victory": "Gewonnen!",
  "game.draw": "Unentschieden!",
  "game.gameOver": "Partie beendet",
  "game.giveUp.ai": "Diese Partie aufgeben? Die AI wird zum Sieger erklärt.",
  "game.giveUp.human":
    "Diese Partie aufgeben? Dein Gegner wird zum Sieger erklärt.",
  "game.gaveUp": "Du hast die Partie aufgegeben.",
  "game.error.giveUp": "Die Partie konnte nicht aufgegeben werden",
  "game.error.newGame": "Eine neue Partie konnte nicht gestartet werden",
  "game.error.loadGames": "Die Partien konnten nicht geladen werden.",
  "game.password.updated": "Passwort geändert.",
  "game.password.failed": "Das Passwort konnte nicht geändert werden.",
  "game.ai.noRival": "Es ist kein geeigneter kostenloser Gegner verfügbar.",
  "game.ai.timeout": "Die Denkzeit der AI ist abgelaufen.",
  "game.ai.moveFailed": "AI-Zug fehlgeschlagen",
  "game.ws.syncFailed": "Echtzeit-Sync fehlgeschlagen",
  "game.ws.connectFailed": "Echtzeitverbindung fehlgeschlagen",
  "game.ws.authExpired":
    "Die Anmeldung für die Echtzeitverbindung ist abgelaufen. Lade die Seite neu, um dich wieder zu verbinden.",
  "game.ws.invalidSession":
    "Diese Echtzeitsitzung ist nicht gültig. Lade die Seite neu, um dich wieder zu verbinden.",
  "game.ws.unavailable":
    "Der Echtzeitdienst ist nicht verfügbar. Versuche es erneut.",
  // `board.reset` and `board.zoomNoun` render in that order inside one button.
  // German wants the object first ("Zoom zurücksetzen"), which this two-span call
  // site cannot express, so the established German UI loanword `Reset` carries the
  // action and the noun follows it.
  "board.zoomNoun": "Zoom",
  "header.giveUp": "Aufgeben",
  "header.givingUp": "Gebe auf...",
  "header.giveUpTooltip": "Aktuelle Partie aufgeben",
  "header.logout": "Abmelden",
  "header.loggingOut": "Melde ab...",
  "header.backToBoards": "Zurück zu den Partien",
  "header.profile": "Profil",
  "header.games": "Partien",
  "overlay.aiThinking": "AI denkt nach",
  "overlay.searching": "Suche nach Zügen...",
  "overlay.best": "Bester Zug",
  // The badge is a very narrow pill next to a truncating word and a score, so it
  // takes the shortest standard German badge word rather than the full label.
  "overlay.bestBadge": "TOP",
  "overlay.filtering":
    "Filtere schwache und ungültige Züge heraus, bevor ein ernsthafter Zug erscheint...",
};

export const deFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Stein ${p.letter}, ${p.points} ` + pluralDe(p.points, "Punkt", "Punkte"),
  // Colon-labels, so no counted noun has to agree with an arbitrary count.
  "overlay.stats.tried": (p) => `Versucht: ${p.count}`,
  "overlay.stats.valid": (p) => `Gültig: ${p.count}`,
  "overlay.stats.rejected": (p) => `Verworfen: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Zu viele Anfragen. Versuche es in etwa ${p.minutes} ` +
    pluralDe(p.minutes, "Minute", "Minuten") +
    " erneut.",
  // `winner` and `loser` receive tile letters, never a person, so third person
  // singular agreement is correct here.
  "draw.reason.closer": (p) => `${p.winner} ist näher an A als ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralDe(p.count, "Stein", "Steine") + " ausgewählt",
  "game.ai.exploring": (p) => `Suche gültige Wörter mit ${p.model}...`,
  "game.ai.attempt": (p) => `Versuch ${p.index}/${p.total} · ${p.label}`,
  "game.toast.aiPlayedWord": (p) => `Die AI spielte ${p.word}`,
  "game.status.opponentPlaying": (p) => `${p.name} ist am Zug`,
  // Two full forms, never a suffix trick.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ungültige Wörter!" : "Ungültiges Wort!",
  "game.ai.routeFailed": (p) => `AI-Aufruf fehlgeschlagen (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `AI-Aufruf fehlgeschlagen (${p.status}), noch vor dem Start des Streams.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `AI-Aufruf fehlgeschlagen (${p.status}): ${p.preview}`,
  "play.humanQueue.queueFor": (p) => `Warteschlange: ${p.variant}`,
  "queue.room": (p) => `Raum ${p.code}`,
  "history.pageOf": (p) => `Seite ${p.page} von ${p.total}`,
  "history.showing": (p) => `Angezeigt: ${p.from}-${p.to} von ${p.total}`,
  "picker.flagAlt": (p) => `Flagge: ${p.language}`,
};
