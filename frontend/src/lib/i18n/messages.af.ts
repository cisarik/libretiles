// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralAf } from "./plural";

// Frozen AFRIKAANS game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile blokkie (die blokkie, blokkies) · letter letter (die letter, letters) ·
//   rack blokkierak (die blokkierak), bare `rak` only where the tile noun stands beside it ·
//   blank blanko, always carried by the compound blankoblokkie where the PIECE is named ·
//   bag sak (die sak) · board = bord (die bord; the playing surface, stem `bord-` in compounds)
//   AND wedstryd (die wedstryd, wedstryde; the metonym for a saved game) · pass pas (the settled
//   game call, and a usable noun `'n pas`) · points punt / punte, NOT abbreviated ·
//   rival = opponent teenstander (die teenstander).
//
// `bord` really is two words. `bord` is the surface a blokkie sits on; `wedstryd` is the metonym
// for a stored game ("Gestoorde wedstryde", "Terug na wedstryde"). A third word stays apart from
// both: `spel` is the game as a product or ruleset, which is why the picker says `Spelvariant`
// and never `Wedstrydvariant`. `wedstryd` and not `party`: Afrikaans `party` means a political or
// social party, and as a game word it is the exact cognate of catalog 5's frozen Dutch `partij`,
// which D6 forbids harmonizing to. `wedstryd` is also nine characters where `partij` is six, so
// `header.games` and `header.backToBoards` are longer here — reported below.
// `pas` and `ruil` are different moves and keep different words. tile and letter are NOT collapsed
// the way Icelandic collapses them: a `blankoblokkie` is a blokkie carrying no letter that becomes
// one, so the piece and the character it carries need separate words. `blokkie` and not `teël`
// (a ceramic tile, and the cognate of Dutch `tegel`) and not `steen` (a brick, and the cognate of
// catalog 1's frozen German `Stein`).
// THE PASS NOUN EXISTS HERE, as it does in Danish and Swedish and unlike Icelandic, Italian and
// Dutch: `pas` is the settled Afrikaans call in card and board games, so a noun-shaped pass site
// needs no verbal rephrasing — see `game.toast.passRejected`. One knock-on, and it is the same one
// three predecessors reported: the verb `pas` also means "to fit", so `error.conflict` says
// `bots met` and never `pas nie ... nie`. Afrikaans escapes the second knock-on: the passport is
// `paspoort` and never bare `pas`, unlike Danish `et pas` and Icelandic `passi`.
// `beurt` is the TURN and `skuif` is the MOVE; those two are kept apart everywhere.
//
// Register: informal `jy` / `jou`, error messages included. Never `u`. Afrikaans has NO separate
// possessive pronoun — `jou` is both the object and the possessive form — so this catalog contains
// two second-person words in total and no third one exists to get wrong.
// Label style: IMPERATIVE for every control, action label, column heading and accessible name
// (Speel · Pas · Ruil · Kanselleer · Meld af · Open · Soek · Stuur · Kies · Herstel · Gee op).
// ⚠ THE COINCIDE / CONTRAST QUESTION IS ONLY PARTLY ANSWERABLE IN AFRIKAANS, and that is the
// honest answer rather than a forced choice. The Afrikaans verb is INVARIANT: infinitive,
// imperative and every present-tense person share one form, so at a SINGLE-WORD control the two
// candidate styles are the same string and cannot contrast at all. Where they can contrast is
// OBJECT ORDER in a multi-word label — the infinitive puts its object first ("om die ruil te
// bevestig"), the imperative puts it after ("Bevestig ruil") — and every multi-word control here
// takes the imperative order (Bevestig ruil · Herstel zoem · Open instellings · Verlaat ry ·
// Gee op). So the convention is the imperative, the informal `jy` prose is also imperative
// (Kontroleer die gegewens · Knyp om te zoem · Probeer weer), and the two COINCIDE — but for a
// morphological reason rather than a stylistic one, unlike Italian, Danish and Swedish, and
// unlike Dutch, which had a genuine infinitive-versus-bare-stem choice to make.
// Pre-authorized exceptions used: the PAGINATION PAIR (`history.prev` / `history.next` are
// adjectives of the implied `bladsy`), the TOGGLE STATE WORDS (`settings.toggle.on` / `.off`) and
// the BADGE WORDS (`settings.board.active`, `overlay.bestBadge`).
// Progress states take the bare invariant verb plus an ellipsis (Meld aan... · Meld af... ·
// Begin... · Verander...). Because the verb is invariant these differ from their control label
// only by the ellipsis; that is the language, and it keeps `header.loggingOut` at ten characters
// against the English fourteen inside the non-wrapping header cluster.
//
// ORTHOGRAPHY. `ê ô î û ë ï` are real UTF-8 everywhere and are never written as bare ASCII
// (`môre`, `reël`, `sê`, `hê`, `wêreld`). ✔ Measured against locales.ts's `foldForSearch`: every
// one of them is a combining diacritic that NFD decomposes, so picker search folds them correctly
// (môre → more, reël → reel, sê → se). The fold gap that affects Danish `æ` and Icelandic `þ ð`
// does not touch this catalog, and `EXPLICIT_SEARCH_FOLDS` needs no Afrikaans entry.
// ⚠ AND A MEASURED REALITY CHECK, so a reviewer does not read absence as ASCII substitution: of the
// six, only `ê` actually ARISES in this key set, exactly once, in `Sê` at `chat.placeholder`. The
// other five never occur, because no word this interface needs carries them — not because any of
// them was flattened. The only other non-ASCII letters in the file are the `č`/`š` of the two Slavic
// endonyms, which are fixed by project rule.
// NO COMMON NOUN IS CAPITALIZED outside sentence-initial position — Afrikaans is not German here,
// and a capitalized `Blokkie` or `Bord` is the single most visible way this catalog could have
// gone wrong. THE OPPOSITE HALF OF THE SAME RULE: Afrikaans DOES capitalize language names and
// nationality adjectives, in a standalone picker row and in running text alike, so `Afrikaans`,
// `Engels`, `Duits` and `die Nederlandse woordelys` all keep their capital. That sides with Dutch
// and German and against Italian, Icelandic, Danish and Swedish — see `game.lexicon.*`.
// Sentence-initial `'n` stays lowercase and the NEXT word takes the capital ("'n Blankoblokkie wen
// altyd", "'n Gratis teenstander is ... gekies"). That is an Afrikaans orthographic rule, not a
// typo, and it is visible at `draw.subtitle` and `settings.warn.rivalRepair`.
// Compounds are written CLOSED, as one word: spelvariant, koppelvlaktaal, wagwoord, blokkierak,
// beurtstatus, spelerry, premiumvoorkoms, dinktyd. A compound on an ACRONYM stem takes a hyphen
// instead: AI-teenstander, AI-duel, AI-vordering, GPU-las.
// `AI` is a preserved product token. Afrikaans has ONE definite article `die`, no grammatical
// gender and no definite suffix, so the article decision that cost German, Portuguese, Icelandic
// and Italian a gender, Dutch a `de`/`het` choice, Danish an apostrophe (`AI'en`) and Swedish a
// colon (`AI:n`) is FREE here: `die AI` everywhere, and the choice is invisible because there was
// never a second form to pick. Same for `die GPU`.
// Thousands separator is a NO-BREAK SPACE, U+00A0. ✔ Measured with Intl.NumberFormat("af") on node
// v26.4.0 / ICU 78.3: `279 496`. It is written as the escape `279\u00A0496` in `landing.footnote`,
// the way messages.sk.ts, messages.cs.ts, messages.pl.ts, messages.pt.ts and messages.sv.ts write
// it — ⚠ FIVE predecessors and not four. ⛔ The five catalogs that ship a PERIOD — de, is, it, nl,
// da — are NOT the model here, and Dutch's period is the one purely mechanical way this catalog
// could have been got wrong.
//
// ⚠⚠ DUTCH IS THIS LANGUAGE'S PARENT, AND `messages.nl.ts` WAS REQUIRED READING FOR SHAPE.
// Where this catalog deliberately diverges from it, with the four mechanical checks that prove it:
//   · PRONOUNS — Dutch `je` / `jij` / `jouw` against Afrikaans `jy` / `jou`, which has no separate
//     possessive. ✔ CHECKED: zero `jouw`, zero `jij` and zero standalone `je` in any emitted
//     string in this file.
//   · `ij` → `y` — Dutch `wedstrijd` / `IJslands` / `gelijkspel` / `bijgewerkt` against Afrikaans
//     `wedstryd` / `Yslands` / `gelykop` / `bygewerk`. ✔ CHECKED: zero `ij` in any emitted string.
//   · `-lijk` → `-lik` — Dutch `mogelijk` / `tijdelijk` / `dagelijks` against Afrikaans `moontlik`
//     / `tydelik` / `daagliks`. ✔ CHECKED: zero `lijk` in any emitted string.
//   · `z-` → `s-` — Dutch `zak` / `zoeken` / `zet` / `Zweeds` against Afrikaans `sak` / `soek` /
//     `skuif` / `Sweeds`. ⚠ Not mechanically checkable, because `z` is legitimate in Afrikaans
//     loans. A deliberate pass over every z-initial word in this file leaves exactly ONE: `zoem`,
//     the Afrikaans verb and noun for optical zoom, at `board.zoomNoun` and `board.pinchToZoom`.
//     Every other z-word Dutch would use is spelled with `s` here.
//   · THE DOUBLE NEGATIVE, and it is the most systematic difference of all. Dutch negates once;
//     Afrikaans BRACKETS a negative clause with `nie … nie`, and the same bracket closes a clause
//     opened by `geen`, `nooit`, `niks` or `niemand`. That changes clause SHAPE, not just words,
//     and it reaches every `error.*`, every `game.blocker.*`, all thirteen `game.lexicon.*` rows
//     and every `unavailable` string. A single closing `nie` is omitted only where `nie` is
//     already clause-final ("Nie gevind nie." keeps both because the participle precedes it).
//   · THE VERB — Dutch inflects (`ik speel` / `wij spelen`); the Afrikaans verb is INVARIANT
//     (`ek speel` / `ons speel`). Any Dutch plural verb form is wrong here, and this is why the
//     label-style question above collapses.
//   · GENDER — Dutch `de`/`het` does not exist in Afrikaans, so the agreement traps that bit
//     Portuguese, Icelandic, Danish and Swedish cannot bite this catalog at all.
//   · THE SEPARATOR — U+00A0 here against Dutch's period, as noted above.
//   · `board.reset` — Dutch's file comments a workaround for that call site. Afrikaans needs none,
//     and the reason is stated at the key itself rather than inherited.
export const afText: Record<TextKey, string> = {
  // Both values are deliberately byte-identical to English: `Libre Tiles` is a preserved brand, and
  // `premium` is an indeclinable loan modifier that Afrikaans places before the noun exactly as
  // English does. Neither is a skipped key.
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "mense en AI.",
  "landing.lead":
    "Oopbron-woordspel waar spelers regstreeks bymekaarkom, met skerp AI-teenstanders, premiumafwerking op die bord en 'n geskiedenis wat gereed is vir jou volgende wedstryd.",
  "landing.card.ai.title": "AI-duelle",
  // `model` is TRANSLATED here, and for Afrikaans that decision is INVISIBLE: the ordinary
  // Afrikaans noun is `model` (die model), byte-identical to the protected token, so `modelkeuse`
  // is what the translated and the untranslated reading both produce. `chat` is KEPT in all seven
  // measured sites, and for Afrikaans that decision IS observable — the native words are `klets`
  // and `geselsie`, neither of which is `chat` — so it is stated rather than assumed: sites 2 to 7
  // name the product's chat panel, which the player matches against `chat.title`, and `klets`
  // carries a chatter-or-gossip reading that reads wrong over a game panel.
  "landing.card.ai.body": "Premiumwedstryde met modelkeuse",
  "landing.card.queue.title": "Regstreekse ry",
  "landing.card.queue.body": "Intydse sinkronisasie en chat",
  "landing.card.saved.title": "Gestoorde wedstryde",
  "landing.card.saved.body": "Sit wedstryde teen AI of mense voort",
  // The separator is U+00A0 written as an escape, not the period Dutch ships. The number itself is
  // unchanged, and `Open source` plus the Collins name stay exactly as they are.
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 geldige woorde",
  "auth.eyebrow": "Rekening",
  // Afrikaans sentence case collapses English's "Sign in" / "Sign In" pair into one string, so the
  // heading and the tab are deliberately identical rather than artificially distinguished.
  "auth.heading.login": "Meld aan",
  "auth.heading.register": "Skep rekening",
  "auth.tab.login": "Meld aan",
  "auth.tab.register": "Registreer",
  "auth.field.username": "Gebruikersnaam",
  "auth.field.password": "Wagwoord",
  "a11y.chatInput": "Chatboodskap",
  "a11y.dialog.profile": "Profiel",
  "a11y.dialog.games": "Gestoorde wedstryde",
  "a11y.dialog.blank": "Kies 'n letter",
  "a11y.dialog.rival": "Teenstander nie beskikbaar nie",
  // `beurt` is the TURN and `skuif` is the MOVE; this announcer names the turn.
  "a11y.status.turn": "Beurtstatus",
  "a11y.status.aiThinking": "AI-vordering",
  "a11y.rackBlank": "Blankoblokkie",
  "auth.submit.loading": "Meld aan...",
  "auth.submit.login": "Speel nou",
  "auth.submit.register": "Skep rekening en speel",
  "meta.title": "Libre Tiles — woordspel op die web met AI en intydse multispeler",
  // The seventh site of the `chat` token, the one that occurs in prose rather than as a panel
  // name, and all eleven shipped catalogs keep it there. This one does too.
  "meta.description":
    "Oopbron-woordspel met AI-teenstanders, regstreekse wedstryde teen mense, chat en gladde sleep-en-los.",
  "error.checkFields": "Kontroleer die gegewens wat jy gestuur het.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Gebruikersnaam of wagwoord is verkeerd",
  "error.sessionExpired": "Jou sessie is verstreke. Meld weer aan.",
  "error.forbidden": "Jy het nie toestemming daarvoor nie.",
  // Both halves of the bracket are kept even in this two-word fragment: Afrikaans closes the
  // negative clause after the participle, so `nie gevind nie` and never a single `nie`.
  "error.notFound": "Nie gevind nie.",
  // `bots met` and not `pas nie ... nie`: `pas` is this catalog's frozen pass term and also means
  // "to fit", the same knock-on Icelandic, Danish and Swedish reported for their own pass words.
  "error.conflict": "Hierdie aksie bots met die huidige stand van die wedstryd.",
  "error.throttled.unknown": "Te veel versoeke. Wag 'n bietjie en probeer weer.",
  "error.throttled.oneMinute":
    "Te veel versoeke. Probeer oor ongeveer 'n minuut weer.",
  "error.unavailable": "Die diens is tydelik nie beskikbaar nie. Probeer weer.",
  "error.generic": "Iets het verkeerd geloop. Probeer weer.",
  // `se` is the Afrikaans possessive particle, and it is the whole of the genitive: no case ending,
  // no apostrophe as in Danish `AI'ens`, no colon as in Swedish `AI:ns`.
  "settings.timeout.title": "Die AI se dinktyd",
  "settings.timeout.30": "Vinnige blik op die bord",
  "settings.timeout.60": "Gebalanseerde soektog",
  "settings.timeout.120": "Verstekdinktyd",
  "settings.timeout.180": "Toernooitempo",
  "settings.timeout.300": "Langste dinktyd",
  "settings.steps.title": "Soekstappe",
  "settings.steps.10": "Vinnige gereedskap",
  "settings.steps.20": "Meer pogings",
  "settings.steps.30": "Gerigte soektog",
  "settings.steps.50": "Versteksoekdiepte",
  "settings.steps.80": "Maksimum druk",
  "settings.board.title": "Bordoppervlak",
  "settings.board.description":
    "Word op hierdie toestel gestoor en op die bord gebruik.",
  "settings.board.wood": "Hout",
  "settings.board.woodDesc": "Klassieke okkerneutaar",
  "settings.board.black": "Swart",
  "settings.board.blackDesc": "Glansende naglak",
  "settings.board.green": "Groen",
  "settings.board.greenDesc": "Donker toernooivilt",
  // ⚠ THIS TRAP DOES NOT BITE AFRIKAANS, as it did not bite Dutch or Italian, and unlike
  // Portuguese, Icelandic, Danish and Swedish. The badge is a SIBLING span of the surface label
  // (settings/page.tsx:216 against :219), never attributive to it, and an Afrikaans PREDICATE
  // adjective has exactly one form — `aktief` — with no gender, number or definiteness to agree
  // with. So it stays correct beside the noun `Hout` and beside the adjectives `Swart` and `Groen`
  // alike, and no invariable phrase of the kind is, pt and da needed is required.
  "settings.board.active": "Aktief",
  // Toggle state words, not action labels: the pre-authorized exception to the imperative style.
  "settings.toggle.on": "Aan",
  "settings.toggle.off": "Af",
  "settings.shiny.title": "Glanseffek",
  // ⚠ ` as ` here is the ordinary Afrikaans conjunction, not a TypeScript cast. See the note under
  // `draw.reason.closer` and the audit finding reported with this exchange.
  "settings.shiny.description":
    "Skakel die lewende glans af as jy die GPU ligter wil belas.",
  "settings.shiny.onDesc": "Geanimeerde glans op die bord",
  "settings.shiny.offDesc": "Laer GPU-las",
  "settings.premium.title": "Premiumvoorkoms",
  "settings.premium.description":
    "Interaktiewe amberlig vir die wedstryd se kopbalk en die blokkierak.",
  "settings.premium.onDesc": "Interaktiewe premiumpanele",
  "settings.premium.offDesc": "Klassieke donker oppervlakke",
  "settings.backToGame": "Terug na die wedstryd",
  "settings.error.newGame": "Kon nie nou 'n nuwe wedstryd begin nie.",
  "settings.warn.accountSync":
    "Rekeningsinkronisasie is tans nie beskikbaar nie. Die instellings werk steeds plaaslik op hierdie toestel.",
  // Sentence-initial `'n` stays lowercase and `Gratis` takes the capital: that is the Afrikaans
  // rule, not a stray capital on a common word.
  "settings.warn.rivalRepair":
    "'n Gratis teenstander is op hierdie toestel gekies. Die voorkeur op die rekening kon nog nie herstel word nie.",
  "settings.uiLanguage.title": "Koppelvlaktaal",
  "settings.uiLanguage.description":
    "Kieslyste, knoppies en boodskappe. Geld onmiddellik en net op hierdie toestel.",
  // Endonyms, identical in every catalog by project rule. Never Afrikaans exonyms.
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "picker.search": "Soek",
  "picker.noMatch": "Geen resultate nie",
  "picker.uiLanguageLabel": "Koppelvlaktaal",
  "picker.gameVariantLabel": "Spelvariant",
  "settings.gameVariant.title": "Spelvariant",
  // `nooit ... nie` is the same bracket as `nie ... nie`, and the closing `nie` still lands at the
  // end of its own clause — after the relative clause `wat aan die gang is`.
  "settings.gameVariant.description":
    "Blokkies, sak en woordelys. Geld net vir NUWE wedstryde en verander nooit 'n wedstryd wat aan die gang is nie. Dit is nie die koppelvlaktaal nie.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED — and unlike Danish, Swedish,
  // Italian and Icelandic, NOT merely because a picker row is a standalone item: Afrikaans
  // capitalizes a language name in itself, so the `game.lexicon.*` family below keeps the capital
  // in running text too. Afrikaans sides with Dutch and German here.
  // Measured with Intl.DisplayNames("af") on node v26.4.0 / ICU 78.3, then checked as a set with
  // locales.ts's own `foldForSearch`: these twelve have ZERO case-insensitive substring collisions,
  // so no variant label contains another variant's name — which keeps Icelandic the campaign's only
  // outlier. `Afrikaans` is byte-identical to English because Afrikaans has no separate exonym for
  // its own name; that is correct, not a missing translation.
  // ⚠ TWO OF THESE TWELVE ARE THE BEST AVAILABLE PROOF THAT THIS CATALOG WAS NOT ADJUSTED FROM
  // DUTCH: Dutch ships `Zweeds` and `IJslands`, Afrikaans is `Sweeds` and `Yslands`. Those are
  // exactly the `z-` → `s-` and `ij` → `y` shifts, in two picker rows, and no gate in this
  // repository could have caught either one.
  "settings.gameVariant.english": "Engels",
  "settings.gameVariant.slovak": "Slowaaks",
  "settings.gameVariant.czech": "Tsjeggies",
  "settings.gameVariant.polish": "Pools",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italiaans",
  "settings.gameVariant.dutch": "Nederlands",
  "settings.gameVariant.german": "Duits",
  "settings.gameVariant.portuguese": "Portugees",
  "settings.gameVariant.danish": "Deens",
  "settings.gameVariant.swedish": "Sweeds",
  "settings.gameVariant.icelandic": "Yslands",
  "settings.rival.title": "Jou teenstander",
  "settings.rival.description":
    "Die administrateur kies die teenstander vir nuwe wedstryde.",
  "nav.settings": "Instellings",
  "nav.account": "Rekening",
  "profile.subtitle": "Rekeninggegewens en wagwoordsekuriteit op een plek.",
  "profile.email": "E-pos",
  "profile.noEmail": "Geen e-pos gestel nie",
  // Composed as a label against a value that can degrade to `history.unknownDate`. The trap does
  // NOT bite Afrikaans: `sedert` is a bare preposition that governs its complement with no article,
  // no case and no agreement, so "Lid sedert Onbekend" is exactly as awkward as the English
  // original and no more so — pre-existing, not introduced here.
  "profile.memberSince": "Lid sedert",
  "profile.password.subtitle":
    "Verander jou wagwoord sonder om die wedstryd te verlaat.",
  "profile.password.footnote":
    "Sterker wagwoorde maak rekeninge in wedstryde teen mense veiliger.",
  "profile.field.current": "Huidige wagwoord",
  "profile.field.new": "Nuwe wagwoord",
  "profile.field.confirm": "Bevestig nuwe wagwoord",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Huidige wagwoord",
  // `karakters` and not `letters`: here the English `characters` means text characters, and
  // `letter` is this catalog's frozen word for what a blokkie carries.
  "profile.ph.new": "Minstens 8 karakters",
  "profile.ph.confirm": "Herhaal die nuwe wagwoord",
  "profile.submit": "Verander wagwoord",
  "profile.submitting": "Verander...",
  "profile.error.allFields": "Vul al die wagwoordvelde in.",
  "profile.error.mismatch": "Die nuwe wagwoorde stem nie ooreen nie.",
  "play.title": "Kies jou volgende wedstryd",
  "play.lead":
    "Begin 'n premiumduel teen die AI, spring in die regstreekse ry, of maak een van jou gestoorde wedstryde weer oop.",
  "play.ai.eyebrow": "Wedstryd teen AI",
  "play.ai.title": "Speel teen die AI",
  "play.ai.body":
    "Speel teen die huidige AI-teenstander, met die geanimeerde openingstrekking.",
  "play.ai.preparing": "Berei wedstryd voor...",
  "play.rival.unavailable": "Geen teenstander beskikbaar nie",
  "play.humanQueue.eyebrow": "Spelerry",
  "play.humanQueue.title": "Kry 'n regstreekse teenstander",
  // `Is daar niemand nie` — the bracket closes a clause opened by `niemand`, not by `nie`.
  "play.humanQueue.body":
    "Sluit aan by die eerste speler wat wag. Is daar niemand nie, dan wag jou wedstryd in die wagkamer.",
  "play.humanQueue.joining": "Sluit by die ry aan...",
  "play.saved.eyebrow": "Gestoorde wedstryde",
  "play.saved.title": "Gaan voort waar jy opgehou het",
  "play.saved.note":
    "Wedstryde teen die AI en teen mense deel een premiumgeskiedenis.",
  "play.error.catalogEmpty":
    "Die teenstanderkatalogus is leeg. Vul die gratis katalogus sodat wedstryde teen die AI gespeel kan word.",
  "play.error.catalogUnavailable":
    "Die teenstanderkatalogus is tans nie beskikbaar nie. Probeer oor 'n oomblik weer.",
  "play.error.variantUnavailable":
    "Geen speelbare spelvariant is beskikbaar nie. Nuwe wedstryde is geblokkeer totdat 'n speelbare variant gelaai kan word.",
  "play.error.startAi": "Kon nie 'n wedstryd teen die AI begin nie.",
  "play.error.joinQueue": "Kon nie by die spelerry aansluit nie.",
  "play.error.loadGames": "Kon nie jou wedstryde laai nie.",
  // Byte-identical to English because `AI` is a preserved product token, as at `draw.side.ai`.
  "history.filter.ai": "AI",
  "history.filter.human": "Mense",
  "history.filter.all": "Alles",
  "history.sort.recent": "Nuutste",
  "history.refresh": "Verfris",
  "history.loading": "Laai wedstryde",
  "history.empty.title": "Nog geen wedstryde in hierdie filter nie",
  "history.empty.body":
    "Begin 'n nuwe wedstryd, en dit verskyn hier met premiumpaginering, uitslagkentekens en vinnige skakels om verder te speel.",
  "history.noneYet": "Nog geen gestoorde wedstryde nie",
  // Its name lies about its scope. ✔ Measured at four call sites: GameHistoryPanel.tsx:97 and both
  // uses inside `formatJoinedDate` (ProfileModal.tsx:23 and :26) are a missing DATE, and only
  // ProfileModal.tsx:220 is a missing USERNAME — three dates, one username. Afrikaans escapes this
  // the cheapest way of any catalog so far: the language has NO grammatical gender at all, so
  // `Onbekend` cannot be asked to agree with `datum` or with `gebruikersnaam`, and one form is
  // trivially correct at all four sites. Splitting the key would be a `messages.en.ts` change and
  // is not in this slice.
  "history.unknownDate": "Onbekend",
  "history.col.rival": "Teenstander",
  // `Soort` and not `Modus`: this column holds a category (AI-duel / Duel teen mense), which is
  // what an Afrikaans table calls a kind.
  "history.col.mode": "Soort",
  "history.col.result": "Uitslag",
  "history.col.score": "Punte",
  "history.col.moves": "Skuiwe",
  "history.col.updated": "Opgedateer",
  // The eight outcome badges read against `wedstryd` in the row and against the column heading
  // `Uitslag` in the header. That trap CANNOT bite Afrikaans: the language has no grammatical
  // gender, an Afrikaans predicate participle never agrees with anything, and `Wag` and `Aan die
  // gang` are an invariant verb and an invariable phrase. ⚠ Note two participles that take NO
  // `ge-` prefix, because their stems already begin with an unstressed prefix: `verloor` and
  // `verlaat`, against `gewen` and `opgegee`, where `ge-` is present and infixed after the
  // separable `op`. A Dutch-shaped `gelijkspel` would also be wrong twice over here — the word is
  // `gelykop` and it carries the `ij` → `y` shift.
  "history.outcome.waiting": "Wag",
  "history.outcome.active": "Aan die gang",
  "history.outcome.won": "Gewen",
  "history.outcome.lost": "Verloor",
  "history.outcome.draw": "Gelykop",
  "history.outcome.gaveUp": "Opgegee",
  "history.outcome.abandoned": "Verlaat",
  // DEAD KEY: `OUTCOME_META` at GameHistoryPanel.tsx:36-75 has exactly SEVEN arms — waiting,
  // in_progress, won, lost, draw, gave_up, abandoned — and no `unknown`, so the product cannot
  // render this. ✔ Measured. The value is correct and no further effort is spent on it. Its
  // removal belongs to a later slice.
  "history.outcome.unknown": "Onbekend",
  "history.mode.ai": "AI-duel",
  "history.mode.human": "Duel teen mense",
  "history.hint.waitingRoom": "Wagkamer",
  "history.hint.boardReady": "Wedstryd gereed",
  // Fifteen characters, the shortest of any catalog, and the mixed-gender problem that forced
  // Icelandic into a neuter cannot arise: Afrikaans has no gender, and `leeg` is invariable. This
  // is the one place bare `rak` is used instead of `blokkierak`, because `sak` stands beside it and
  // removes the shelf reading.
  "history.endReason.bagEmpty": "Sak en rak leeg",
  "history.endReason.noMoves": "Geen skuiwe beskikbaar nie",
  "history.endReason.sixZero": "Ses beurte sonder punte",
  "history.endReason.gaveUp": "Wedstryd opgegee",
  "history.endReason.queueCancelled": "Ry gekanselleer",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139, where it
  // alternates in the same slot with `history.current`. ✔ The Afrikaans imperative `Open` works in
  // both roles, so that fixed call site costs nothing.
  "history.open": "Open",
  // ⚠ AND UNLIKE DANISH AND SWEDISH, THE PARTNER COSTS NOTHING EITHER. Both of them had to reach
  // for an indeclinable participle-adjective because `aktuel`/`aktuellt` inflects for gender.
  // `Huidige` is the ordinary Afrikaans ATTRIBUTIVE form, and the attributive `-e` does not vary by
  // gender, number or definiteness, so it already agrees with everything and with nothing.
  "history.current": "Huidige",
  // Pagination is a pair of adjectives of the implied `bladsy`, so these two are the one place the
  // imperative label style would be wrong.
  "history.prev": "Vorige",
  "history.next": "Volgende",
  "history.modal.subtitle":
    "Kyk na ou wedstryde, wissel tussen AI en mense, en spring vinnig terug in die spel.",
  "queue.title": "Wag vir 'n teenstander",
  "queue.body":
    "Jou wedstryd is gereed. Dit begin sodra 'n ander speler aansluit.",
  "queue.leave": "Verlaat ry",
  "queue.leaving": "Verlaat ry...",
  "queue.error.dropped": "Die intydse verbinding is verbreek.",
  "queue.error.enter": "Kon nie die wagkamer binnegaan nie.",
  "queue.error.leave": "Kon nie die ry verlaat nie.",
  "draw.eyebrow": "Openingstrekking",
  "draw.title": "Wie open die wedstryd",
  // `nader` is an invariable comparative on a blokkie that is fixed at author time, not a runtime
  // value; the interpolated variant of this sentence is `draw.reason.closer`. Sentence-initial `'n`
  // puts the capital on `Blankoblokkie`.
  "draw.subtitle":
    "Wie die blokkie nader aan A trek, begin. 'n Blankoblokkie wen altyd.",
  "draw.side.you": "Jy",
  // Byte-identical to English because `AI` is a preserved product token.
  "draw.side.ai": "AI",
  "draw.pending": "Trek blokkies uit die sak...",
  // Bare `blanko` rather than the compound: this caption renders directly under the blokkie it
  // labels, where the piece is already named by its position.
  "draw.blankCaption": "blanko",
  "draw.result.youStart": "Jy begin",
  "draw.result.aiStart": "Die AI begin",
  // `Jou` is both the object and the possessive form — Afrikaans has no `jouw`.
  "draw.reason.blankYou": "Jou blankoblokkie wen die trekking.",
  "draw.reason.blankAi": "Die AI het die blankoblokkie getrek.",
  "draw.reason.bothBlank": "Albei blokkies is blanko, so jy begin.",
  "controls.play": "Speel",
  // Three characters, the frozen pass term, and the settled Afrikaans game call. The passport
  // reading that Danish, Swedish and Icelandic had to disambiguate does not exist here: the
  // Afrikaans word for a passport is `paspoort`.
  "controls.pass": "Pas",
  "controls.exchange": "Ruil",
  // Imperative order, object after the verb — the infinitive would be `Ruil bevestig`, and that is
  // the one place in this catalog where the two candidate styles are distinguishable. Thirteen
  // characters against the English sixteen, so this control gains room rather than losing it.
  "controls.confirmExchange": "Bevestig ruil",
  // ⚠ Ten characters against the English six, in a non-wrapping fixed-height grid cell. `Kanselleer`
  // is the standard Afrikaans UI word and there is no shorter honest form, so it is kept correct and
  // the overflow risk is reported rather than abbreviated away.
  "controls.cancel": "Kanselleer",
  // Rendered under a CSS `uppercase` class on the board (Board.tsx:652-653) and as a bare label in
  // the AI overlay, so the value stays lowercase. It is the SAME word as
  // `game.aiPlayedFor.points`: Afrikaans abbreviates `punte` in scoring tables but not in running
  // UI text, and inventing `pte` here would be an abbreviation this language's own interfaces do
  // not use. Five characters, level with Danish `point` and Swedish `poäng`.
  "board.pts": "punte",
  // On-board instructions on the tightest text surface in the product (Board.tsx:669, :671, :677).
  // These three total 41 characters against the English 28 — shorter than Dutch's 47 and Icelandic's
  // 41 is matched exactly; the shortest correct Afrikaans is kept and the overflow is reported.
  // `zoem` is the Afrikaans verb for optical zoom and the only z-initial word in this file.
  "board.pinchToZoom": "Knyp om te zoem",
  // `beweeg` and not `skuif`: `skuif` is this catalog's frozen word for a game MOVE, and it is also
  // the ordinary Afrikaans verb "to slide". Using it here would put both readings on the board.
  "board.dragToPan": "Sleep om te beweeg",
  "board.hide": "Versteek",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in the fixed order
  // [action][noun] at Board.tsx:692-693. ⚠ THAT CALL SITE DOES NOT BITE AFRIKAANS, and the reason
  // is worth stating precisely, because the prediction was that it would. A button label is a
  // MAIN-clause imperative, and Afrikaans main clauses are verb-initial here exactly as Dutch's
  // are; verb-finality only governs subordinate clauses and non-finite verb phrases. German was
  // bitten because its imperative would strand a SEPARABLE prefix (`Setze den Zoom zurück`), and it
  // reached for the loanword `Reset`; Dutch was bitten because its catalog had chosen the
  // INFINITIVE as its control style and had to abandon it. Afrikaans is bitten by neither: `herstel`
  // is INSEPARABLE, so nothing is stranded, and the imperative and the infinitive are the same
  // string, so there is no style to abandon. "Herstel zoem" is simply correct in the order the two
  // spans impose. A separable choice such as `stel terug` WOULD have bitten, which is why this one
  // was made deliberately.
  "board.reset": "Herstel",
  "rack.empty": "Geen blokkies op die rak nie",
  "blank.chooseLetter": "Kies 'n letter vir die blankoblokkie",
  "chat.title": "Wedstrydchat",
  "chat.empty": "Nog geen boodskappe nie.",
  "chat.you": "Jy",
  "chat.unavailable": "Chat nie beskikbaar nie",
  // `Sê` carries a real circumflex, never the ASCII `Se`, which is a different Afrikaans word.
  "chat.placeholder": "Sê iets",
  "chat.send": "Stuur",
  "game.lexicon.collins2019": "Nie in Collins Scrabble Words 2019 nie",
  "game.lexicon.slovak": "Nie in die Slowaakse woordelys nie",
  "game.lexicon.czech": "Nie in die Tsjeggiese woordelys nie",
  "game.lexicon.polish": "Nie in die Poolse woordelys nie",
  // ⚠ ELEVEN language rows, not twelve: there is no `game.lexicon.english`, because the English
  // variant's `lexicon_id` is `collins2019` and its row names the dictionary rather than a
  // language. All eleven take the language name plus the attributive `-e`, which in Afrikaans is
  // one form for every gender, number and definiteness, so agreement with `woordelys` is free —
  // and CAPITALIZED, because Afrikaans capitalizes a nationality word in running text as well as
  // in a picker row. That is where this catalog parts company with Italian, Icelandic, Danish and
  // Swedish and agrees with Dutch and German.
  // ⭐ AND THE `afrikaans` ROW NEEDS NO EXCEPTION AT ALL. German, Portuguese, Danish and Swedish
  // each had to except it because no adjective is built on the name in their languages; Icelandic,
  // Italian and Dutch did not. For THIS catalog the name is the native language name, `Afrikaanse`
  // is the ordinary attributive form of it, and the row is the most regular of the eleven rather
  // than the irregular one.
  "game.lexicon.afrikaans": "Nie in die Afrikaanse woordelys nie",
  "game.lexicon.italian": "Nie in die Italiaanse woordelys nie",
  "game.lexicon.dutch": "Nie in die Nederlandse woordelys nie",
  "game.lexicon.german": "Nie in die Duitse woordelys nie",
  "game.lexicon.portuguese": "Nie in die Portugese woordelys nie",
  "game.lexicon.danish": "Nie in die Deense woordelys nie",
  "game.lexicon.swedish": "Nie in die Sweedse woordelys nie",
  "game.lexicon.icelandic": "Nie in die Yslandse woordelys nie",
  "game.lexicon.unknown": "Nie in die spel se woordelys nie",
  "game.blocker.auth.title": "Teenstander se aanmelding het misluk",
  "game.blocker.auth.body":
    "Hierdie gratis teenstander kon nie aanmeld nie. Wissel na 'n ander gratis teenstander, of probeer later weer.",
  "game.blocker.rate.title": "Teenstander het sy perk bereik",
  "game.blocker.rate.body":
    "Hierdie gratis teenstander het sy versoekperk bereik. Wissel na 'n ander gratis teenstander, of probeer later weer.",
  "game.blocker.unavail.title": "Teenstander is nie beskikbaar nie",
  "game.blocker.unavail.body":
    "Hierdie gratis teenstander is tydelik nie beskikbaar nie. Wissel na 'n ander gratis teenstander, of probeer later weer.",
  "game.blocker.badge.auth": "Aanmelding",
  "game.blocker.badge.rate": "Perk bereik",
  // `Onbeskikbaar` and not `Nie beskikbaar nie`: on a tracked uppercase eyebrow the single negative
  // ADJECTIVE is both correct Afrikaans and twelve characters instead of eighteen, and it needs no
  // bracket at all. The prose bodies above keep the bracket, where the clause requires it.
  "game.blocker.badge.unavail": "Onbeskikbaar",
  "game.blocker.close": "Sluit",
  "game.blocker.openSettings": "Open instellings",
  "game.toast.invalidPlacement": "Ongeldige plasing",
  "game.toast.invalidWords": "Ongeldige woorde",
  "game.toast.moveRejected": "Skuif verwerp",
  "game.toast.exchangeRejected": "Ruil verwerp",
  // No verbal rephrasing is needed here, unlike in Icelandic, Italian and Dutch: `'n pas` is a real
  // Afrikaans game noun, so this heading keeps the English noun shape.
  "game.toast.passRejected": "Pas verwerp",
  // ⚠ THE ONE PROTECTED-TOKEN SITE WHERE THIS CATALOG DIVERGES FROM ALL ELEVEN PREDECESSORS, and
  // not on `chat`. Afrikaans has native words for the connection states — `aanlyn` and `vanlyn` —
  // so `offline` is translated while the product-concept token `chat` beside it is not.
  "game.toast.chatOffline": "Chat is vanlyn",
  "game.toast.aiPasses": "Die AI pas",
  "game.toast.aiExchanged": "Die AI het blokkies geruil",
  "game.toast.aiExchangedBody":
    "Die AI het die rak vernuwe en die beurt gebruik.",
  "game.toast.aiPassedBody": "Kon nie 'n geldige skuif vind nie — jou beurt!",
  // ⚠ THIS CALL SITE BITES AFRIKAANS, as it bit German and Dutch, and the mechanism is confirmed.
  // page.tsx:338 composes `[before] <span>{score}</span> [points]` with the score FIXED in the
  // middle and nothing able to follow the counted noun, and the Afrikaans PERFECT puts its
  // participle at the very end of the clause ("Die AI het 34 punte behaal"), which those two spans
  // cannot express. ⚠ AND THE ESCAPE IS NOT GERMAN'S OR DUTCH'S. Both of them fell back to the
  // SIMPLE PAST (`spielte`, `scoorde`); Afrikaans has a well-formed simple past for only a handful
  // of verbs — `was`, `had`, `kon`, `wou`, `moes`, `sou`, `wis` — and `behaal` is not among them,
  // so that escape does not exist. What is available is the PRESENT tense, which is finite and
  // therefore verb-second, so its object follows it: "Die AI behaal 34 punte". `.points` stays the
  // bare counted noun, consistent with `board.pts` and with GLOSSARY D6, and the cost is a tense
  // rather than a register. `game.toast.aiPlayedWord` is kept in the same tense so the one toast is
  // consistent; the exchange and pass toasts above are separate toasts and keep the perfect.
  "game.aiPlayedFor.before": "Die AI behaal",
  "game.aiPlayedFor.points": "punte",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation at page.tsx:1003. The indefinite
  // article `'n` is a separate word in Afrikaans and is carried here, so the fallback reads "Die AI
  // speel 'n woord" while a real word reads "Die AI speel KAAS" — Afrikaans needs no article before
  // a bare cited word. Eight characters, between Swedish's seven and German's eight.
  "game.aWord": "'n woord",
  "game.status.selectExchange": "Kies blokkies om te ruil",
  "game.status.aiMoveReady": "Die AI se skuif is gereed",
  "game.status.aiThinking": "Die AI dink",
  "game.status.yourTurn": "Jou beurt",
  "game.status.waitingForAi": "Wag vir die AI",
  "game.opponentFallback": "Teenstander",
  "game.waitingSlot": "Wag",
  "game.sessionExpired": "Sessie verstreke",
  "game.lastError": "Laaste fout:",
  "game.newGame": "Nuwe wedstryd",
  "game.starting": "Begin...",
  "game.victory": "Jy wen!",
  "game.draw": "Gelykop!",
  "game.gameOver": "Wedstryd verby",
  // ✔ Rendered by `window.confirm` at page.tsx:671, so these two carry no markup, no CSS width and
  // no wrapping control — complete sentences in native browser chrome. ` as ` here is the ordinary
  // Afrikaans conjunction and `aangewys` is the clause-final participle, which this string can
  // afford because the whole sentence is one value.
  "game.giveUp.ai": "Gee hierdie wedstryd op? Die AI word as die wenner aangewys.",
  "game.giveUp.human":
    "Gee hierdie wedstryd op? Jou teenstander word as die wenner aangewys.",
  // Italian needed `avere` plus an invariable object here because a reflexive participle agrees
  // with the SUBJECT. Afrikaans needs nothing: `het` + `opgegee` never agrees with anything, the
  // language has no gender to guess, and the double negative does not reach this sentence because
  // it is not negative. ⚠ Note the `ge-` the prompt flagged: `opgee` infixes it after the separable
  // prefix, giving `opgegee` and never `geopgee`.
  "game.gaveUp": "Jy het die wedstryd opgegee.",
  "game.error.giveUp": "Kon nie hierdie wedstryd opgee nie",
  "game.error.newGame": "Kon nie 'n nuwe wedstryd begin nie",
  "game.error.loadGames": "Kon nie die wedstryde laai nie.",
  "game.password.updated": "Wagwoord is verander.",
  "game.password.failed": "Kon nie die wagwoord verander nie.",
  "game.ai.noRival": "Geen geskikte gratis teenstander is beskikbaar nie.",
  "game.ai.timeout": "Die AI se dinktyd is verstreke.",
  "game.ai.moveFailed": "Die AI se skuif het misluk",
  "game.ws.syncFailed": "Intydse sinkronisasie het misluk",
  "game.ws.connectFailed": "Intydse verbinding het misluk",
  // `om weer te verbind` is an infinitive clause, and Afrikaans puts its verb last — the one place
  // verb-finality is plainly visible in this catalog, alongside `voordat` at `overlay.filtering`.
  "game.ws.authExpired":
    "Die aanmelding vir intydse verbinding is verstreke. Herlaai die bladsy om weer te verbind.",
  "game.ws.invalidSession":
    "Hierdie intydse sessie is nie geldig nie. Herlaai die bladsy om weer te verbind.",
  "game.ws.unavailable": "Die intydse diens is nie beskikbaar nie. Probeer weer.",
  // ⚠ NOT byte-identical to the `zoom` that nl, da, sv, it and pt all ship. `zoem` is the Afrikaans
  // verb and noun for optical zoom, it stays lowercase because Afrikaans does not capitalize a
  // common noun, and it is the single z-initial word in this file — the deliberate exception to the
  // `z-` → `s-` pass. The button that holds it is CSS-uppercased anyway (Board.tsx:691).
  "board.zoomNoun": "zoem",
  "header.giveUp": "Gee op",
  "header.givingUp": "Gee op...",
  "header.giveUpTooltip": "Gee hierdie wedstryd op",
  // Seven characters in the non-wrapping header cluster, tying Icelandic and under Dutch's nine.
  // ⭐ Its in-place swap partner `header.loggingOut` is TEN — shorter than every shipped catalog
  // except Italian's nine, and four under the English fourteen — so the swap costs the cluster
  // nothing. The invariant verb is what buys that: no progressive form has to be built.
  "header.logout": "Meld af",
  "header.loggingOut": "Meld af...",
  // Eighteen characters, and `wedstryde` is the reason: it is three longer than the `partij` family
  // every other Germanic catalog could use. ✔ This value reaches only an `aria-label` and a
  // nowrap TOOLTIP beside an icon-only button, so the length is not a layout risk here.
  "header.backToBoards": "Terug na wedstryde",
  "header.profile": "Profiel",
  "header.games": "Wedstryde",
  // Headline-style label, so the article is dropped here while the full status line at
  // `game.status.aiThinking` keeps `Die`.
  "overlay.aiThinking": "AI dink",
  "overlay.searching": "Soek skuiwe...",
  // Deliberately DIVERGES from `overlay.bestBadge` below, the way de, is, nl, da and sv diverge:
  // this is a label with room for the noun, that one is a 10px pill.
  "overlay.best": "Beste skuif",
  // A very narrow `text-[10px] font-black shrink-0` pill beside a truncating word and a score. FIVE
  // characters — the shortest form that cannot be read as untranslated English, since Afrikaans
  // spells the superlative `beste` and a bare `BEST` would be byte-identical to the English.
  "overlay.bestBadge": "BESTE",
  // `voordat` opens a subordinate clause, so `gewys word` lands at the end of it: Afrikaans
  // verb-finality, in the one string long enough to show it.
  "overlay.filtering":
    "Filtreer swak en ongeldige skuiwe uit voordat 'n ernstige skuif gewys word...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, two slots each, so this catalog has SIX slot fillers
// and every one of them is a PURE NOUN rather than a phrase — the nl/da position and not the
// is/it/sv one. The reason is structural: an Afrikaans predicate participle does not inflect for
// number, so `gekies` is appended OUTSIDE the helper the way German appends `ausgewählt`, and the
// slot never has to carry a two-word phrase.
// ✔ MEASURED on node v26.4.0 / ICU 78.3 and pinned by plural.test.ts: CLDR af has exactly TWO
// categories and selects `one` only at i = 1, `other` for everything else INCLUDING ZERO, so
// Afrikaans writes "0 punte" and never the "0 ponto" that CLDR Portuguese produces next door.
// Fractions are `other` as in English and Swedish — ⛔ Danish is the fraction outlier of the four
// two-slot Germanic languages (da 0.5 selects `one`), so the caveat on `pluralDa` is not this
// catalog's caveat.
//   point noun   punt / punte — ordinary plural in -e, and NOT the Dutch `punten`.
//   minute noun  minuut / minute — ordinary plural in -e, and NOT the Dutch `minuten`.
//   tile noun    blokkie / blokkies — a diminutive, so its plural takes -s.
// `pluralAf` is called and never `pluralEn` and never `pluralNl`: all three agree over the
// integers, but the helpers are separate bodies precisely so a future CLDR divergence in one
// cannot silently change another.
export const afFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Blokkie ${p.letter}, ${p.points} ` + pluralAf(p.points, "punt", "punte"),
  // Noun and invariable-participle labels, so nothing has to agree with an arbitrary runtime count.
  // `Pogings` and not the participle `Probeer`, which is identical to the imperative and would read
  // as a button beside a number.
  "overlay.stats.tried": (p) => `Pogings: ${p.count}`,
  "overlay.stats.valid": (p) => `Geldig: ${p.count}`,
  "overlay.stats.rejected": (p) => `Verwerp: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Te veel versoeke. Probeer oor ongeveer ${p.minutes} ` +
    pluralAf(p.minutes, "minuut", "minute") +
    " weer.",
  // ✔ `winner` and `loser` receive TILE LETTERS, never a person (draw-result.ts:29-30). `is` is an
  // invariant verb and `nader` an invariable comparative, so neither opaque value takes an article
  // or an agreeing word. ⚠ THE ` as ` HERE IS THE AFRIKAANS CONJUNCTION "than", not a TypeScript
  // cast: it is followed by an interpolation rather than a capitalized identifier, so the
  // cast-shaped audit line of the validation ladder does not fire on it. It would fire on a correct
  // Afrikaans sentence such as "Speel as Afrikaans", which is why that line must never be run
  // against prose.
  "draw.reason.closer": (p) => `${p.winner} is nader aan A as ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralAf(p.count, "blokkie", "blokkies") + " gekies",
  // `model` is an opaque runtime id, so `met` carries it with no article before it.
  "game.ai.exploring": (p) => `Soek geldige woorde met ${p.model}...`,
  "game.ai.attempt": (p) => `Poging ${p.index}/${p.total} · ${p.label}`,
  // Present tense, matching `game.aiPlayedFor.before` in the same toast. The perfect would be
  // "Die AI het KAAS gespeel", which this string could express — it is used in the present only so
  // the one toast has one tense.
  "game.toast.aiPlayedWord": (p) => `Die AI speel ${p.word}`,
  // `name` is an opaque runtime value, so the predicate is an invariant finite verb with nothing to
  // agree with. Bare `speel` is unambiguous here, unlike Danish `spiller` and Swedish `spelar`
  // beside their nouns for a player: the Afrikaans noun is `speler`, a different word.
  "game.status.opponentPlaying": (p) => `${p.name} speel nou`,
  // Two full forms, never a suffix trick — and unlike Dutch only the NOUN changes. Dutch alternates
  // `ongeldig woord` with `ongeldige woorden`, because its adjective inflects for definiteness and
  // number; the Afrikaans attributive `-e` does neither, so `Ongeldige` is correct in both.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ongeldige woorde!" : "Ongeldige woord!",
  "game.ai.routeFailed": (p) => `Die AI-aanroep het misluk (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `Die AI-aanroep het misluk (${p.status}), nog voor die stroom begin het.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `Die AI-aanroep het misluk (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, and although Afrikaans has only one definite
  // article, prefixing an opaque value with `die` would still assert that the value is a bare noun
  // rather than an already-determined phrase.
  "play.humanQueue.queueFor": (p) => `Ry: ${p.variant}`,
  "queue.room": (p) => `Kamer ${p.code}`,
  "history.pageOf": (p) => `Bladsy ${p.page} van ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `Wys: ${p.from}-${p.to} van ${p.total}`,
  // Colon form for the same reason as `play.humanQueue.queueFor`: `language` is opaque.
  "picker.flagAlt": (p) => `Vlag: ${p.language}`,
};
