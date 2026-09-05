// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralNl } from "./plural";

// Frozen DUTCH game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile tegel (de) · letter letter (de) · rack letterbak (de) · blank joker (de) ·
//   bag zak (de) · board = bord (het; the physical playing surface) AND partij (de; a saved
//   game) · pass passen (a VERB, and its own verbal noun) · points punten (het punt),
//   abbreviated ptn · rival = opponent tegenstander (de).
//
// `bord` really is two words. `bord` is the surface a tegel sits on; `partij` is the metonym for
// a stored game ("Opgeslagen partijen", "Terug naar partijen"), which is what Dutch board-game
// usage says — "een partij schaak". A third word stays apart from both: `spel` is the game as a
// product or ruleset, which is why the picker says `Spelvariant` and never `Partijvariant`.
// `passen` and `ruilen` are different moves and keep different words. tile and letter are NOT
// collapsed the way Icelandic collapses them: a `joker` is a tegel carrying no letter that
// becomes one, so the piece and the character it carries need separate words.
// `tegel` and not `steen`: `steen` is real Dutch, but it is the exact cognate of catalog 1's
// frozen German `Stein`, and D6 forbids harmonizing terminology across languages.
// PASS HAS NO USABLE NOUN here either, the way Icelandic `passi` is a passport and Italian
// `passo` is a step: Dutch `een pas` is a step or a pass card. Dutch still needs no verbal
// rephrasing, because the infinitive IS the verbal noun — see `game.toast.passRejected`.
// `turn` is `beurt` and `move` is `zet`; those two are kept apart everywhere.
//
// Register: informal `je` / `jij` / `jouw`, error messages included. Never `u` / `uw`, and the
// two systems are never mixed. `jij` and `jouw` appear only where they carry contrast ("Jij
// begint", "Jouw joker wint de trekking"); `je` everywhere else.
// Label style: INFINITIVE for every control, action label, column heading and accessible name
// (Spelen · Passen · Ruilen · Annuleren · Uitloggen · Openen · Zoeken · Verzenden); the `je`
// IMPERATIVE only for prose sentences, hero headings and on-board instructions (Kies je volgende
// partij, Controleer de ingevulde gegevens, Knijp om te zoomen). Never mixed inside one strip.
// The two CONTRAST in Dutch rather than coinciding: the conventional Dutch control form is the
// infinitive (Annuleren, Opslaan, Vernieuwen) while the informal prose imperative is the bare
// stem (Kies, Controleer, Probeer), so unlike Italian this catalog had to choose between them.
// Pre-authorized exceptions used: the PAGINATION PAIR (`history.prev` / `history.next` are
// adjectives of the implied `pagina`), the TOGGLE STATE WORDS (`settings.toggle.on` / `.off`) and
// the BADGE WORDS (`settings.board.active`, `overlay.bestBadge`). One further exception is not
// pre-authorized and is forced by a fixed call site: see `board.reset`.
// Progress states take the bare infinitive plus an ellipsis (Inloggen... · Uitloggen... ·
// Starten... · Wijzigen...) rather than the longer "Bezig met ...", which would overflow the
// non-wrapping header cluster at `header.loggingOut`.
//
// ORTHOGRAPHY. Compounds are written CLOSED, as one word: spelvariant, interfacetaal,
// wachtwoord, letterbak, beurtstatus, spelerswachtrij. A compound on an acronym stem takes a
// hyphen instead: AI-tegenstander, AI-duel, AI-voortgang. NO COMMON NOUN IS CAPITALIZED outside
// sentence-initial position — Dutch is not German here, and a capitalized `Tegel` or `Bord` is
// the single most visible way this catalog could have gone wrong. The opposite half of the same
// rule: Dutch DOES capitalize language names and nationality adjectives, in a standalone picker
// row and in running text alike, so `Nederlands` and `het Nederlandse lexicon` both keep their
// capital where Italian and Icelandic lowercase theirs.
// `ij` is always two plain letters, and `IJ` capitalizes BOTH of them (IJslands, IJslandse). The
// ligature `ĳ` / `Ĳ` never appears: modern orthography does not use it, and locales.ts's search
// fold cannot decompose it, so a ligature in a picker label would be unsearchable.
// `AI` is a preserved product token and takes `de`, never `het`: its Dutch head noun
// `(kunstmatige) intelligentie` is a de-word, and Dutch assigns `de` to loan acronyms by
// default. Dutch has no gender agreement on predicate nouns or participles, so that choice is
// visible only in the article itself ("De AI wordt tot winnaar uitgeroepen").
// Thousands separator is a PERIOD (279.496), measured with Intl.NumberFormat("nl").
export const nlText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  // Deliberately byte-identical: a preserved brand plus `premium`, an indeclinable loan modifier
  // that Dutch places before the noun exactly as English does.
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "mensen en AI.",
  "landing.lead":
    "Open-source woordspel met koppelen in realtime, scherpe AI-tegenstanders, premium bordafwerking en een overzicht dat klaarstaat voor je volgende partij.",
  "landing.card.ai.title": "AI-duels",
  // `model` is TRANSLATED here, and for Dutch that decision is invisible: the ordinary Dutch
  // noun is `model` (het model), byte-identical to the protected token. The five `chat` sites
  // keep the English token, which is likewise the naturalized Dutch word (chatten, de chat).
  "landing.card.ai.body": "Premiumpartijen met modelkeuze",
  "landing.card.queue.title": "Live wachtrij",
  "landing.card.queue.body": "Synchronisatie in realtime en chat",
  "landing.card.saved.title": "Opgeslagen partijen",
  "landing.card.saved.body": "Partijen tegen AI of mensen voortzetten",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279.496 geldige woorden",
  // `Account` is byte-identical to English at both this eyebrow and `nav.account`, and it is the
  // ordinary Dutch noun (het account) — the same naturalization as `chat` documented above.
  "auth.eyebrow": "Account",
  // Dutch sentence case collapses English's "Sign in" / "Sign In" pair into one string, so the
  // heading and the tab are deliberately identical rather than artificially distinguished.
  "auth.heading.login": "Inloggen",
  "auth.heading.register": "Account aanmaken",
  "auth.tab.login": "Inloggen",
  "auth.tab.register": "Registreren",
  "auth.field.username": "Gebruikersnaam",
  "auth.field.password": "Wachtwoord",
  "a11y.chatInput": "Chatbericht",
  "a11y.dialog.profile": "Profiel",
  "a11y.dialog.games": "Opgeslagen partijen",
  "a11y.dialog.blank": "Letter kiezen",
  "a11y.dialog.rival": "Tegenstander niet beschikbaar",
  "a11y.status.turn": "Beurtstatus",
  "a11y.status.aiThinking": "AI-voortgang",
  "a11y.rackBlank": "Jokertegel",
  "auth.submit.loading": "Inloggen...",
  "auth.submit.login": "Nu spelen",
  "auth.submit.register": "Account aanmaken en spelen",
  "meta.title":
    "Libre Tiles — woordspel op het web met AI en live multiplayer",
  "meta.description":
    "Open-source woordspel met AI-tegenstanders, live partijen tegen mensen, chat en soepele drag-and-drop.",
  "error.checkFields": "Controleer de ingevulde gegevens.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Gebruikersnaam of wachtwoord is onjuist",
  "error.sessionExpired": "Je sessie is verlopen. Log opnieuw in.",
  "error.forbidden": "Daar heb je geen rechten voor.",
  "error.notFound": "Niet gevonden.",
  "error.conflict": "Deze actie past niet bij de huidige stand van de partij.",
  "error.throttled.unknown":
    "Te veel verzoeken. Wacht even en probeer het opnieuw.",
  "error.throttled.oneMinute":
    "Te veel verzoeken. Probeer het over ongeveer een minuut opnieuw.",
  "error.unavailable":
    "De dienst is tijdelijk niet beschikbaar. Probeer het opnieuw.",
  "error.generic": "Er is iets misgegaan. Probeer het opnieuw.",
  "settings.timeout.title": "Denktijd van de AI",
  "settings.timeout.30": "Snelle blik op het bord",
  "settings.timeout.60": "Evenwichtig zoeken",
  "settings.timeout.120": "Standaard denktijd",
  "settings.timeout.180": "Toernooitempo",
  "settings.timeout.300": "Langste denktijd",
  "settings.steps.title": "Zoekstappen",
  "settings.steps.10": "Snelle tools",
  "settings.steps.20": "Meer pogingen",
  "settings.steps.30": "Gericht zoeken",
  "settings.steps.50": "Standaard zoekdiepte",
  "settings.steps.80": "Maximale druk",
  "settings.board.title": "Bordoppervlak",
  "settings.board.description":
    "Wordt op dit apparaat opgeslagen en op het bord gebruikt.",
  "settings.board.wood": "Hout",
  "settings.board.woodDesc": "Klassiek notenhout",
  "settings.board.black": "Zwart",
  "settings.board.blackDesc": "Glanzende nachtlak",
  "settings.board.green": "Groen",
  "settings.board.greenDesc": "Donker toernooivilt",
  // The trap the other catalogs met does NOT bite Dutch. The badge is a sibling span of the
  // surface name (settings/page.tsx:218-220), never attributive to it, and a Dutch predicate or
  // standalone adjective has exactly ONE form — so `Actief` is already invariable and stays
  // correct beside the noun `Hout` (het) and beside the adjectives `Zwart` and `Groen` alike.
  // No invariable phrase was needed, unlike Portuguese and Icelandic.
  "settings.board.active": "Actief",
  // Toggle state words, not action labels: the pre-authorized exception to the infinitive style.
  "settings.toggle.on": "Aan",
  "settings.toggle.off": "Uit",
  "settings.shiny.title": "Glanseffect",
  "settings.shiny.description":
    "Zet de levende glans uit als je de GPU wilt ontzien.",
  "settings.shiny.onDesc": "Bewegende glans op het bord",
  "settings.shiny.offDesc": "Lagere GPU-belasting",
  "settings.premium.title": "Premiumlook",
  "settings.premium.description":
    "Interactief amberkleurig licht voor de kop van de partij en de letterbak.",
  "settings.premium.onDesc": "Interactieve premiumpanelen",
  "settings.premium.offDesc": "Klassieke donkere vlakken",
  "settings.backToGame": "Terug naar de partij",
  "settings.error.newGame": "Er kon nu geen nieuwe partij worden gestart.",
  "settings.warn.accountSync":
    "De accountsynchronisatie is nu niet beschikbaar. De instellingen werken nog wel lokaal op dit apparaat.",
  "settings.warn.rivalRepair":
    "Op dit apparaat is een gratis tegenstander gekozen. De voorkeur in je account kon nog niet worden hersteld.",
  "settings.uiLanguage.title": "Interfacetaal",
  "settings.uiLanguage.description":
    "Menu's, knoppen en meldingen. Geldt direct en alleen op dit apparaat.",
  // Endonyms, identical in every catalog by project rule. Never Dutch exonyms.
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
  "picker.search": "Zoeken",
  "picker.noMatch": "Geen resultaat",
  "picker.uiLanguageLabel": "Interfacetaal",
  "picker.gameVariantLabel": "Spelvariant",
  "settings.gameVariant.title": "Spelvariant",
  "settings.gameVariant.description":
    "Tegels, zak en lexicon. Geldt alleen voor NIEUWE partijen en verandert een lopende partij nooit. Dit is niet de interfacetaal.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED — but not because they are
  // standalone picker rows. Dutch capitalizes a language name and a nationality adjective
  // everywhere, so the `game.lexicon.*` family below keeps the capital in running text too. That
  // is where Dutch parts company with Italian and Icelandic and agrees with German instead.
  // Measured with Intl.DisplayNames("nl") on node v26.4.0 / ICU 78.3, then checked as a set:
  // these twelve have ZERO case-insensitive substring collisions, so no variant label contains
  // another variant's name. `Afrikaans` is byte-identical to English because Dutch has no
  // separate exonym for it; that is correct, not a missing translation. `IJslands` capitalizes
  // BOTH letters of the digraph — `Ijslands` would be a spelling error.
  "settings.gameVariant.english": "Engels",
  "settings.gameVariant.slovak": "Slowaaks",
  "settings.gameVariant.czech": "Tsjechisch",
  "settings.gameVariant.polish": "Pools",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italiaans",
  "settings.gameVariant.dutch": "Nederlands",
  "settings.gameVariant.german": "Duits",
  "settings.gameVariant.portuguese": "Portugees",
  "settings.gameVariant.danish": "Deens",
  "settings.gameVariant.swedish": "Zweeds",
  "settings.gameVariant.icelandic": "IJslands",
  "settings.rival.title": "Je tegenstander",
  "settings.rival.description":
    "De beheerder kiest de tegenstander voor nieuwe partijen.",
  "nav.settings": "Instellingen",
  // Byte-identical to English, same naturalized noun as `auth.eyebrow` above.
  "nav.account": "Account",
  "profile.subtitle":
    "Accountgegevens en wachtwoordbeveiliging op één plek.",
  "profile.email": "E-mail",
  "profile.noEmail": "Geen e-mail ingesteld",
  // Composed as a label against a value that can degrade to `history.unknownDate`. Dutch has no
  // obligatory preposition-plus-article form, so `sinds` governs a date and the fallback equally
  // and this cost nothing; "Lid sinds Onbekend" is as awkward as the English original and no
  // more so, which makes it pre-existing rather than a defect introduced here.
  "profile.memberSince": "Lid sinds",
  "profile.password.subtitle":
    "Wijzig je wachtwoord zonder de partij te verlaten.",
  "profile.password.footnote":
    "Sterkere wachtwoorden maken accounts voor partijen tegen mensen veiliger.",
  "profile.field.current": "Huidig wachtwoord",
  "profile.field.new": "Nieuw wachtwoord",
  "profile.field.confirm": "Nieuw wachtwoord bevestigen",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Huidig wachtwoord",
  // `tekens` and not `letters`: here the English `characters` means text characters, and `letter`
  // is this catalog's frozen word for what a tegel carries.
  "profile.ph.new": "Minstens 8 tekens",
  "profile.ph.confirm": "Herhaal het nieuwe wachtwoord",
  "profile.submit": "Wachtwoord wijzigen",
  "profile.submitting": "Wijzigen...",
  "profile.error.allFields": "Vul alle wachtwoordvelden in.",
  "profile.error.mismatch": "De nieuwe wachtwoorden zijn niet gelijk.",
  "play.title": "Kies je volgende partij",
  "play.lead":
    "Start een premiumduel tegen de AI, spring in de live wachtrij of open een van je opgeslagen partijen.",
  "play.ai.eyebrow": "Partij tegen AI",
  "play.ai.title": "Speel tegen de AI",
  "play.ai.body":
    "Speel tegen de huidige AI-tegenstander, met de bewegende openingstrekking.",
  "play.ai.preparing": "Partij voorbereiden...",
  "play.rival.unavailable": "Geen tegenstander beschikbaar",
  "play.humanQueue.eyebrow": "Spelerswachtrij",
  "play.humanQueue.title": "Vind een live tegenstander",
  "play.humanQueue.body":
    "Sluit je aan bij de eerste wachtende speler. Is er niemand, dan wacht je partij in de wachtkamer.",
  "play.humanQueue.joining": "Aansluiten bij de wachtrij...",
  "play.saved.eyebrow": "Opgeslagen partijen",
  "play.saved.title": "Ga verder waar je gebleven was",
  "play.saved.note":
    "Partijen tegen AI en tegen mensen delen één premiumoverzicht.",
  "play.error.catalogEmpty":
    "De catalogus met tegenstanders is leeg. Vul de gratis catalogus om partijen tegen AI te kunnen spelen.",
  "play.error.catalogUnavailable":
    "De catalogus met tegenstanders is nu niet beschikbaar. Probeer het over een moment opnieuw.",
  "play.error.variantUnavailable":
    "Er is geen speelbare spelvariant beschikbaar. Nieuwe partijen zijn geblokkeerd totdat er een speelbare variant kan worden geladen.",
  "play.error.startAi": "Er kon geen partij tegen AI worden gestart.",
  "play.error.joinQueue":
    "Aansluiten bij de spelerswachtrij is niet gelukt.",
  "play.error.loadGames": "Je partijen konden niet worden geladen.",
  "history.filter.ai": "AI",
  "history.filter.human": "Mensen",
  "history.filter.all": "Alles",
  "history.sort.recent": "Nieuwste",
  "history.refresh": "Vernieuwen",
  "history.loading": "Partijen laden",
  "history.empty.title": "Nog geen partijen in dit filter",
  "history.empty.body":
    "Start een nieuwe partij en die verschijnt hier, met premiumpaginering, resultaatlabels en snelle links om verder te spelen.",
  "history.noneYet": "Nog geen opgeslagen partijen",
  // Its name lies about its scope. Measured at four call sites: GameHistoryPanel.tsx:97 and both
  // uses inside `formatJoinedDate` (ProfileModal.tsx:23 and :26) are a missing DATE, and only
  // ProfileModal.tsx:220 is a missing USERNAME. Dutch escapes this twice over: `de datum` and
  // `de gebruikersnaam` are both de-words, so even an inflecting form would agree with both, and
  // a standalone Dutch adjective is uninflected anyway. Splitting the key would be a
  // `messages.en.ts` change and is not in this slice.
  "history.unknownDate": "Onbekend",
  "history.col.rival": "Tegenstander",
  "history.col.mode": "Modus",
  "history.col.result": "Resultaat",
  // Byte-identical to English and correct Dutch: `score` (de score) is the native noun for a
  // points total; `puntenstand` exists but is too long for a table column head.
  "history.col.score": "Score",
  "history.col.moves": "Zetten",
  "history.col.updated": "Bijgewerkt",
  // The eight outcome badges read against `partij` (de) in the row and against the column
  // heading `Resultaat` (het) in the header. That trap does not bite Dutch: every value here is
  // either a noun or a predicate participle, and a Dutch predicate participle is invariable, so
  // none of them agrees with anything. "Gewonnen" / "Verloren" is also what a Dutch results
  // table actually says.
  "history.outcome.waiting": "Wachten",
  "history.outcome.active": "Bezig",
  "history.outcome.won": "Gewonnen",
  "history.outcome.lost": "Verloren",
  "history.outcome.draw": "Gelijkspel",
  "history.outcome.gaveUp": "Opgegeven",
  "history.outcome.abandoned": "Verlaten",
  // DEAD KEY: `OUTCOME_META` at GameHistoryPanel.tsx:36-75 has exactly seven arms and no
  // `unknown`, so the product cannot render this. The value is correct and no further effort is
  // spent on it. Its removal belongs to a later slice.
  "history.outcome.unknown": "Onbekend",
  "history.mode.ai": "AI-duel",
  "history.mode.human": "Duel tegen mensen",
  "history.hint.waitingRoom": "Wachtkamer",
  "history.hint.boardReady": "Partij klaar",
  // `zak` (de) and `letterbak` (de) share a gender class, and the shared predicate `leeg` is
  // uninflected regardless, so no mixed-gender problem arises here.
  "history.endReason.bagEmpty": "Zak en letterbak leeg",
  "history.endReason.noMoves": "Geen zetten mogelijk",
  "history.endReason.sixZero": "Zes beurten zonder punten",
  "history.endReason.gaveUp": "Partij opgegeven",
  "history.endReason.queueCancelled": "Wachtrij geannuleerd",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139, where it
  // alternates in the same slot with `history.current` — an infinitive against an adjective in
  // one position. The infinitive works in both roles, and `Huidige` is uninflected here, so this
  // fixed call site cost Dutch nothing.
  "history.open": "Openen",
  "history.current": "Huidige",
  // Pagination is a pair of adjectives of the implied `pagina`, so these two are the one place
  // the infinitive label style would be wrong.
  "history.prev": "Vorige",
  "history.next": "Volgende",
  "history.modal.subtitle":
    "Bekijk oude partijen, wissel tussen AI en mensen en spring snel terug in het spel.",
  "queue.title": "Wachten op een tegenstander",
  "queue.body":
    "Je partij staat klaar. Die begint zodra er een andere speler bij komt.",
  "queue.leave": "Wachtrij verlaten",
  "queue.leaving": "Wachtrij verlaten...",
  "queue.error.dropped": "De realtimeverbinding is verbroken.",
  "queue.error.enter": "Je kon de wachtkamer niet binnengaan.",
  "queue.error.leave": "De wachtrij kon niet worden verlaten.",
  "draw.eyebrow": "Openingstrekking",
  "draw.title": "Wie de partij opent",
  // `dichter` is an invariable comparative here and the tegel is fixed at author time, not a
  // runtime value. The interpolated variant of this sentence is `draw.reason.closer`.
  "draw.subtitle":
    "Wie de tegel dichter bij A trekt, begint. Een joker wint altijd.",
  // Contrastive `Jij`: this label sits opposite the AI's side, which is what the contrast is for.
  "draw.side.you": "Jij",
  "draw.side.ai": "AI",
  "draw.pending": "Tegels uit de zak trekken...",
  "draw.blankCaption": "joker",
  "draw.result.youStart": "Jij begint",
  "draw.result.aiStart": "De AI begint",
  "draw.reason.blankYou": "Jouw joker wint de trekking.",
  "draw.reason.blankAi": "De AI trok de joker.",
  "draw.reason.bothBlank": "Beide tegels zijn jokers, dus jij begint.",
  "controls.play": "Spelen",
  "controls.pass": "Passen",
  "controls.exchange": "Ruilen",
  // `de ruil` is a settled Dutch noun, unlike the pass move, so the object can precede the
  // infinitive here in the order Dutch wants.
  "controls.confirmExchange": "Ruil bevestigen",
  "controls.cancel": "Annuleren",
  // Rendered CSS-uppercased on the board and read as a bare label elsewhere, so the value stays
  // lowercase. Deliberately NOT the same word as `game.aiPlayedFor.points`: this is a 10px pill
  // and that one is a 1.36rem sentence, so the pill takes the standard Dutch abbreviation and
  // the sentence takes the full noun.
  "board.pts": "ptn",
  // On-board instructions, so these two take the prose imperative rather than the control
  // infinitive. Both are longer than the English they replace on the tightest text surface in
  // the product; the shortest correct Dutch is kept and the overflow is reported.
  "board.pinchToZoom": "Knijp om te zoomen",
  "board.dragToPan": "Sleep om te schuiven",
  "board.hide": "Verbergen",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in the fixed order
  // [action][noun] at Board.tsx:692-693. Dutch, like German, puts the object BEFORE an
  // infinitive ("Zoom herstellen"), which that call site cannot express. German reached for the
  // loanword `Reset`; Dutch has a better answer, because the IMPERATIVE takes its object after
  // it: "Herstel zoom" is correct Dutch in exactly the order the spans impose. This is the one
  // control that is not an infinitive, and the call site is the reason.
  "board.reset": "Herstel",
  "rack.empty": "Geen tegels in de letterbak",
  "blank.chooseLetter": "Kies een letter voor de joker",
  "chat.title": "Partijchat",
  "chat.empty": "Nog geen berichten.",
  "chat.you": "Jij",
  "chat.unavailable": "Chat niet beschikbaar",
  "chat.placeholder": "Zeg iets",
  "chat.send": "Verzenden",
  "game.lexicon.collins2019": "Niet in Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Niet in het Slowaakse lexicon",
  "game.lexicon.czech": "Niet in het Tsjechische lexicon",
  "game.lexicon.polish": "Niet in het Poolse lexicon",
  // Twelve rows take the attributive nationality adjective agreeing with `het lexicon`, which in
  // Dutch is the language name of `settings.gameVariant.*` plus `-e` — so the two families stay
  // consistent for free. Unlike Italian and Icelandic the CASE also stays the same, because
  // Dutch capitalizes a nationality adjective in running text; and unlike German, Afrikaans
  // needs no exception, since `Afrikaanse` is an ordinary Dutch adjective.
  "game.lexicon.afrikaans": "Niet in het Afrikaanse lexicon",
  "game.lexicon.italian": "Niet in het Italiaanse lexicon",
  "game.lexicon.dutch": "Niet in het Nederlandse lexicon",
  "game.lexicon.german": "Niet in het Duitse lexicon",
  "game.lexicon.portuguese": "Niet in het Portugese lexicon",
  "game.lexicon.danish": "Niet in het Deense lexicon",
  "game.lexicon.swedish": "Niet in het Zweedse lexicon",
  "game.lexicon.icelandic": "Niet in het IJslandse lexicon",
  "game.lexicon.unknown": "Niet in het lexicon van het spel",
  "game.blocker.auth.title": "Authenticatie van de tegenstander is mislukt",
  "game.blocker.auth.body":
    "Deze gratis tegenstander kon zich niet authenticeren. Kies een andere gratis tegenstander of probeer het later opnieuw.",
  "game.blocker.rate.title": "Tegenstander heeft de limiet bereikt",
  "game.blocker.rate.body":
    "Deze gratis tegenstander heeft de aanvraaglimiet bereikt. Kies een andere gratis tegenstander of probeer het later opnieuw.",
  "game.blocker.unavail.title": "Tegenstander is niet beschikbaar",
  "game.blocker.unavail.body":
    "Deze gratis tegenstander is tijdelijk niet beschikbaar. Kies een andere gratis tegenstander of probeer het later opnieuw.",
  "game.blocker.badge.auth": "Authenticatie",
  "game.blocker.badge.rate": "Limiet bereikt",
  "game.blocker.badge.unavail": "Niet beschikbaar",
  "game.blocker.close": "Sluiten",
  "game.blocker.openSettings": "Instellingen openen",
  "game.toast.invalidPlacement": "Ongeldige plaatsing",
  "game.toast.invalidWords": "Ongeldige woorden",
  "game.toast.moveRejected": "Zet geweigerd",
  "game.toast.exchangeRejected": "Ruil geweigerd",
  // Dutch has no usable NOUN for the pass move (`een pas` is a step or a pass card), which is
  // the same gap Icelandic and Italian reported. Dutch needs no rephrasing for it: the
  // infinitive `passen` is itself the verbal noun, so this heading keeps the English shape.
  "game.toast.passRejected": "Passen geweigerd",
  // Byte-identical to English, and correct Dutch: `chat` and `offline` are both naturalized.
  "game.toast.chatOffline": "Chat is offline",
  "game.toast.aiPasses": "De AI past",
  "game.toast.aiExchanged": "De AI ruilde tegels",
  "game.toast.aiExchangedBody":
    "De AI vernieuwde de letterbak en gebruikte de beurt.",
  "game.toast.aiPassedBody": "Geen geldige zet gevonden — jij bent aan zet!",
  // ⚠ THIS CALL SITE BITES DUTCH, for the same reason it bit German. page.tsx:338 composes
  // `[before] <span>{score}</span> [points]` with the score FIXED in the middle and nothing
  // after the counted noun, and the Dutch perfect puts its participle at the end of the clause
  // ("De AI heeft 34 punten gescoord"), which those two spans cannot express. The SIMPLE PAST is
  // the answer, as it was for German — but it costs Dutch less: `scoorde` is fully idiomatic in
  // written Dutch, where German's `spielte` is a register downgrade from the spoken perfect.
  // `game.toast.aiPlayedWord` below is kept in the same tense so the one toast is consistent.
  "game.aiPlayedFor.before": "De AI scoorde",
  "game.aiPlayedFor.points": "punten",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation at page.tsx:1003. The indefinite
  // article is carried here, so the fallback reads "De AI speelde een woord" while a real word
  // reads "De AI speelde KAAS" — Dutch needs no article before a bare cited word.
  "game.aWord": "een woord",
  "game.status.selectExchange": "Kies tegels om te ruilen",
  "game.status.aiMoveReady": "Zet van de AI is klaar",
  "game.status.aiThinking": "De AI denkt na",
  "game.status.yourTurn": "Jij bent aan zet",
  "game.status.waitingForAi": "Wachten op de AI",
  "game.opponentFallback": "Tegenstander",
  "game.waitingSlot": "Wachten",
  "game.sessionExpired": "Sessie verlopen",
  "game.lastError": "Laatste fout:",
  "game.newGame": "Nieuwe partij",
  "game.starting": "Starten...",
  "game.victory": "Gewonnen!",
  "game.draw": "Gelijkspel!",
  "game.gameOver": "Einde partij",
  // The one place the `de AI` decision is visible at all: Dutch has no gender agreement on the
  // predicate noun, so only the article shows it.
  "game.giveUp.ai":
    "Deze partij opgeven? De AI wordt tot winnaar uitgeroepen.",
  "game.giveUp.human":
    "Deze partij opgeven? Je tegenstander wordt tot winnaar uitgeroepen.",
  // Italian needed `avere` plus an invariable object here because a reflexive participle agrees
  // with the subject. Dutch builds its perfect the same way German does but its participle NEVER
  // agrees with anything, so `hebben` + `opgegeven` needs no gender and this trap does not bite.
  "game.gaveUp": "Je hebt de partij opgegeven.",
  "game.error.giveUp": "Deze partij kon niet worden opgegeven",
  "game.error.newGame": "Er kon geen nieuwe partij worden gestart",
  "game.error.loadGames": "De partijen konden niet worden geladen.",
  "game.password.updated": "Wachtwoord gewijzigd.",
  "game.password.failed": "Het wachtwoord kon niet worden gewijzigd.",
  "game.ai.noRival": "Er is geen geschikte gratis tegenstander beschikbaar.",
  "game.ai.timeout": "De denktijd van de AI is verstreken.",
  "game.ai.moveFailed": "Zet van de AI is mislukt",
  "game.ws.syncFailed": "Realtimesynchronisatie is mislukt",
  "game.ws.connectFailed": "Realtimeverbinding is mislukt",
  "game.ws.authExpired":
    "De authenticatie voor realtime is verlopen. Vernieuw de pagina om opnieuw te verbinden.",
  "game.ws.invalidSession":
    "Deze realtimesessie is niet geldig. Vernieuw de pagina om opnieuw te verbinden.",
  "game.ws.unavailable":
    "De realtimedienst is niet beschikbaar. Probeer het opnieuw.",
  "board.zoomNoun": "zoom",
  "header.giveUp": "Opgeven",
  "header.givingUp": "Opgeven...",
  "header.giveUpTooltip": "Deze partij opgeven",
  // Nine characters against the English six, in a non-wrapping header cluster: longer than
  // Italian's four and Icelandic's seven, far shorter than pt-PT's fifteen. `Uitloggen` and
  // `Afmelden` are both standard; the everyday informal one is chosen to match the `je` register.
  "header.logout": "Uitloggen",
  "header.loggingOut": "Uitloggen...",
  "header.backToBoards": "Terug naar partijen",
  "header.profile": "Profiel",
  "header.games": "Partijen",
  "overlay.aiThinking": "AI denkt na",
  "overlay.searching": "Zetten zoeken...",
  "overlay.best": "Beste zet",
  // A very narrow pill beside a truncating word and a score. Five characters: the shortest form
  // that cannot be read as untranslated English, since a bare `BEST` is byte-identical to it.
  "overlay.bestBadge": "BESTE",
  "overlay.filtering":
    "Zwakke en ongeldige zetten worden eruit gefilterd voordat er een serieuze zet verschijnt...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, two slots each, so this catalog has SIX slot fillers
// and every one of them is a PURE NOUN rather than a phrase. CLDR nl selects `one` only at
// exactly 1 and `other` for everything else INCLUDING ZERO — measured on node v26.4.0 /
// ICU 78.3 and pinned by plural.test.ts — so Dutch writes "0 punten" and never the "0 ponto"
// that CLDR Portuguese produces next door.
//   point noun   punt / punten
//   minute noun  minuut / minuten
//   tile noun    tegel / tegels — and NOT the phrase Icelandic and Italian needed. A Dutch
//                predicate participle is invariable, so `geselecteerd` is appended OUTSIDE the
//                helper the way German appends `ausgewählt`, and the slot stays a bare noun.
// `pluralNl` is called and never `pluralEn`: the two agree over the integers but their CLDR
// rules differ on fractions, which is why the helper exists separately.
export const nlFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Tegel ${p.letter}, ${p.points} ` + pluralNl(p.points, "punt", "punten"),
  // Colon-labels with invariable participles, so nothing has to agree with an arbitrary count.
  "overlay.stats.tried": (p) => `Geprobeerd: ${p.count}`,
  "overlay.stats.valid": (p) => `Geldig: ${p.count}`,
  "overlay.stats.rejected": (p) => `Geweigerd: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Te veel verzoeken. Probeer het over ongeveer ${p.minutes} ` +
    pluralNl(p.minutes, "minuut", "minuten") +
    " opnieuw.",
  // `winner` and `loser` receive TILE LETTERS, never a person (draw-result.ts:29-30). `ligt` is
  // an invariable third-person verb and `dichter` an invariable comparative, so neither opaque
  // value needs an article and nothing has to agree with it.
  "draw.reason.closer": (p) => `${p.winner} ligt dichter bij A dan ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralNl(p.count, "tegel", "tegels") + " geselecteerd",
  // `model` is an opaque runtime id, so `met` carries it with no article before it.
  "game.ai.exploring": (p) => `Geldige woorden zoeken met ${p.model}...`,
  "game.ai.attempt": (p) => `Poging ${p.index}/${p.total} · ${p.label}`,
  // Simple past, matching `game.aiPlayedFor.before` in the same toast.
  "game.toast.aiPlayedWord": (p) => `De AI speelde ${p.word}`,
  // `is aan zet` and not a participle: `name` is an opaque runtime value, and this predicate is
  // invariable.
  "game.status.opponentPlaying": (p) => `${p.name} is aan zet`,
  // Two full forms, never a suffix trick, and unlike English the ADJECTIVE also changes:
  // `ongeldig` before an indefinite neuter singular, `ongeldige` in the plural.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ongeldige woorden!" : "Ongeldig woord!",
  "game.ai.routeFailed": (p) => `De AI-aanroep is mislukt (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `De AI-aanroep is mislukt (${p.status}), nog voor de stream begon.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `De AI-aanroep is mislukt (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, and a Dutch article before a value whose
  // de/het class is unknown would be a guess.
  "play.humanQueue.queueFor": (p) => `Wachtrij: ${p.variant}`,
  "queue.room": (p) => `Kamer ${p.code}`,
  "history.pageOf": (p) => `Pagina ${p.page} van ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `Weergegeven: ${p.from}-${p.to} van ${p.total}`,
  // Colon form for the same reason as `play.humanQueue.queueFor`: `language` is opaque.
  "picker.flagAlt": (p) => `Vlag: ${p.language}`,
};
