// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralDa } from "./plural";

// Frozen DANISH game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile brik (en brik, brikken, brikker, brikkerne) · letter bogstav (et bogstav) ·
//   rack brikholder (en brikholder) · blank joker (en joker) · bag pose (en pose) ·
//   board = bræt (et bræt; the physical playing surface, stem `bræt-` in compounds) AND
//   parti (et parti; the metonym for a saved game) · pass pas (the game CALL, usable as a
//   noun; the verbal form is `melde pas`) · points point (et point, INVARIABLE in number) ·
//   rival = opponent modstander (en modstander).
//
// `bræt` really is two words. `bræt` is the surface a brik sits on; `parti` is the metonym for a
// stored game ("Gemte partier", "Tilbage til partier"), which is what Danish board-game usage
// says — "et parti skak". A third word stays apart from both: `spil` is the game as a product or
// ruleset, which is why the picker says `Spilvariant` and never `Partivariant`. `pas` and `bytte`
// are different moves and keep different words. tile and letter are NOT collapsed the way
// Icelandic collapses them: a `joker` is a brik carrying no bogstav that becomes one, so the
// piece and the character it carries need separate words. `tur` is the TURN and `træk` is the
// MOVE; those two are kept apart everywhere.
// THE PASS NOUN EXISTS HERE, unlike in Icelandic, Italian and Dutch. Danish game usage says
// "melde pas", and `pas` is the settled call in card and board games ("efter tre pas"), so a
// noun-shaped pass site needs no verbal rephrasing — see `game.toast.passRejected`. Two
// knock-ons: `et pas` is also a passport, which the neighbouring `Pas` button disambiguates, and
// the verb `passe` also means "to fit", so `error.conflict` says `strider mod` and never
// `passer ikke` — the same trap Icelandic reported.
//
// Register: informal `du` / `din` / `dit` / `dine`, error messages included. Never `De` / `Deres`.
// This cost nothing at all: Danish `De` is genuinely ARCHAIC rather than merely formal, so unlike
// German's `Sie` or Italian's `Lei` there was never a second usable register to weigh.
// Label style: IMPERATIVE for every control, action label, column heading and accessible name
// (Spil · Pas · Byt · Annuller · Log ud · Åbn · Søg · Send · Vælg · Nulstil). The control
// convention and the prose register COINCIDE in Danish rather than contrasting: the imperative is
// both what a Danish button says and what `du`-prose says (Vælg dit næste parti, Tjek de
// indtastede oplysninger, Prøv igen), so unlike Dutch this catalog never had to choose between an
// infinitive control form and a bare-stem prose form. Italian is the precedent, not Dutch.
// Pre-authorized exceptions used: the PAGINATION PAIR (`history.prev` / `history.next` are
// adjectives of the implied `side`), the TOGGLE STATE WORDS (`settings.toggle.on` / `.off`) and
// the BADGE WORDS (`settings.board.active`, `overlay.bestBadge`).
// Progress states take the present tense plus an ellipsis (Logger ind... · Logger ud... ·
// Starter... · Skifter...), which keeps `header.loggingOut` inside the non-wrapping header
// cluster.
//
// ORTHOGRAPHY. `æ ø å` are real UTF-8 everywhere and are never written `ae` / `oe` / `aa`.
// NO COMMON NOUN IS CAPITALIZED outside sentence-initial position — Danish is not German here,
// and a capitalized `Brik` or `Bræt` is the single most visible way this catalog could have gone
// wrong, because Danish is the language German is most often confused with orthographically.
// AND NO LANGUAGE NAME OR NATIONALITY WORD IS CAPITALIZED IN RUNNING TEXT either (`dansk`,
// `engelsk`, `tysk`), which is where Danish parts company with BOTH adjacent Germanic catalogs:
// German and Dutch capitalize them, Italian and Icelandic do not, and Danish sides with Italian
// and Icelandic. Standalone picker rows still take a capital — see `settings.gameVariant.*`.
// Compounds are written CLOSED, as one word: spilvariant, grænsefladesprog, adgangskode,
// brikholder, brætoverflade, betænkningstid, spillerkø. A compound on a foreign or acronym stem
// takes a hyphen instead: AI-modstander, AI-duel, premium-look, live-kø.
// The DEFINITE ARTICLE IS A SUFFIX and not a separate word, so every noun's gender and
// definiteness are baked into the word form: brikken / brættet / brikkerne. That is the reason no
// interpolated runtime value in this catalog ever carries a definite suffix or an agreeing
// adjective. The INDEFINITE article `en` / `et` is a separate word and therefore safe, which is
// why `game.aWord` can carry one.
// `AI` is a preserved product token and takes COMMON gender `en`, never `et`: its Danish head
// noun `(kunstig) intelligens` is an en-word. Danish writes the definite form of an abbreviation
// with an apostrophe, so "the AI" is `AI'en` and its genitive is `AI'ens` — which means this
// gender choice is visible in almost every AI string rather than only in an article, precisely
// because Danish marks definiteness as a suffix. Same rule for `GPU'en`.
// Thousands separator is a PERIOD (279.496), measured with Intl.NumberFormat("da").
//
// ⚠ SWEDISH IS CATALOG 7 AND MUST NOT REUSE THESE. Distinctively Danish forms, one line each:
//   · the game pieces and the bag — Danish `brik` / `brikker` / `brikkerne` and `pose`; the
//     Swedish words are built on different stems, so `brik` and `pose` are not transferable, and
//     Danish's definite plural `-ne` is not Swedish's.
//   · the alphabet — Danish `æ ø å` against Swedish `å ä ö`: `Vælg`, `Søg`, `Bekræft`, `bræt` and
//     `næste` contain letters a Swedish catalog must not carry at all.
//   · sign-out and the `-lig` trap — Danish `Log ud` is two short words where Swedish is not, and
//     Danish `tilgængelig` / `ugyldig` / `mulig` share their SUFFIX with Swedish while differing
//     in the stem, so a Swedish author who assumes `-lig` transfers gets the ending right and the
//     word wrong.
export const daText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  // Deliberately byte-identical: a preserved brand plus `premium`, an indeclinable loan modifier
  // that Danish places before the noun exactly as English does.
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "mennesker og AI.",
  "landing.lead":
    "Open source-ordspil med live-matchmaking, skarpe AI-modstandere, premium-brætgrafik og en historik, der er klar til dit næste parti.",
  "landing.card.ai.title": "AI-dueller",
  // `model` is TRANSLATED here, and for Danish that decision is INVISIBLE: the ordinary Danish
  // noun is `model` (en model), byte-identical to the protected token, so `modelvalg` is what the
  // translated and the untranslated reading both produce. The five `chat` sites keep the English
  // token, which is likewise the naturalized Danish word (at chatte, en chat) — so that decision
  // is not observable in the string either.
  "landing.card.ai.body": "Premium-partier med modelvalg",
  "landing.card.queue.title": "Live-kø",
  "landing.card.queue.body": "Synkronisering i realtid og chat",
  "landing.card.saved.title": "Gemte partier",
  "landing.card.saved.body": "Fortsæt partier mod AI eller mennesker",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279.496 gyldige ord",
  "auth.eyebrow": "Konto",
  // Danish sentence case collapses English's "Sign in" / "Sign In" pair into one string, so the
  // heading and the tab are deliberately identical rather than artificially distinguished.
  "auth.heading.login": "Log ind",
  "auth.heading.register": "Opret konto",
  "auth.tab.login": "Log ind",
  "auth.tab.register": "Registrer",
  "auth.field.username": "Brugernavn",
  "auth.field.password": "Adgangskode",
  "a11y.chatInput": "Chatbesked",
  "a11y.dialog.profile": "Profil",
  "a11y.dialog.games": "Gemte partier",
  "a11y.dialog.blank": "Vælg et bogstav",
  "a11y.dialog.rival": "Modstander ikke tilgængelig",
  // `tur` is the TURN and `træk` is the MOVE; this announcer names the turn.
  "a11y.status.turn": "Turstatus",
  "a11y.status.aiThinking": "AI-fremgang",
  "a11y.rackBlank": "Jokerbrik",
  "auth.submit.loading": "Logger ind...",
  "auth.submit.login": "Spil nu",
  "auth.submit.register": "Opret konto og spil",
  "meta.title": "Libre Tiles — ordspil på nettet med AI og live-multiplayer",
  "meta.description":
    "Open source-ordspil med AI-modstandere, live-partier mod mennesker, chat og glidende drag-and-drop.",
  "error.checkFields": "Tjek de indtastede oplysninger.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Brugernavn eller adgangskode er forkert",
  "error.sessionExpired": "Din session er udløbet. Log ind igen.",
  "error.forbidden": "Det har du ikke rettigheder til.",
  "error.notFound": "Blev ikke fundet.",
  // `strider mod` and not `passer ikke til`: `passe` is the frozen pass term and also means
  // "to fit", which is the same knock-on Icelandic reported for `passa`.
  "error.conflict": "Handlingen strider mod partiets aktuelle tilstand.",
  "error.throttled.unknown": "For mange forespørgsler. Vent lidt, og prøv igen.",
  "error.throttled.oneMinute":
    "For mange forespørgsler. Prøv igen om cirka et minut.",
  "error.unavailable": "Tjenesten er midlertidigt utilgængelig. Prøv igen.",
  "error.generic": "Noget gik galt. Prøv igen.",
  // `betænkningstid` is the settled Danish board-game word for thinking time. `AI'ens` is the
  // genitive of the definite `AI'en`, which is where the `en` gender choice becomes visible.
  "settings.timeout.title": "AI'ens betænkningstid",
  "settings.timeout.30": "Hurtigt blik på brættet",
  "settings.timeout.60": "Afbalanceret søgning",
  "settings.timeout.120": "Standardbetænkningstid",
  "settings.timeout.180": "Turneringstempo",
  "settings.timeout.300": "Længste betænkningstid",
  "settings.steps.title": "Søgetrin",
  "settings.steps.10": "Hurtige værktøjer",
  "settings.steps.20": "Flere forsøg",
  "settings.steps.30": "Fokuseret søgning",
  "settings.steps.50": "Standardsøgedybde",
  "settings.steps.80": "Maksimalt pres",
  "settings.board.title": "Brætoverflade",
  "settings.board.description":
    "Gemmes på denne enhed og bruges på spillebrættet.",
  "settings.board.wood": "Træ",
  "settings.board.woodDesc": "Klassisk valnøddeåring",
  "settings.board.black": "Sort",
  "settings.board.blackDesc": "Blank natlak",
  "settings.board.green": "Grøn",
  "settings.board.greenDesc": "Mørk turneringsfilt",
  // ⚠ THIS TRAP BITES DANISH, unlike Dutch and Italian. The badge is a sibling span of the
  // surface name (settings/page.tsx:218-220), and a Danish adjective inflects for gender:
  // `aktiv` for an en-word, `aktivt` for an et-word. The three surface labels are not one class —
  // `Træ` is a neuter noun while `Sort` and `Grøn` are colour words — and the implied head noun
  // is itself ambiguous between `et bræt` and `en overflade`. An invariable prepositional phrase
  // avoids the guess entirely and is the same length as the English it replaces.
  "settings.board.active": "I brug",
  // Toggle state words, not action labels: the pre-authorized exception to the imperative style.
  "settings.toggle.on": "Til",
  "settings.toggle.off": "Fra",
  "settings.shiny.title": "Glanseffekt",
  "settings.shiny.description":
    "Slå den levende glans fra, hvis du vil belaste GPU'en mindre.",
  "settings.shiny.onDesc": "Animeret glans på brættet",
  "settings.shiny.offDesc": "Lavere GPU-belastning",
  "settings.premium.title": "Premium-look",
  "settings.premium.description":
    "Interaktivt ravfarvet lys til partiets topbjælke og brikholderen.",
  "settings.premium.onDesc": "Interaktive premium-paneler",
  "settings.premium.offDesc": "Klassiske mørke flader",
  "settings.backToGame": "Tilbage til partiet",
  "settings.error.newGame": "Der kunne ikke startes et nyt parti lige nu.",
  "settings.warn.accountSync":
    "Kontosynkronisering er ikke tilgængelig lige nu. Indstillingerne virker fortsat lokalt på denne enhed.",
  "settings.warn.rivalRepair":
    "Der er valgt en gratis modstander på denne enhed. Præferencen på kontoen kunne endnu ikke repareres.",
  "settings.uiLanguage.title": "Grænsefladesprog",
  "settings.uiLanguage.description":
    "Menuer, knapper og meddelelser. Gælder med det samme og kun på denne enhed.",
  // Endonyms, identical in every catalog by project rule. Never Danish exonyms.
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
  "picker.search": "Søg",
  // `Ingen resultater` and not `Intet match`: `match` is a neuter loan in Danish, so the negative
  // determiner would have to be `intet`, and the plural noun phrase avoids that entirely.
  "picker.noMatch": "Ingen resultater",
  "picker.uiLanguageLabel": "Grænsefladesprog",
  "picker.gameVariantLabel": "Spilvariant",
  "settings.gameVariant.title": "Spilvariant",
  "settings.gameVariant.description":
    "Brikker, pose og ordliste. Gælder kun for NYE partier og ændrer aldrig et igangværende parti. Det er ikke grænsefladesproget.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED — but only because a picker row
  // is a standalone list item and therefore sentence-initial. Danish does NOT capitalize a
  // language name in itself, so the `game.lexicon.*` family below writes the same words lowercase.
  // That puts Danish in Italian's and Icelandic's position and not Dutch's.
  // Measured with Intl.DisplayNames("da") on node v26.4.0 / ICU 78.3, then checked as a set:
  // these twelve have ZERO case-insensitive substring collisions, so no variant label contains
  // another variant's name. `Afrikaans` is byte-identical to English because Danish has no
  // separate exonym for it; that is correct, not a missing translation. None of the twelve
  // contains `æ`, which matters because locales.ts's search fold cannot decompose `æ` while it
  // does fold `ø` and `å`.
  "settings.gameVariant.english": "Engelsk",
  "settings.gameVariant.slovak": "Slovakisk",
  "settings.gameVariant.czech": "Tjekkisk",
  "settings.gameVariant.polish": "Polsk",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italiensk",
  "settings.gameVariant.dutch": "Nederlandsk",
  "settings.gameVariant.german": "Tysk",
  "settings.gameVariant.portuguese": "Portugisisk",
  "settings.gameVariant.danish": "Dansk",
  "settings.gameVariant.swedish": "Svensk",
  "settings.gameVariant.icelandic": "Islandsk",
  "settings.rival.title": "Din modstander",
  "settings.rival.description":
    "Administratoren vælger modstanderen til nye partier.",
  "nav.settings": "Indstillinger",
  "nav.account": "Konto",
  // `ét` carries the acute accent Danish uses on stressed neuter `one`, against unstressed `et`.
  "profile.subtitle": "Kontooplysninger og adgangskodesikkerhed på ét sted.",
  "profile.email": "E-mail",
  "profile.noEmail": "Ingen e-mail angivet",
  // Composed as a label against a value that can degrade to `history.unknownDate`. The trap does
  // NOT bite Danish: `siden` is a bare preposition that governs its complement with no article,
  // no case and no definite suffix, so "Medlem siden Ukendt" is exactly as awkward as the English
  // original and no more so — pre-existing, not introduced here.
  "profile.memberSince": "Medlem siden",
  "profile.password.subtitle":
    "Skift din adgangskode uden at forlade partiet.",
  "profile.password.footnote":
    "Stærkere adgangskoder beskytter din konto bedre i partier mod mennesker.",
  "profile.field.current": "Nuværende adgangskode",
  "profile.field.new": "Ny adgangskode",
  "profile.field.confirm": "Bekræft ny adgangskode",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Nuværende adgangskode",
  // `tegn` and not `bogstaver`: here the English `characters` means text characters, and `bogstav`
  // is this catalog's frozen word for what a brik carries.
  "profile.ph.new": "Mindst 8 tegn",
  "profile.ph.confirm": "Gentag den nye adgangskode",
  "profile.submit": "Skift adgangskode",
  "profile.submitting": "Skifter...",
  "profile.error.allFields": "Udfyld alle felter til adgangskoden.",
  "profile.error.mismatch": "De nye adgangskoder er ikke ens.",
  "play.title": "Vælg dit næste parti",
  "play.lead":
    "Start en premium-duel mod AI'en, hop ind i live-køen, eller åbn et af dine gemte partier.",
  "play.ai.eyebrow": "Parti mod AI",
  "play.ai.title": "Spil mod AI'en",
  "play.ai.body":
    "Spil mod den aktuelle AI-modstander, med den animerede åbningstrækning.",
  "play.ai.preparing": "Forbereder parti...",
  "play.rival.unavailable": "Ingen modstander tilgængelig",
  "play.humanQueue.eyebrow": "Spillerkø",
  "play.humanQueue.title": "Find en live-modstander",
  "play.humanQueue.body":
    "Slut dig til den første spiller, der venter. Er der ingen, venter dit parti i venterummet.",
  "play.humanQueue.joining": "Går ind i køen...",
  "play.saved.eyebrow": "Gemte partier",
  "play.saved.title": "Fortsæt, hvor du slap",
  // `én` carries the acute accent Danish uses on stressed common-gender `one`.
  "play.saved.note": "Partier mod AI og mod mennesker deler én fælles historik.",
  "play.error.catalogEmpty":
    "Modstanderkataloget er tomt. Fyld det gratis katalog, så partier mod AI kan spilles.",
  "play.error.catalogUnavailable":
    "Modstanderkataloget er ikke tilgængeligt lige nu. Prøv igen om et øjeblik.",
  "play.error.variantUnavailable":
    "Der er ingen spilbar spilvariant tilgængelig. Nye partier er blokeret, indtil en spilbar variant kan indlæses.",
  "play.error.startAi": "Partiet mod AI kunne ikke startes.",
  "play.error.joinQueue": "Du kunne ikke komme ind i spillerkøen.",
  "play.error.loadGames": "Dine partier kunne ikke indlæses.",
  "history.filter.ai": "AI",
  "history.filter.human": "Mennesker",
  "history.filter.all": "Alle",
  "history.sort.recent": "Nyeste",
  "history.refresh": "Opdater",
  "history.loading": "Indlæser partier",
  "history.empty.title": "Der er endnu ingen partier i dette filter",
  "history.empty.body":
    "Start et nyt parti, og det vises her med premium-sideskift, resultatmærker og hurtige links til at spille videre.",
  "history.noneYet": "Endnu ingen gemte partier",
  // Its name lies about its scope. Measured at four call sites: GameHistoryPanel.tsx:97 and both
  // uses inside `formatJoinedDate` (ProfileModal.tsx:23 and :26) are a missing DATE, and only
  // ProfileModal.tsx:220 is a missing USERNAME. Danish escapes this for a purely morphological
  // reason: `ukendt` already ends in -t, so its indefinite common and neuter singular forms are
  // IDENTICAL, and one form is therefore correct for both `en dato` and `et brugernavn`.
  // Splitting the key would be a `messages.en.ts` change and is not in this slice.
  "history.unknownDate": "Ukendt",
  "history.col.rival": "Modstander",
  // `Type` is byte-identical to English and is nonetheless ordinary Danish (en type). This column
  // holds a category (AI-duel / Duel mod mennesker), which is what a Danish table calls a type.
  "history.col.mode": "Type",
  "history.col.result": "Resultat",
  // `Score` is byte-identical to English and is the naturalized Danish noun (en score).
  "history.col.score": "Score",
  "history.col.moves": "Træk",
  "history.col.updated": "Opdateret",
  // The eight outcome badges read against `parti` in the row and against the column heading
  // `Resultat` in the header. That trap does not bite Danish, twice over: both nouns are NEUTER,
  // so even an agreeing form would be consistent across the two call sites; and every value here
  // is either a fixed phrase or a past participle in -t/-et, whose form is identical to the
  // neuter singular and is exactly what a Danish results table uses as an unmarked result label.
  "history.outcome.waiting": "Venter",
  "history.outcome.active": "I gang",
  "history.outcome.won": "Vundet",
  "history.outcome.lost": "Tabt",
  "history.outcome.draw": "Uafgjort",
  "history.outcome.gaveUp": "Opgivet",
  "history.outcome.abandoned": "Forladt",
  // DEAD KEY: `OUTCOME_META` at GameHistoryPanel.tsx:36-75 has exactly seven arms and no
  // `unknown`, so the product cannot render this. The value is correct and no further agreement
  // effort is spent on it. Its removal belongs to a later slice.
  "history.outcome.unknown": "Ukendt",
  "history.mode.ai": "AI-duel",
  "history.mode.human": "Duel mod mennesker",
  "history.hint.waitingRoom": "Venterum",
  "history.hint.boardReady": "Partiet er klar",
  // `pose` and `brikholder` are both COMMON gender, so the shared predicate simply takes the
  // plural `tomme` and no mixed-gender problem arises — unlike Icelandic, where the two nouns
  // differ in gender and force a neuter.
  "history.endReason.bagEmpty": "Pose og brikholder tomme",
  "history.endReason.noMoves": "Ingen mulige træk",
  "history.endReason.sixZero": "Seks træk uden point",
  "history.endReason.gaveUp": "Partiet opgivet",
  "history.endReason.queueCancelled": "Køen annulleret",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139, where it
  // alternates in the same slot with `history.current`. The Danish imperative works in both roles,
  // so that fixed call site costs nothing.
  "history.open": "Åbn",
  // Its partner did cost something. `aktuel` / `aktuelt` inflects for gender and the implied noun
  // here is the NEUTER `parti`, so the agreeing form would have to be `Aktuelt`. `Nuværende` is a
  // participle-derived adjective that is indeclinable in every gender, number and definiteness,
  // so nothing agrees with anything.
  "history.current": "Nuværende",
  // Pagination is a pair of adjectives of the implied `side`, so these two are the one place the
  // imperative label style would be wrong.
  "history.prev": "Forrige",
  "history.next": "Næste",
  "history.modal.subtitle":
    "Se gamle partier, skift mellem AI og mennesker, og hop hurtigt tilbage i spillet.",
  "queue.title": "Venter på en modstander",
  "queue.body":
    "Dit parti er klar. Det starter, så snart en anden spiller kommer til.",
  "queue.leave": "Forlad køen",
  "queue.leaving": "Forlader køen...",
  "queue.error.dropped": "Realtidsforbindelsen blev afbrudt.",
  "queue.error.enter": "Du kunne ikke komme ind i venterummet.",
  "queue.error.leave": "Køen kunne ikke forlades.",
  "draw.eyebrow": "Åbningstrækning",
  "draw.title": "Hvem åbner partiet",
  // `tættest` is a superlative on a brik that is fixed at author time, not a runtime value. The
  // interpolated variant of this sentence is `draw.reason.closer`.
  "draw.subtitle":
    "Den, der trækker brikken tættest på A, begynder. En joker vinder altid.",
  "draw.side.you": "Dig",
  "draw.side.ai": "AI",
  "draw.pending": "Trækker brikker fra posen...",
  "draw.blankCaption": "joker",
  "draw.result.youStart": "Du begynder",
  "draw.result.aiStart": "AI'en begynder",
  "draw.reason.blankYou": "Din joker vinder trækningen.",
  "draw.reason.blankAi": "AI'en trak jokeren.",
  "draw.reason.bothBlank": "Begge brikker er jokere, så du begynder.",
  "controls.play": "Spil",
  // `Pas` is the Danish game call, three characters, and it is the frozen pass term.
  "controls.pass": "Pas",
  "controls.exchange": "Byt",
  "controls.confirmExchange": "Bekræft bytte",
  "controls.cancel": "Annuller",
  // Rendered under a CSS `uppercase` class on the board (Board.tsx:652-653) and as a bare label in
  // the AI overlay (AIThinkingOverlay.tsx:113, :314), so the value stays lowercase. It is the SAME
  // word as `game.aiPlayedFor.points`: Danish `point` is already five characters and is not
  // abbreviated in running UI text, so there is no shorter honest form to reach for.
  "board.pts": "point",
  // On-board instructions on the tightest text surface in the product. Both are longer than the
  // English they replace; the shortest correct Danish is kept and the overflow is reported.
  "board.pinchToZoom": "Knib for at zoome",
  "board.dragToPan": "Træk for at flytte",
  "board.hide": "Skjul",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in the fixed order
  // [action][noun] at Board.tsx:692-693. That call site does NOT bite Danish: the Danish
  // imperative takes its object after it, so "Nulstil zoom" is correct in exactly the order the
  // spans impose. German had to reach for the loanword `Reset` and Dutch had to abandon its
  // infinitive control style to get here; Danish needs neither, because the imperative is already
  // this catalog's control form.
  "board.reset": "Nulstil",
  "rack.empty": "Ingen brikker i brikholderen",
  "blank.chooseLetter": "Vælg et bogstav til jokeren",
  "chat.title": "Partichat",
  "chat.empty": "Endnu ingen beskeder.",
  "chat.you": "Dig",
  "chat.unavailable": "Chat ikke tilgængelig",
  "chat.placeholder": "Skriv noget",
  // Byte-identical to English and correct Danish: the imperative of `sende` is `send`.
  "chat.send": "Send",
  "game.lexicon.collins2019": "Ikke i Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Ikke i den slovakiske ordliste",
  "game.lexicon.czech": "Ikke i den tjekkiske ordliste",
  "game.lexicon.polish": "Ikke i den polske ordliste",
  // Ten rows take the language adjective in its definite form, which in Danish is `-e` for EVERY
  // gender and number, so agreement with `ordliste` is free and the two families stay consistent
  // apart from case: these are lowercase because Danish writes a language word lowercase in
  // running text, while the picker rows above take a capital. `afrikaans` is the one exception:
  // Danish has no established adjective built on it, so that row carries the bare language name
  // after a preposition rather than an invented `*afrikaanske`. German and Portuguese made the
  // same exception by their own mechanisms.
  "game.lexicon.afrikaans": "Ikke i ordlisten for afrikaans",
  "game.lexicon.italian": "Ikke i den italienske ordliste",
  "game.lexicon.dutch": "Ikke i den nederlandske ordliste",
  "game.lexicon.german": "Ikke i den tyske ordliste",
  "game.lexicon.portuguese": "Ikke i den portugisiske ordliste",
  "game.lexicon.danish": "Ikke i den danske ordliste",
  "game.lexicon.swedish": "Ikke i den svenske ordliste",
  "game.lexicon.icelandic": "Ikke i den islandske ordliste",
  "game.lexicon.unknown": "Ikke i spillets ordliste",
  "game.blocker.auth.title": "Godkendelse af modstanderen mislykkedes",
  "game.blocker.auth.body":
    "Denne gratis modstander kunne ikke godkendes. Skift til en anden gratis modstander, eller prøv igen senere.",
  "game.blocker.rate.title": "Modstanderen har nået sin grænse",
  "game.blocker.rate.body":
    "Denne gratis modstander har nået sin grænse for forespørgsler. Skift til en anden gratis modstander, eller prøv igen senere.",
  "game.blocker.unavail.title": "Modstanderen er ikke tilgængelig",
  "game.blocker.unavail.body":
    "Denne gratis modstander er midlertidigt utilgængelig. Skift til en anden gratis modstander, eller prøv igen senere.",
  "game.blocker.badge.auth": "Godkendelse",
  "game.blocker.badge.rate": "Grænse nået",
  "game.blocker.badge.unavail": "Utilgængelig",
  "game.blocker.close": "Luk",
  "game.blocker.openSettings": "Åbn indstillinger",
  "game.toast.invalidPlacement": "Ugyldig placering",
  "game.toast.invalidWords": "Ugyldige ord",
  "game.toast.moveRejected": "Træk afvist",
  "game.toast.exchangeRejected": "Bytte afvist",
  // No verbal rephrasing is needed here, unlike in Icelandic, Italian and Dutch: `pas` is a real
  // Danish game noun, and the neighbouring `Pas` button removes the passport reading.
  "game.toast.passRejected": "Pas afvist",
  // Almost byte-identical to English, and correct Danish: `chat` and `offline` are both
  // naturalized, so this is the clearest case where the protected-token decision is invisible.
  "game.toast.chatOffline": "Chat er offline",
  "game.toast.aiPasses": "AI'en melder pas",
  "game.toast.aiExchanged": "AI'en byttede brikker",
  "game.toast.aiExchangedBody": "AI'en fornyede sin brikholder og brugte turen.",
  "game.toast.aiPassedBody": "Fandt ikke et gyldigt træk — det er din tur!",
  // ⚠ THE NAMED CALL SITE, AND IT DOES NOT BITE DANISH. page.tsx:338 composes
  // `[before] <span>{score}</span> [points]` with the score FIXED in the middle and nothing after
  // the counted noun. German and Dutch both had to abandon the perfect tense here because their
  // verb phrase is FINAL — the participle would land after the number. Danish is Mainland
  // Scandinavian and is NOT verb-final in its verb phrase: the participle stands immediately
  // after the auxiliary and BEFORE its object, so "AI'en har scoret 34 point" fits the two spans
  // exactly as written, and the perfect tense survives with no register downgrade.
  // `game.toast.aiPlayedWord` is kept in the same tense so the one toast is consistent.
  "game.aiPlayedFor.before": "AI'en har scoret",
  "game.aiPlayedFor.points": "point",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation at page.tsx:1003. Danish's
  // INDEFINITE article is a separate word — only the definite article is a suffix — so it can be
  // carried here safely: the fallback reads "AI'en har spillet et ord" while a real word reads
  // "AI'en har spillet KAGE", and Danish needs no article before a bare cited word. `ord` is
  // neuter, hence `et`.
  "game.aWord": "et ord",
  "game.status.selectExchange": "Vælg brikker, der skal byttes",
  "game.status.aiMoveReady": "AI'ens træk er klar",
  "game.status.aiThinking": "AI'en tænker",
  "game.status.yourTurn": "Din tur",
  "game.status.waitingForAi": "Venter på AI'en",
  "game.opponentFallback": "Modstander",
  "game.waitingSlot": "Venter",
  "game.sessionExpired": "Sessionen er udløbet",
  "game.lastError": "Seneste fejl:",
  "game.newGame": "Nyt parti",
  "game.starting": "Starter...",
  "game.victory": "Du vandt!",
  "game.draw": "Uafgjort!",
  "game.gameOver": "Partiet er slut",
  // Rendered by `window.confirm` at page.tsx:671, so these two carry no markup and no styling.
  "game.giveUp.ai": "Vil du opgive dette parti? AI'en bliver erklæret som vinder.",
  "game.giveUp.human":
    "Vil du opgive dette parti? Din modstander bliver erklæret som vinder.",
  // Italian needed `avere` plus an invariable object here because a reflexive participle agrees
  // with the SUBJECT. Danish builds its perfect with `have` and its participle never agrees with
  // anything, so `har opgivet` needs no gender and this trap does not bite. The definite suffix on
  // `partiet` is safe because that noun is fixed at author time, not interpolated.
  "game.gaveUp": "Du har opgivet partiet.",
  "game.error.giveUp": "Partiet kunne ikke opgives",
  "game.error.newGame": "Der kunne ikke startes et nyt parti",
  "game.error.loadGames": "Partierne kunne ikke indlæses.",
  "game.password.updated": "Adgangskoden er skiftet.",
  "game.password.failed": "Adgangskoden kunne ikke skiftes.",
  "game.ai.noRival": "Der er ingen egnet gratis modstander tilgængelig.",
  "game.ai.timeout": "AI'ens betænkningstid er udløbet.",
  "game.ai.moveFailed": "AI'ens træk mislykkedes",
  "game.ws.syncFailed": "Realtidssynkronisering mislykkedes",
  "game.ws.connectFailed": "Realtidsforbindelsen mislykkedes",
  "game.ws.authExpired":
    "Godkendelsen til realtid er udløbet. Genindlæs siden for at oprette forbindelse igen.",
  "game.ws.invalidSession":
    "Denne realtidssession er ikke gyldig. Genindlæs siden for at oprette forbindelse igen.",
  "game.ws.unavailable": "Realtidstjenesten er ikke tilgængelig. Prøv igen.",
  // Lowercase: Danish does not capitalize a common noun, and `zoom` is an ordinary loan (et zoom).
  "board.zoomNoun": "zoom",
  "header.giveUp": "Opgiv",
  "header.givingUp": "Opgiver...",
  "header.giveUpTooltip": "Opgiv det aktuelle parti",
  // Six characters in a non-wrapping header cluster, tying English and beating every other
  // catalog except Italian's four — and its in-place replacement `header.loggingOut` is twelve
  // against English's fourteen, so the swap costs the cluster nothing either.
  "header.logout": "Log ud",
  "header.loggingOut": "Logger ud...",
  "header.backToBoards": "Tilbage til partier",
  "header.profile": "Profil",
  "header.games": "Partier",
  "overlay.aiThinking": "AI tænker",
  "overlay.searching": "Søger efter træk...",
  // Deliberately DIVERGES from `overlay.bestBadge` below, the way de, is and nl diverge: this is a
  // label with room for the noun, that one is a 10px pill.
  "overlay.best": "Bedste træk",
  // A very narrow pill beside a truncating word and a score. Five characters, the predicative
  // superlative rather than the attributive `BEDSTE`, and it cannot be mistaken for untranslated
  // English because Danish spells it with a d.
  "overlay.bestBadge": "BEDST",
  "overlay.filtering":
    "Filtrerer svage og ugyldige træk fra, før et seriøst træk vises...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, two slots each, so this catalog has SIX slot fillers
// and every one of them is a PURE NOUN rather than a phrase. CLDR da selects `one` only at exactly
// 1 and `other` for everything else INCLUDING ZERO — measured on node v26.4.0 / ICU 78.3 and
// pinned by plural.test.ts — so Danish writes "0 point" and never the "0 ponto" that CLDR
// Portuguese produces next door.
//   point noun   point / point — Danish `point` (et point) is INVARIABLE in number: "1 point",
//                "5 point", "34 point". The two slots therefore carry the SAME word, as Icelandic
//                `stig` does. That is the language, not an oversight: do not invent a second form
//                to make the slots look distinct.
//   minute noun  minut / minutter — et minut, ordinary neuter plural in -er.
//   tile noun    brik / brikker — and NOT the phrase Icelandic and Italian needed. The predicate
//                participle `valgt` already ends in -t, so its common and neuter singular forms
//                are identical, and Danish keeps the uninflected form in this verbless label for
//                the plural too. `valgt` is therefore appended OUTSIDE the helper the way German
//                appends `ausgewählt`, and the slot stays a bare noun.
// `pluralDa` is called and never `pluralEn`: the two agree over the integers but CLDR da selects
// `one` for 0.5 and 1.5 while en does not, which is why the helper exists separately.
export const daFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Brik ${p.letter}, ${p.points} ` + pluralDa(p.points, "point", "point"),
  // Colon-labels in the invariable citation form, so nothing has to agree with an arbitrary count.
  "overlay.stats.tried": (p) => `Prøvet: ${p.count}`,
  "overlay.stats.valid": (p) => `Gyldig: ${p.count}`,
  "overlay.stats.rejected": (p) => `Afvist: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `For mange forespørgsler. Prøv igen om cirka ${p.minutes} ` +
    pluralDa(p.minutes, "minut", "minutter") +
    ".",
  // `winner` and `loser` receive TILE LETTERS, never a person (draw-result.ts:29-30). `er` is an
  // invariable third-person verb and `tættere` an invariable comparative, so neither opaque value
  // takes an article, a definite suffix or an agreeing adjective.
  "draw.reason.closer": (p) => `${p.winner} er tættere på A end ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralDa(p.count, "brik", "brikker") + " valgt",
  // `model` is an opaque runtime id, so `med` carries it with no article before it.
  "game.ai.exploring": (p) => `Søger gyldige ord med ${p.model}...`,
  "game.ai.attempt": (p) => `Forsøg ${p.index}/${p.total} · ${p.label}`,
  // Perfect tense, matching `game.aiPlayedFor.before` in the same toast.
  "game.toast.aiPlayedWord": (p) => `AI'en har spillet ${p.word}`,
  // `name` is an opaque runtime value, so the predicate is a finite verb with no article, no
  // definite suffix and nothing to agree with. `nu` is there to force the verb reading: bare
  // `spiller` is also the Danish noun for a player.
  "game.status.opponentPlaying": (p) => `${p.name} spiller nu`,
  // Two full forms, never a suffix trick. The NOUN is invariable here — `ord` is the same in both
  // numbers — so only the adjective marks number: `ugyldigt` in the indefinite neuter singular,
  // `ugyldige` in the plural.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ugyldige ord!" : "Ugyldigt ord!",
  "game.ai.routeFailed": (p) => `AI-kaldet mislykkedes (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `AI-kaldet mislykkedes (${p.status}), før streamen begyndte.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `AI-kaldet mislykkedes (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, and a Danish definite suffix on a value
  // whose en/et class is unknown would be a guess.
  "play.humanQueue.queueFor": (p) => `Kø: ${p.variant}`,
  "queue.room": (p) => `Rum ${p.code}`,
  "history.pageOf": (p) => `Side ${p.page} af ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `Viser: ${p.from}-${p.to} af ${p.total}`,
  // Colon form for the same reason as `play.humanQueue.queueFor`: `language` is opaque.
  "picker.flagAlt": (p) => `Flag: ${p.language}`,
};
