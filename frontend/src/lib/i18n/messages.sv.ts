// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralSv } from "./plural";

// Frozen SWEDISH game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile bricka (en bricka, brickan, brickor, brickorna) · letter bokstav (en bokstav) ·
//   rack brickställ (ett brickställ, brickstället) · blank blank (en blank), always carried by the
//   unambiguous compound blankbricka (en blankbricka) where the PIECE is named · bag påse (en
//   påse) · board = bräde (ett bräde, brädet; the playing surface, full form spelbräde, stem
//   bräd- in compounds) AND parti (ett parti; the metonym for a saved game) · pass passa (the
//   verb) with the game call pass (ett pass) · points poäng (en poäng, INVARIABLE in number) ·
//   rival = opponent motståndare (en motståndare).
//
// `bräde` really is two words. `bräde` is the surface a bricka sits on; `parti` is the metonym for
// a stored game ("Sparade partier", "Tillbaka till partier"), which is what Swedish board-game
// usage says — "ett parti schack". A third word stays apart from both: `spel` is the game as a
// product or ruleset, which is why the picker says `Spelvariant` and never `Partivariant`.
// `passa` and `byta` are different moves and keep different words. tile and letter are NOT
// collapsed the way Icelandic collapses them: a `blank` is a bricka carrying no bokstav that
// becomes one, so the piece and the character it carries need separate words.
// THE PASS NOUN EXISTS HERE, as it does in Danish and unlike Icelandic, Italian and Dutch:
// `pass` is the settled Swedish call in card and board games, so a noun-shaped pass site needs no
// verbal rephrasing — see `game.toast.passRejected`. Two knock-ons, and they are the same two
// Danish and Icelandic reported: `ett pass` is also a passport, which the neighbouring `Passa`
// button disambiguates, and the verb `passa` also means "to fit", so `error.conflict` says
// `strider mot` and never `passar inte`.
// `blank` needed the compound because Swedish `blank` is ALSO an ordinary adjective meaning
// glossy — the exact ambiguity German solved with `Blankostein`. `blankbricka` names the piece,
// bare `blank` is used only in `draw.blankCaption`, which renders directly under the bricka it
// labels, and no surface description in this catalog uses `blank` adjectivally (see
// `settings.board.blackDesc`). `joker` was available and is deliberately NOT used: it is the
// Danish and Dutch choice, and D6 forbids harmonizing terminology across languages.
// `tur` is the TURN and `drag` is the MOVE; those two are kept apart wherever the English
// distinguishes them, with one stated exception at `history.endReason.sixZero`.
//
// Register: informal `du` / `din` / `ditt` / `dina`, error messages included. Never `Ni` / `Er`.
// This cost nothing, for a dated reason: the du-reform of the late 1960s retired `Ni` as a polite
// form, and what survives reads as distancing or archaic rather than merely formal. So, as in
// Danish, there was never a second usable register to weigh — unlike German's `Sie` or Italian's
// `Lei`.
// Label style: IMPERATIVE for every control, action label, column heading and accessible name
// (Spela · Passa · Byt · Avbryt · Logga ut · Öppna · Sök · Skicka · Välj · Återställ · Ge upp).
// The control convention and the prose register COINCIDE in Swedish rather than contrasting: the
// imperative is both what a Swedish button says and what `du`-prose says (Välj ditt nästa parti,
// Kontrollera de angivna uppgifterna, Försök igen), so like Italian and Danish — and unlike Dutch
// — this catalog never had to choose between an infinitive control form and a bare-stem prose
// form.
// Pre-authorized exceptions used: the PAGINATION PAIR (`history.prev` / `history.next` are
// adjectives of the implied `sida`), the TOGGLE STATE WORDS (`settings.toggle.on` / `.off`) and
// the BADGE WORDS (`settings.board.active`, `overlay.bestBadge`).
// Progress states take the present tense plus an ellipsis (Loggar in... · Loggar ut... ·
// Startar... · Ändrar...), which keeps `header.loggingOut` at twelve characters inside the
// non-wrapping header cluster, two under the English it replaces.
// `gratis` is used for the free rival rather than `kostnadsfri`, and the choice is grammatical as
// well as short: `gratis` is an INVARIABLE adjective, so it never has to agree with anything, and
// it forms closed compounds (gratismotståndare, gratiskatalogen).
//
// ORTHOGRAPHY. `å ä ö` are real UTF-8 everywhere and are never written `aa` / `ae` / `oe`. All
// three are combining diacritics that NFD decomposes, so locales.ts's picker search folds them
// correctly (Åtgärd → atgard, Välj → valj, Sök → sok); the fold gap that affects Danish `æ` and
// Icelandic `þ ð` does not touch this catalog.
// NO COMMON NOUN IS CAPITALIZED outside sentence-initial position — Swedish is not German here,
// and a capitalized `Bricka` or `Bräde` is the single most visible way this catalog could have
// gone wrong. AND NO LANGUAGE NAME IS CAPITALIZED IN RUNNING TEXT either (`svenska`, `engelska`,
// `tyska`): Swedish sides with Danish, Italian and Icelandic, against German and Dutch, which
// capitalize them. Standalone picker rows still take a capital — see `settings.gameVariant.*`.
// Compounds are written CLOSED, as one word: spelvariant, gränssnittsspråk, lösenord, brickställ,
// brädyta, betänketid, spelarkö. A compound on a foreign or acronym stem takes a hyphen instead:
// AI-motståndare, AI-duell, AI-förlopp, live-matchning.
// The DEFINITE ARTICLE IS A SUFFIX and not a separate word, so every noun's gender and
// definiteness are baked into the word form: brickan / brädet / brickorna. That is the reason no
// interpolated runtime value in this catalog ever carries a definite suffix or an agreeing
// adjective. The INDEFINITE article `en` / `ett` is a separate word and therefore safe, which is
// why `game.aWord` can carry one.
// `AI` is a preserved product token and takes COMMON gender `en`, never `ett`: its Swedish head
// noun `artificiell intelligens` is an en-word. Swedish attaches an inflectional ending to an
// abbreviation with a COLON, not an apostrophe, so "the AI" is `AI:n` and its genitive is `AI:ns`
// — the same convention as `TV:n` and `EU:s`, and NOT Danish's `AI'en`. Because Swedish marks
// definiteness as a suffix, that gender choice is visible in almost every AI string rather than
// only in an article. Same rule for `GPU:n`.
// Thousands separator is a NO-BREAK SPACE, U+00A0, measured with Intl.NumberFormat("sv") on node
// v26.4.0 / ICU 78.3: `279 496`. It is written as the escape `279\u00A0496` in `landing.footnote`,
// the way messages.sk.ts, messages.cs.ts, messages.pl.ts and messages.pt.ts write it. ⛔ The five
// catalogs that ship a period — de, nl, it, is, da — are NOT the model here, and copying them
// would be the one purely mechanical way to get this catalog wrong.
//
// ⚠ DANISH IS CATALOG 6 AND LANDED ONE COMMIT AGO. Where this catalog deliberately diverges:
//   · the pieces and the bag — Danish `brik` / `brikkerne` / `pose` against Swedish `bricka` /
//     `brickorna` / `påse`. These are cognate pairs in different shapes rather than different
//     stems, which is why the temptation is real: `brik` and `pose` are simply not Swedish words,
//     and Danish's definite plural `-ne` is Swedish's `-na` on a different plural (`-or`).
//   · the alphabet — Danish `æ ø å` against Swedish `å ä ö`. This file contains no `æ` and no `ø`
//     at all; `Vælg`, `Søg`, `Bekræft`, `bræt` and `næste` become `Välj`, `Sök`, `Bekräfta`,
//     `bräde` and `nästa`.
//   · sign-out and the `-lig` trap — Danish `Log ud` (6) against Swedish `Logga ut` (8), and
//     Danish `tilgængelig` / `ugyldig` / `mulig` against Swedish `tillgänglig` / `ogiltig` /
//     `möjlig`, where the suffix transfers and the stem does not.
//   · the definite abbreviation — Danish `AI'en` against Swedish `AI:n`.
//   · CLDR fractions — Danish selects `one` for 0.5, Swedish selects `other` like English, so the
//     fraction caveat on `pluralDa` is not this catalog's caveat.
//   · the thousands separator — Danish's period against this catalog's U+00A0.
export const svText: Record<TextKey, string> = {
  // Both values are deliberately byte-identical to English: `Libre Tiles` is a preserved brand, and
  // `premium` is an indeclinable loan modifier that Swedish places before the noun exactly as
  // English does. Neither is a skipped key.
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "människor och AI.",
  "landing.lead":
    "Ordspel med öppen källkod, live-matchning, vassa AI-motståndare, premiumgrafik på brädet och en historik som är klar för ditt nästa parti.",
  "landing.card.ai.title": "AI-dueller",
  // `model` is TRANSLATED here, and unlike in Danish and Dutch the decision IS observable: the
  // ordinary Swedish noun is `modell` (en modell) with two l's, so `modellval` and the
  // untranslated `modelval` are different strings. `chat` is translated for the same reason and is
  // likewise observable — the Swedish noun is `chatt` (en chatt) with two t's — which makes this
  // catalog the first in the campaign where the protected-token decision changes any byte at all.
  "landing.card.ai.body": "Premiumpartier med modellval",
  "landing.card.queue.title": "Livekö",
  "landing.card.queue.body": "Synkronisering i realtid och chatt",
  "landing.card.saved.title": "Sparade partier",
  "landing.card.saved.body": "Fortsätt partier mot AI eller människor",
  // The separator is U+00A0 and not the period five of the six new catalogs ship. The number
  // itself is unchanged.
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 giltiga ord",
  "auth.eyebrow": "Konto",
  // Swedish sentence case collapses English's "Sign in" / "Sign In" pair into one string, so the
  // heading and the tab are deliberately identical rather than artificially distinguished.
  "auth.heading.login": "Logga in",
  "auth.heading.register": "Skapa konto",
  "auth.tab.login": "Logga in",
  "auth.tab.register": "Registrera",
  "auth.field.username": "Användarnamn",
  "auth.field.password": "Lösenord",
  "a11y.chatInput": "Chattmeddelande",
  "a11y.dialog.profile": "Profil",
  "a11y.dialog.games": "Sparade partier",
  "a11y.dialog.blank": "Välj en bokstav",
  "a11y.dialog.rival": "Motståndaren är inte tillgänglig",
  // `tur` is the TURN and `drag` is the MOVE; this announcer names the turn.
  "a11y.status.turn": "Turstatus",
  "a11y.status.aiThinking": "AI-förlopp",
  "a11y.rackBlank": "Blankbricka",
  "auth.submit.loading": "Loggar in...",
  "auth.submit.login": "Spela nu",
  "auth.submit.register": "Skapa konto och spela",
  "meta.title": "Libre Tiles — ordspel på webben med AI och live-multiplayer",
  // The sixth prose site of the `chat` token, and the one not listed in this campaign's measured
  // set of five; it is translated here for the same reason as the other five.
  "meta.description":
    "Ordspel med öppen källkod, med AI-motståndare, live-partier mot människor, chatt och smidig dra-och-släpp-hantering.",
  "error.checkFields": "Kontrollera de angivna uppgifterna.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Fel användarnamn eller lösenord",
  "error.sessionExpired": "Din session har gått ut. Logga in igen.",
  "error.forbidden": "Du har inte behörighet att göra det.",
  "error.notFound": "Hittades inte.",
  // `strider mot` and not `passar inte`: `passa` is the frozen pass term and also means "to fit",
  // which is the same knock-on Danish and Icelandic reported.
  "error.conflict": "Åtgärden strider mot partiets aktuella tillstånd.",
  "error.throttled.unknown":
    "För många förfrågningar. Vänta en stund och försök igen.",
  "error.throttled.oneMinute":
    "För många förfrågningar. Försök igen om ungefär en minut.",
  "error.unavailable":
    "Tjänsten är för tillfället inte tillgänglig. Försök igen.",
  "error.generic": "Något gick fel. Försök igen.",
  // `betänketid` is the settled Swedish board-game word for thinking time — Danish's
  // `betænkningstid` is a different formation. `AI:ns` is the genitive of the definite `AI:n`,
  // which is where the `en` gender choice becomes visible.
  "settings.timeout.title": "AI:ns betänketid",
  "settings.timeout.30": "Snabb blick på brädet",
  "settings.timeout.60": "Balanserad sökning",
  "settings.timeout.120": "Standardbetänketid",
  "settings.timeout.180": "Turneringstempo",
  "settings.timeout.300": "Längsta betänketid",
  "settings.steps.title": "Söksteg",
  "settings.steps.10": "Snabba verktyg",
  "settings.steps.20": "Fler försök",
  "settings.steps.30": "Fokuserad sökning",
  "settings.steps.50": "Standardsökdjup",
  "settings.steps.80": "Maximalt tryck",
  "settings.board.title": "Brädyta",
  "settings.board.description":
    "Sparas på den här enheten och används på spelbrädet.",
  "settings.board.wood": "Trä",
  "settings.board.woodDesc": "Klassisk valnötsådring",
  "settings.board.black": "Svart",
  // `Glansig` and not `Blank`: `blank` is this catalog's frozen word for the blank tile, and using
  // it adjectivally here would put the two readings on one settings panel.
  "settings.board.blackDesc": "Glansig nattlack",
  "settings.board.green": "Grön",
  "settings.board.greenDesc": "Mörk turneringsfilt",
  // ⚠ THIS TRAP BITES SWEDISH, as it bit Danish, Portuguese and Icelandic, and unlike Dutch and
  // Italian. The badge is a sibling span of the surface name (settings/page.tsx:216 and :220), and
  // a Swedish predicate adjective inflects: `aktiv` for an en-word, `aktivt` for an ett-word,
  // `aktiva` in the plural. The three surface labels are not one class — `Trä` is a neuter NOUN
  // while `Svart` and `Grön` are colour adjectives in different forms — and the implied head noun
  // is itself ambiguous between `ett bräde` and `en yta`. `Används` is a present passive verb form
  // and therefore invariable, so no guess is made.
  "settings.board.active": "Används",
  // Toggle state words, not action labels: the pre-authorized exception to the imperative style.
  "settings.toggle.on": "På",
  "settings.toggle.off": "Av",
  "settings.shiny.title": "Glanseffekt",
  "settings.shiny.description":
    "Stäng av den levande glansen när du vill belasta GPU:n mindre.",
  "settings.shiny.onDesc": "Animerad glans på brädet",
  "settings.shiny.offDesc": "Lägre GPU-belastning",
  "settings.premium.title": "Premiumutseende",
  "settings.premium.description":
    "Interaktivt bärnstensfärgat ljus för partiets rubrikrad och brickstället.",
  "settings.premium.onDesc": "Interaktiva premiumytor",
  "settings.premium.offDesc": "Klassiska mörka ytor",
  "settings.backToGame": "Tillbaka till partiet",
  "settings.error.newGame":
    "Det gick inte att starta ett nytt parti just nu.",
  "settings.warn.accountSync":
    "Kontosynkroniseringen är inte tillgänglig just nu. Inställningarna fungerar fortfarande lokalt på den här enheten.",
  "settings.warn.rivalRepair":
    "En gratismotståndare är vald på den här enheten. Inställningen på kontot kunde inte repareras än.",
  "settings.uiLanguage.title": "Gränssnittsspråk",
  "settings.uiLanguage.description":
    "Menyer, knappar och meddelanden. Gäller omedelbart och bara på den här enheten.",
  // Endonyms, identical in every catalog by project rule. Never Swedish exonyms.
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
  "picker.search": "Sök",
  "picker.noMatch": "Ingen träff",
  "picker.uiLanguageLabel": "Gränssnittsspråk",
  "picker.gameVariantLabel": "Spelvariant",
  "settings.gameVariant.title": "Spelvariant",
  "settings.gameVariant.description":
    "Brickor, påse och ordlista. Gäller bara NYA partier och ändrar aldrig ett pågående parti. Det här är inte gränssnittsspråket.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED — but only because a picker row
  // is a standalone list item and therefore sentence-initial. Swedish does NOT capitalize a
  // language name in itself, so the `game.lexicon.*` family below writes the same words lowercase.
  // That puts Swedish in Danish's, Italian's and Icelandic's position and not Dutch's or German's.
  // Measured with Intl.DisplayNames("sv") on node v26.4.0 / ICU 78.3, then checked as a set: these
  // twelve have ZERO case-insensitive substring collisions, so no variant label contains another
  // variant's name. `Afrikaans` is byte-identical to English because Swedish has no separate
  // exonym for it; that is correct, not a missing translation. None of the twelve contains `æ` or
  // `ø`, and every diacritic they do carry (`ä`, `ö`) folds for picker search.
  "settings.gameVariant.english": "Engelska",
  "settings.gameVariant.slovak": "Slovakiska",
  "settings.gameVariant.czech": "Tjeckiska",
  "settings.gameVariant.polish": "Polska",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italienska",
  "settings.gameVariant.dutch": "Nederländska",
  "settings.gameVariant.german": "Tyska",
  "settings.gameVariant.portuguese": "Portugisiska",
  "settings.gameVariant.danish": "Danska",
  "settings.gameVariant.swedish": "Svenska",
  "settings.gameVariant.icelandic": "Isländska",
  "settings.rival.title": "Din motståndare",
  "settings.rival.description":
    "Administratören väljer motståndare för nya partier.",
  "nav.settings": "Inställningar",
  "nav.account": "Konto",
  "profile.subtitle": "Kontouppgifter och lösenordssäkerhet på ett ställe.",
  "profile.email": "E-post",
  "profile.noEmail": "Ingen e-post angiven",
  // Composed as a label against a value that can degrade to `history.unknownDate`. The trap does
  // NOT bite Swedish: `sedan` is a bare preposition that governs its complement with no article,
  // no case and no definite suffix, so "Medlem sedan Okänt" is exactly as awkward as the English
  // original and no more so — pre-existing, not introduced here.
  "profile.memberSince": "Medlem sedan",
  "profile.password.subtitle":
    "Ändra ditt lösenord utan att lämna partiet.",
  "profile.password.footnote":
    "Starkare lösenord skyddar ditt konto bättre i partier mot människor.",
  "profile.field.current": "Nuvarande lösenord",
  "profile.field.new": "Nytt lösenord",
  "profile.field.confirm": "Bekräfta nytt lösenord",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Nuvarande lösenord",
  // `tecken` and not `bokstäver`: here the English `characters` means text characters, and
  // `bokstav` is this catalog's frozen word for what a bricka carries.
  "profile.ph.new": "Minst 8 tecken",
  "profile.ph.confirm": "Upprepa det nya lösenordet",
  "profile.submit": "Ändra lösenord",
  "profile.submitting": "Ändrar...",
  "profile.error.allFields": "Fyll i alla lösenordsfält.",
  "profile.error.mismatch": "De nya lösenorden är inte lika.",
  "play.title": "Välj ditt nästa parti",
  "play.lead":
    "Starta en premiumduell mot AI:n, hoppa in i livekön eller öppna ett av dina sparade partier.",
  "play.ai.eyebrow": "Parti mot AI",
  "play.ai.title": "Spela mot AI:n",
  "play.ai.body":
    "Spela mot den aktuella AI-motståndaren, med den animerade inledande dragningen.",
  "play.ai.preparing": "Förbereder partiet...",
  "play.rival.unavailable": "Ingen motståndare tillgänglig",
  "play.humanQueue.eyebrow": "Spelarkö",
  "play.humanQueue.title": "Hitta en motståndare live",
  "play.humanQueue.body":
    "Anslut dig till den första spelaren som väntar. Om ingen finns där väntar ditt parti i väntrummet.",
  "play.humanQueue.joining": "Går in i kön...",
  "play.saved.eyebrow": "Sparade partier",
  "play.saved.title": "Fortsätt där du slutade",
  "play.saved.note":
    "Partier mot AI och mot människor delar en gemensam premiumhistorik.",
  "play.error.catalogEmpty":
    "Motståndarkatalogen är tom. Fyll gratiskatalogen så att partier mot AI kan spelas.",
  "play.error.catalogUnavailable":
    "Motståndarkatalogen är inte tillgänglig just nu. Försök igen om en stund.",
  "play.error.variantUnavailable":
    "Ingen spelbar spelvariant är tillgänglig. Nya partier är blockerade tills en spelbar variant kan läsas in.",
  "play.error.startAi": "Partiet mot AI kunde inte startas.",
  "play.error.joinQueue": "Det gick inte att gå in i spelarkön.",
  "play.error.loadGames": "Dina partier kunde inte läsas in.",
  // Byte-identical to English because `AI` is a preserved product token, as at `draw.side.ai`.
  "history.filter.ai": "AI",
  "history.filter.human": "Människor",
  "history.filter.all": "Alla",
  "history.sort.recent": "Senaste",
  "history.refresh": "Uppdatera",
  "history.loading": "Läser in partier",
  "history.empty.title": "Det finns inga partier i det här filtret än",
  "history.empty.body":
    "Starta ett nytt parti, så visas det här med premiumsidväxling, resultatmärken och snabba länkar för att spela vidare.",
  "history.noneYet": "Inga sparade partier än",
  // Its name lies about its scope. Measured at four call sites: GameHistoryPanel.tsx:97 and both
  // uses inside `formatJoinedDate` (ProfileModal.tsx:23 and :26) are a missing DATE, and only
  // ProfileModal.tsx:220 is a missing USERNAME. Swedish escapes this by GENDER rather than by
  // Danish's morphological accident: `ett datum` and `ett användarnamn` are BOTH neuter, so the
  // neuter singular `Okänt` is the correct form at all four sites. Splitting the key would be a
  // `messages.en.ts` change and is not in this slice.
  "history.unknownDate": "Okänt",
  "history.col.rival": "Motståndare",
  // `Typ` and not `Läge`: this column holds a category (AI-duell / Duell mot människor), which is
  // what a Swedish table calls a type.
  "history.col.mode": "Typ",
  "history.col.result": "Resultat",
  "history.col.score": "Poäng",
  "history.col.moves": "Drag",
  // Breaks this catalog's own agreement pattern on purpose: `uppdaterad` is the en-form, agreeing
  // with the implied table ROW (`en rad`) rather than with the row's `parti` (ett parti), which is
  // what a Swedish table heading over a timestamp column actually says.
  "history.col.updated": "Uppdaterad",
  // The eight outcome badges read against `parti` in the row and against the column heading
  // `Resultat` in the header. That trap does NOT bite Swedish, twice over: both nouns are NEUTER
  // (`ett parti`, `ett resultat`), so a single neuter form is correct at both sites; and `Vinst`
  // and `Förlust` are NOUNS that agree with nothing at all, while `Väntar` and `Pågår` are
  // invariable finite verbs. Only the two participles carry a form, and both take the neuter -t
  // that both candidate head nouns require.
  "history.outcome.waiting": "Väntar",
  "history.outcome.active": "Pågår",
  "history.outcome.won": "Vinst",
  "history.outcome.lost": "Förlust",
  "history.outcome.draw": "Oavgjort",
  "history.outcome.gaveUp": "Uppgivet",
  "history.outcome.abandoned": "Övergivet",
  // DEAD KEY: `OUTCOME_META` at GameHistoryPanel.tsx:36-73 has exactly seven arms and no
  // `unknown`, so the product cannot render this. The value is correct and no further agreement
  // effort is spent on it. Its removal belongs to a later slice.
  "history.outcome.unknown": "Okänt",
  "history.mode.ai": "AI-duell",
  "history.mode.human": "Duell mot människor",
  "history.hint.waitingRoom": "Väntrum",
  "history.hint.boardReady": "Partiet är klart",
  // `påse` is COMMON gender and `brickställ` is NEUTER, so the two subjects are a mixed-gender
  // pair — the situation that forced Icelandic into a neuter. Swedish needs no workaround: the
  // shared predicate is PLURAL, and a Swedish plural adjective is `-a` for every gender.
  "history.endReason.bagEmpty": "Påse och brickställ tomma",
  "history.endReason.noMoves": "Inga möjliga drag",
  // The one place the tur / drag split is deliberately not honoured. English says "turns", but
  // Swedish plural `turer` reads as trips rather than as game turns, and a scoreless pass is still
  // a `drag` in Swedish game usage.
  "history.endReason.sixZero": "Sex drag utan poäng",
  "history.endReason.gaveUp": "Partiet uppgivet",
  "history.endReason.queueCancelled": "Kön avbruten",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139, where it
  // alternates in the same slot with `history.current`. The Swedish imperative works in both
  // roles, so that fixed call site costs nothing.
  "history.open": "Öppna",
  // Its partner did cost something, exactly as it cost Danish. `aktuell` / `aktuellt` inflects for
  // gender and the implied noun here is the NEUTER `parti`, so the agreeing form would have to be
  // `Aktuellt`. `Nuvarande` is a present-participle adjective, and Swedish `-ande` participles are
  // indeclinable in every gender, number and definiteness, so nothing agrees with anything.
  "history.current": "Nuvarande",
  // Pagination is a pair of adjectives of the implied `sida`, so these two are the one place the
  // imperative label style would be wrong.
  "history.prev": "Föregående",
  "history.next": "Nästa",
  "history.modal.subtitle":
    "Titta på gamla partier, växla mellan AI och människor och hoppa snabbt tillbaka in i spelet.",
  "queue.title": "Väntar på en motståndare",
  "queue.body":
    "Ditt parti är klart. Det startar så snart en annan spelare ansluter.",
  "queue.leave": "Lämna kön",
  "queue.leaving": "Lämnar kön...",
  "queue.error.dropped": "Realtidsanslutningen bröts.",
  "queue.error.enter": "Det gick inte att komma in i väntrummet.",
  "queue.error.leave": "Det gick inte att lämna kön.",
  "draw.eyebrow": "Inledande dragning",
  "draw.title": "Vem inleder partiet",
  // `närmast` is a superlative on a bricka that is fixed at author time, not a runtime value. The
  // interpolated variant of this sentence is `draw.reason.closer`.
  "draw.subtitle":
    "Den som drar brickan närmast A börjar. En blankbricka vinner alltid.",
  "draw.side.you": "Du",
  // Byte-identical to English because `AI` is a preserved product token.
  "draw.side.ai": "AI",
  "draw.pending": "Drar brickor från påsen...",
  // Byte-identical to English and genuinely the correct native form: `blank` is this catalog's
  // frozen Swedish term, and the bare noun is safe here because the caption renders directly under
  // the bricka it labels, where the adjectival reading cannot arise.
  "draw.blankCaption": "blank",
  "draw.result.youStart": "Du börjar",
  "draw.result.aiStart": "AI:n börjar",
  "draw.reason.blankYou": "Din blankbricka vinner dragningen.",
  "draw.reason.blankAi": "AI:n drog blankbrickan.",
  "draw.reason.bothBlank": "Båda brickorna är blankbrickor, så du börjar.",
  "controls.play": "Spela",
  // `Passa` is the Swedish imperative of the frozen pass term, five characters, and the
  // neighbouring buttons remove the passport reading of the noun `ett pass`.
  "controls.pass": "Passa",
  "controls.exchange": "Byt",
  // Thirteen characters against the English sixteen, so the non-wrapping control grid gains room
  // here rather than losing it.
  "controls.confirmExchange": "Bekräfta byte",
  "controls.cancel": "Avbryt",
  // Rendered under a CSS `uppercase` class on the board (Board.tsx:652-653) and as a bare label in
  // the AI overlay, so the value stays lowercase. It is the SAME word as
  // `game.aiPlayedFor.points`: Swedish `poäng` is already five characters and the abbreviation `p`
  // would read as an invented shortening beside a large number, so there is no shorter honest form.
  "board.pts": "poäng",
  // On-board instructions on the tightest text surface in the product (Board.tsx:668-677). Both
  // are longer than the English they replace; the shortest correct Swedish is kept and the
  // overflow is reported.
  "board.pinchToZoom": "Nyp för att zooma",
  "board.dragToPan": "Dra för att flytta",
  "board.hide": "Dölj",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in the fixed order
  // [action][noun] at Board.tsx:692-693. That call site does NOT bite Swedish: the Swedish
  // imperative takes its object after it, so "Återställ zoom" is correct in exactly the order the
  // spans impose. German had to reach for the loanword `Reset` and Dutch had to abandon its
  // infinitive control style to get here; Swedish needs neither, because the imperative is already
  // this catalog's control form and because Swedish is not verb-final.
  "board.reset": "Återställ",
  "rack.empty": "Inga brickor i brickstället",
  "blank.chooseLetter": "Välj en bokstav till blankbrickan",
  "chat.title": "Partichatt",
  "chat.empty": "Inga meddelanden än.",
  "chat.you": "Du",
  "chat.unavailable": "Chatten är inte tillgänglig",
  "chat.placeholder": "Skriv något",
  "chat.send": "Skicka",
  "game.lexicon.collins2019": "Finns inte i Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Finns inte i den slovakiska ordlistan",
  "game.lexicon.czech": "Finns inte i den tjeckiska ordlistan",
  "game.lexicon.polish": "Finns inte i den polska ordlistan",
  // Measured, TEN for ten: this family has eleven language rows, and ten of them take the language
  // adjective in its definite form, which in Swedish is `-a` for EVERY gender and number, so
  // agreement with `ordlistan` is free. Better than free, in fact: that definite adjective is the
  // SAME STRING as the language noun of `settings.gameVariant.*`, so the two families differ only
  // in case — lowercase here because Swedish writes a language word lowercase in running text,
  // capitalized there because a picker row is a standalone item.
  // `afrikaans` is the eleventh language row and the one exception: Swedish has no adjective built
  // on it, and the nearest form `afrikansk` means African, so that row carries the bare language
  // name after a preposition rather than an invented or a wrong adjective. German, Portuguese and
  // Danish made the same exception by their own mechanisms. There is no `game.lexicon.english`
  // row at all — the English variant's `lexicon_id` is `collins2019`, whose row names the
  // dictionary rather than a language.
  "game.lexicon.afrikaans": "Finns inte i ordlistan för afrikaans",
  "game.lexicon.italian": "Finns inte i den italienska ordlistan",
  "game.lexicon.dutch": "Finns inte i den nederländska ordlistan",
  "game.lexicon.german": "Finns inte i den tyska ordlistan",
  "game.lexicon.portuguese": "Finns inte i den portugisiska ordlistan",
  "game.lexicon.danish": "Finns inte i den danska ordlistan",
  "game.lexicon.swedish": "Finns inte i den svenska ordlistan",
  "game.lexicon.icelandic": "Finns inte i den isländska ordlistan",
  "game.lexicon.unknown": "Finns inte i spelets ordlista",
  "game.blocker.auth.title": "Motståndarens inloggning misslyckades",
  "game.blocker.auth.body":
    "Den här gratismotståndaren kunde inte logga in. Byt till en annan gratismotståndare eller försök igen senare.",
  "game.blocker.rate.title": "Motståndaren har nått sin gräns",
  "game.blocker.rate.body":
    "Den här gratismotståndaren har nått sin gräns för förfrågningar. Byt till en annan gratismotståndare eller försök igen senare.",
  "game.blocker.unavail.title": "Motståndaren är inte tillgänglig",
  "game.blocker.unavail.body":
    "Den här gratismotståndaren är tillfälligt inte tillgänglig. Byt till en annan gratismotståndare eller försök igen senare.",
  "game.blocker.badge.auth": "Inloggning",
  "game.blocker.badge.rate": "Gräns nådd",
  "game.blocker.badge.unavail": "Ej tillgänglig",
  "game.blocker.close": "Stäng",
  "game.blocker.openSettings": "Öppna inställningar",
  "game.toast.invalidPlacement": "Ogiltig placering",
  "game.toast.invalidWords": "Ogiltiga ord",
  // `drag`, `byte` and `pass` are all NEUTER, so one participle form `avvisat` serves all three
  // rejection toasts and none of them has to be rephrased.
  "game.toast.moveRejected": "Drag avvisat",
  "game.toast.exchangeRejected": "Byte avvisat",
  // No verbal rephrasing is needed here, unlike in Icelandic, Italian and Dutch: `pass` is a real
  // Swedish game noun, and the neighbouring `Passa` button removes the passport reading.
  "game.toast.passRejected": "Pass avvisat",
  "game.toast.chatOffline": "Chatten är offline",
  "game.toast.aiPasses": "AI:n passar",
  "game.toast.aiExchanged": "AI:n bytte brickor",
  "game.toast.aiExchangedBody": "AI:n fyllde på brickstället och förbrukade sin tur.",
  "game.toast.aiPassedBody": "Hittade inget giltigt drag — din tur!",
  // ⚠ THE NAMED CALL SITE, AND IT DOES NOT BITE SWEDISH. page.tsx:338 composes
  // `[before] <span>{score}</span> [points]` with the score FIXED in the middle and nothing after
  // the counted noun. German and Dutch both had to abandon the perfect tense here because their
  // verb phrase is FINAL — the participle would land after the number. Swedish is Mainland
  // Scandinavian and never developed that West Germanic order: its perfect is auxiliary + SUPINE +
  // object, so "AI:n har fått 34 poäng" fits the two spans exactly as written and the perfect
  // survives with no register downgrade. `game.toast.aiPlayedWord` is kept in the same tense so
  // the one toast is consistent.
  "game.aiPlayedFor.before": "AI:n har fått",
  "game.aiPlayedFor.points": "poäng",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation at page.tsx:1003. Swedish's
  // INDEFINITE article is a separate word — only the definite article is a suffix — so it can be
  // carried here safely: the fallback reads "AI:n har spelat ett ord" while a real word reads
  // "AI:n har spelat OSTKAKA", and Swedish needs no article before a bare cited word. `ord` is
  // neuter, hence `ett`.
  "game.aWord": "ett ord",
  "game.status.selectExchange": "Välj brickor att byta",
  "game.status.aiMoveReady": "AI:ns drag är klart",
  "game.status.aiThinking": "AI:n tänker",
  "game.status.yourTurn": "Din tur",
  "game.status.waitingForAi": "Väntar på AI:n",
  "game.opponentFallback": "Motståndare",
  "game.waitingSlot": "Väntar",
  "game.sessionExpired": "Sessionen har gått ut",
  "game.lastError": "Senaste fel:",
  "game.newGame": "Nytt parti",
  "game.starting": "Startar...",
  "game.victory": "Du vann!",
  "game.draw": "Oavgjort!",
  "game.gameOver": "Partiet är slut",
  // Rendered by `window.confirm` at page.tsx:671, so these two carry no markup, no styling and no
  // wrapping control — complete sentences in native browser chrome.
  "game.giveUp.ai": "Vill du ge upp det här partiet? AI:n utses till vinnare.",
  "game.giveUp.human":
    "Vill du ge upp det här partiet? Din motståndare utses till vinnare.",
  // Italian needed `avere` plus an invariable object here because a reflexive participle agrees
  // with the SUBJECT. Swedish escapes it more cleanly than Danish does: the Swedish perfect is
  // built with a dedicated SUPINE form (`gett`), which is not a participle at all and by
  // definition never agrees with anything, so no gender is needed. The definite suffix on
  // `partiet` is safe because that noun is fixed at author time, not interpolated.
  "game.gaveUp": "Du har gett upp partiet.",
  "game.error.giveUp": "Det gick inte att ge upp partiet",
  "game.error.newGame": "Det gick inte att starta ett nytt parti",
  "game.error.loadGames": "Partierna kunde inte läsas in.",
  "game.password.updated": "Lösenordet är ändrat.",
  "game.password.failed": "Det gick inte att ändra lösenordet.",
  "game.ai.noRival": "Ingen lämplig gratismotståndare är tillgänglig.",
  "game.ai.timeout": "AI:ns betänketid tog slut.",
  "game.ai.moveFailed": "AI:ns drag misslyckades",
  "game.ws.syncFailed": "Realtidssynkroniseringen misslyckades",
  "game.ws.connectFailed": "Realtidsanslutningen misslyckades",
  "game.ws.authExpired":
    "Inloggningen för realtid har gått ut. Ladda om sidan för att ansluta igen.",
  "game.ws.invalidSession":
    "Den här realtidssessionen är inte giltig. Ladda om sidan för att ansluta igen.",
  "game.ws.unavailable": "Realtidstjänsten är inte tillgänglig. Försök igen.",
  // Byte-identical to English and genuinely the correct native form: `zoom` is an ordinary Swedish
  // loan and stays lowercase because Swedish does not capitalize a common noun. It is carried bare,
  // with no definite suffix, so the loan's en/ett class never has to be settled. The button that
  // holds it is CSS-uppercased anyway (Board.tsx:691).
  "board.zoomNoun": "zoom",
  "header.giveUp": "Ge upp",
  "header.givingUp": "Ger upp...",
  "header.giveUpTooltip": "Ge upp det aktuella partiet",
  // Eight characters in a non-wrapping header cluster, two more than Danish's `Log ud` and level
  // with German — the specific place catalog 6 warned that Swedish is longer. Its in-place
  // replacement `header.loggingOut` is twelve against English's fourteen, so the swap costs the
  // cluster nothing either.
  "header.logout": "Logga ut",
  "header.loggingOut": "Loggar ut...",
  "header.backToBoards": "Tillbaka till partier",
  "header.profile": "Profil",
  "header.games": "Partier",
  // Headline-style label, so the definite `AI:n` is dropped here while the full status line at
  // `game.status.aiThinking` keeps it.
  "overlay.aiThinking": "AI tänker",
  "overlay.searching": "Söker efter drag...",
  // Deliberately DIVERGES from `overlay.bestBadge` below, the way de, is, nl and da diverge: this
  // is a label with room for the noun, that one is a 10px pill.
  "overlay.best": "Bästa draget",
  // A very narrow pill beside a truncating word and a score. Four characters, the predicative
  // superlative rather than the attributive `BÄSTA`, and it cannot be mistaken for untranslated
  // English because Swedish spells it with `ä`.
  "overlay.bestBadge": "BÄST",
  "overlay.filtering":
    "Filtrerar bort svaga och ogiltiga drag innan ett seriöst drag visas...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, two slots each, so this catalog has SIX slot fillers,
// and unlike Danish and Dutch two of them are PHRASES rather than pure nouns. CLDR sv selects
// `one` only at exactly 1 and `other` for everything else INCLUDING ZERO — measured on node
// v26.4.0 / ICU 78.3 and pinned by plural.test.ts — so Swedish writes "0 poäng" and never the
// "0 ponto" that CLDR Portuguese produces next door.
//   point noun   poäng / poäng — Swedish `poäng` (en poäng) is INVARIABLE in number: "1 poäng",
//                "5 poäng", "34 poäng". The two slots therefore carry the SAME word, as Danish
//                `point` and Icelandic `stig` do. That is the language, not an oversight: do not
//                invent a second form to make the slots look distinct.
//   minute noun  minut / minuter — en minut, ordinary plural in -er.
//   tile phrase  bricka vald / brickor valda — the slot carries a two-word PHRASE, as it did for
//                Icelandic and Italian and unlike Danish and Dutch, because a Swedish predicate
//                adjective DOES inflect for number: `vald` in the singular, `valda` in the plural.
//                It therefore cannot be appended outside the helper the way German appends
//                `ausgewählt`. The colon-label shape that keeps the slots pure nouns was available
//                and is deliberately not used: the call site (GameControls.tsx:80-81) is a
//                full-width centred line that wraps freely and is bounded by rack size 7, so the
//                natural Swedish counter reads better than a label.
// `pluralSv` is called and never `pluralEn` or `pluralDa`: sv and en agree over the integers AND
// over fractions, but CLDR da selects `one` for 0.5 and 1.5 while sv selects `other`, so Danish is
// the outlier of the four Germanic two-slot languages here and its caveat is not this catalog's.
export const svFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Bricka ${p.letter}, ${p.points} ` + pluralSv(p.points, "poäng", "poäng"),
  // Category labels agreeing with the implied plural `drag`, which is fixed at author time, so
  // nothing has to agree with an arbitrary runtime count.
  "overlay.stats.tried": (p) => `Testade: ${p.count}`,
  "overlay.stats.valid": (p) => `Giltiga: ${p.count}`,
  "overlay.stats.rejected": (p) => `Avvisade: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `För många förfrågningar. Försök igen om ungefär ${p.minutes} ` +
    pluralSv(p.minutes, "minut", "minuter") +
    ".",
  // `winner` and `loser` receive TILE LETTERS, never a person (draw-result.ts:29-30). `är` is an
  // invariable finite verb and `närmare` an invariable comparative, so neither opaque value takes
  // an article, a definite suffix or an agreeing adjective.
  "draw.reason.closer": (p) => `${p.winner} är närmare A än ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralSv(p.count, "bricka vald", "brickor valda"),
  // `model` is an opaque runtime id, so `med` carries it with no article before it.
  "game.ai.exploring": (p) => `Söker giltiga ord med ${p.model}...`,
  "game.ai.attempt": (p) => `Försök ${p.index}/${p.total} · ${p.label}`,
  // Perfect tense, matching `game.aiPlayedFor.before` in the same toast.
  "game.toast.aiPlayedWord": (p) => `AI:n har spelat ${p.word}`,
  // `name` is an opaque runtime value, so the predicate is a finite verb with no article, no
  // definite suffix and nothing to agree with. `nu` is stylistic here and not the disambiguation
  // Danish needed: Swedish `spelar` is only the verb, while the noun for a player is `spelare`.
  "game.status.opponentPlaying": (p) => `${p.name} spelar nu`,
  // Two full forms, never a suffix trick. The NOUN is invariable here — `ord` is the same in both
  // numbers — so only the adjective marks number: `ogiltigt` in the indefinite neuter singular,
  // `ogiltiga` in the plural.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ogiltiga ord!" : "Ogiltigt ord!",
  "game.ai.routeFailed": (p) => `AI-anropet misslyckades (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `AI-anropet misslyckades (${p.status}), innan streamen startade.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `AI-anropet misslyckades (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, and a Swedish definite suffix on a value
  // whose en/ett class is unknown would be a guess.
  "play.humanQueue.queueFor": (p) => `Kö: ${p.variant}`,
  "queue.room": (p) => `Rum ${p.code}`,
  "history.pageOf": (p) => `Sida ${p.page} av ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `Visar: ${p.from}-${p.to} av ${p.total}`,
  // Colon form for the same reason as `play.humanQueue.queueFor`: `language` is opaque.
  "picker.flagAlt": (p) => `Flagga: ${p.language}`,
};
