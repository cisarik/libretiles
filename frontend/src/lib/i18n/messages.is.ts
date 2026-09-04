// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralIs } from "./plural";

// Frozen ICELANDIC game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile stafur · letter stafur · rack grind · blank jóker · bag poki ·
//   board = borð (the physical playing surface) AND viðureign (a saved game) ·
//   pass passa (verb only) · points stig · rival = opponent mótherji.
//
// tile and letter DELIBERATELY COLLAPSE into one word, the way Slovak collapses them into
// `písmeno`. Icelandic word-game usage really does say `stafur` for the piece on the grind and
// for the letter it carries, it is the shortest correct term on the tightest surfaces, and
// tile/letter is not one of the three splits this campaign mandates. Consequence: where the
// English means a TEXT CHARACTER rather than a game piece, this catalog writes `tákn` instead —
// see `profile.ph.new`.
// `borð` really is two words. `borð` is the surface a stafur sits on; `viðureign` is the metonym
// for a stored game ("Vistaðar viðureignir", "Aftur í viðureignirnar").
// `passa` and `skipta` are different moves and keep different words. `passa` is frozen as a VERB
// only: the Icelandic noun `passi` means a passport, so every noun-shaped pass site is phrased
// verbally — see `game.toast.passRejected`. A knock-on: `passa` also means "to fit", so
// `error.conflict` uses `stangast á við` rather than `passar ekki við`.
// A `jóker` is a stafur that carries no letter and becomes one.
// `leikur` is the MOVE (as in chess), never the game — that is what forces `viðureign` above.
//
// Register: informal `þú` / `þinn` throughout, error messages included. Modern Icelandic has no
// living formal address at all (`þér` is archaic), so unlike German or Portuguese this was not a
// choice between two usable registers.
// Label style: INFINITIVE for every control, action label, column heading and accessible name
// (Spila · Passa · Skipta · Hætta við · Skrá út · Opna); `þú` IMPERATIVE only for prose sentences
// and hero headings (Veldu næstu viðureign). Never mixed inside one strip.
// `premium` is kept untranslated as product chrome and stays an indeclinable modifier, hyphenated
// in compounds the way Icelandic joins a foreign stem: Premium-útlit, premium-viðureignir.
// `AI` is a preserved product token, so it is never rewritten, and it takes FEMININE agreement,
// matching `gervigreind` — visible at `game.giveUp.ai` ("úrskurðuð").
export const isText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  // Deliberately byte-identical: a preserved brand plus the indeclinable `premium` modifier.
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "fólk og AI.",
  "landing.lead":
    "Open-source orðaleikur með pörun í beinni, beittum AI-mótherjum, premium-borði og yfirliti sem er tilbúið fyrir næstu viðureign.",
  "landing.card.ai.title": "AI-einvígi",
  // `model` is TRANSLATED here: on a landing card it is an ordinary noun, and Icelandic `líkan`
  // carries no competing reading (a fashion model is `fyrirsæta`). The five `chat` sites below
  // keep the English token, because each of them names the product's chat panel.
  "landing.card.ai.body": "Premium-viðureignir og val á líkani",
  "landing.card.queue.title": "Biðröð í beinni",
  "landing.card.queue.body": "Samstilling í rauntíma og chat",
  "landing.card.saved.title": "Vistaðar viðureignir",
  "landing.card.saved.body": "Halda áfram viðureign við AI eða fólk",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279.496 gild orð",
  "auth.eyebrow": "Aðgangur",
  "auth.heading.login": "Innskráning",
  "auth.heading.register": "Nýr aðgangur",
  "auth.tab.login": "Skrá inn",
  "auth.tab.register": "Nýskrá",
  "auth.field.username": "Notandanafn",
  "auth.field.password": "Lykilorð",
  "a11y.chatInput": "Chat-skilaboð",
  "a11y.dialog.profile": "Prófíll",
  "a11y.dialog.games": "Vistaðar viðureignir",
  "a11y.dialog.blank": "Velja staf",
  "a11y.dialog.rival": "Mótherji ekki í boði",
  "a11y.status.turn": "Staða leiks",
  "a11y.status.aiThinking": "Framgangur AI",
  "a11y.rackBlank": "Jóker",
  "auth.submit.loading": "Skrái inn...",
  "auth.submit.login": "Spila núna",
  "auth.submit.register": "Búa til aðgang og spila",
  "meta.title":
    "Libre Tiles — orðaleikur á vefnum með AI og fjölspilun í beinni",
  "meta.description":
    "Open-source orðaleikur með AI-mótherjum, viðureignum við fólk í beinni, chat og fágaðri drag-and-drop spilun.",
  "error.checkFields": "Athugaðu gögnin sem þú sendir.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Notandanafn eða lykilorð er ekki rétt",
  "error.sessionExpired":
    "Innskráningin þín er útrunnin. Skráðu þig inn aftur.",
  "error.forbidden": "Þú hefur ekki heimild til þessa.",
  "error.notFound": "Fannst ekki.",
  // `stangast á við` and not `passar ekki við`: `passa` is the frozen pass term.
  "error.conflict":
    "Þessi aðgerð stangast á við núverandi stöðu viðureignarinnar.",
  "error.throttled.unknown":
    "Of margar fyrirspurnir. Bíddu í smá stund og reyndu aftur.",
  "error.throttled.oneMinute":
    "Of margar fyrirspurnir. Reyndu aftur eftir um eina mínútu.",
  "error.unavailable":
    "Þjónustan er ekki í boði í augnablikinu. Reyndu aftur.",
  "error.generic": "Eitthvað fór úrskeiðis. Reyndu aftur.",
  "settings.timeout.title": "Umhugsunartími AI",
  "settings.timeout.30": "Fljótleg borðlesning",
  "settings.timeout.60": "Leit í jafnvægi",
  "settings.timeout.120": "Sjálfgefinn umhugsunartími",
  "settings.timeout.180": "Keppnistaktur",
  "settings.timeout.300": "Lengsta umhugsun",
  "settings.steps.title": "Leitarþrep",
  "settings.steps.10": "Snögg verkfæri",
  "settings.steps.20": "Fleiri tilraunir",
  "settings.steps.30": "Markviss leit",
  "settings.steps.50": "Sjálfgefin leitardýpt",
  "settings.steps.80": "Hámarksþrýstingur",
  "settings.board.title": "Yfirborð borðsins",
  "settings.board.description": "Vistað á þessu tæki og notað á borðinu.",
  "settings.board.wood": "Tré",
  "settings.board.woodDesc": "Klassísk valhnotuáferð",
  "settings.board.black": "Svart",
  "settings.board.blackDesc": "Glansandi næturlakk",
  "settings.board.green": "Grænt",
  "settings.board.greenDesc": "Dökkur keppnisflóki",
  // A badge, not an adjective: `Tré` is a neuter NOUN while `Svart` and `Grænt` are neuter
  // adjectives, so no single agreeing form heads all three rows. An invariable phrase avoids it.
  "settings.board.active": "Í notkun",
  "settings.toggle.on": "Kveikt",
  "settings.toggle.off": "Slökkt",
  "settings.shiny.title": "Glansáhrif",
  "settings.shiny.description":
    "Slökktu á lifandi glansinum ef þú vilt minna álag á GPU.",
  "settings.shiny.onDesc": "Kvikur glans á borðinu",
  "settings.shiny.offDesc": "Minna álag á GPU",
  "settings.premium.title": "Premium-útlit",
  "settings.premium.description":
    "Gagnvirkt gulbrúnt ljós fyrir haus viðureignarinnar og grindina.",
  "settings.premium.onDesc": "Gagnvirk premium-spjöld",
  "settings.premium.offDesc": "Klassísk dökk yfirborð",
  "settings.backToGame": "Aftur í viðureignina",
  "settings.error.newGame": "Ekki var hægt að hefja nýja viðureign núna.",
  "settings.warn.accountSync":
    "Samstilling aðgangs er ekki í boði núna. Stillingarnar virka samt staðbundið á þessu tæki.",
  "settings.warn.rivalRepair":
    "Gjaldfrjáls mótherji er valinn á þessu tæki. Ekki var hægt að laga stillinguna á aðganginum enn.",
  "settings.uiLanguage.title": "Tungumál viðmóts",
  "settings.uiLanguage.description":
    "Valmyndir, hnappar og skilaboð. Tekur gildi strax og aðeins á þessu tæki.",
  // Endonyms, identical in every catalog by project rule. Never Icelandic exonyms.
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "picker.search": "Leita",
  "picker.noMatch": "Engin samsvörun",
  "picker.uiLanguageLabel": "Tungumál viðmóts",
  "picker.gameVariantLabel": "Afbrigði viðureignar",
  "settings.gameVariant.title": "Afbrigði viðureignar",
  "settings.gameVariant.description":
    "Stafir, poki og orðasafn. Gildir aðeins um NÝJAR viðureignir og breytir aldrei viðureign sem er í gangi. Þetta er ekki tungumál viðmótsins.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED because these are standalone
  // picker rows; Icelandic writes a language name lowercase in running text, which is what the
  // `game.lexicon.*` family below does.
  // ⚠ `enska` is a substring of two of its siblings, `hollenska` and `íslenska`, and correct
  // Icelandic cannot avoid either. Swedish is `Sænska` and not `Svenska`: `sænska` is the
  // Icelandic form built on the adjective `sænskur`, `svenska` is the Swedish endonym, and
  // choosing it would have made `enska` a substring of a third sibling for no gain.
  "settings.gameVariant.english": "Enska",
  "settings.gameVariant.slovak": "Slóvakíska",
  "settings.gameVariant.czech": "Tékkneska",
  "settings.gameVariant.polish": "Pólska",
  "settings.gameVariant.afrikaans": "Afríkanska",
  "settings.gameVariant.italian": "Ítalska",
  "settings.gameVariant.dutch": "Hollenska",
  "settings.gameVariant.german": "Þýska",
  "settings.gameVariant.portuguese": "Portúgalska",
  "settings.gameVariant.danish": "Danska",
  "settings.gameVariant.swedish": "Sænska",
  "settings.gameVariant.icelandic": "Íslenska",
  "settings.rival.title": "Mótherjinn þinn",
  "settings.rival.description":
    "Kerfisstjórinn velur mótherja fyrir nýjar viðureignir.",
  "nav.settings": "Stillingar",
  "nav.account": "Aðgangur",
  "profile.subtitle":
    "Upplýsingar um aðganginn og öryggi lykilorðs á einum stað.",
  "profile.email": "Netfang",
  "profile.noEmail": "Ekkert netfang skráð",
  "profile.memberSince": "Meðlimur frá",
  "profile.password.subtitle":
    "Breyttu lykilorðinu þínu án þess að fara úr viðureigninni.",
  "profile.password.footnote":
    "Sterkari lykilorð gera aðganga í viðureignum við fólk öruggari.",
  "profile.field.current": "Núverandi lykilorð",
  "profile.field.new": "Nýtt lykilorð",
  "profile.field.confirm": "Staðfesta nýtt lykilorð",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Núverandi lykilorð",
  // `tákn` and not `stafir`: here the English `characters` means text characters, and `stafur` is
  // this catalog's frozen word for a game tile.
  "profile.ph.new": "Að minnsta kosti 8 tákn",
  "profile.ph.confirm": "Sláðu nýja lykilorðið aftur",
  "profile.submit": "Breyta lykilorði",
  "profile.submitting": "Breyti...",
  "profile.error.allFields": "Fylltu út alla lykilorðareitina.",
  "profile.error.mismatch": "Nýju lykilorðin stemma ekki.",
  "play.title": "Veldu næstu viðureign",
  "play.lead":
    "Byrjaðu premium-einvígi við AI, farðu í biðröðina í beinni eða opnaðu eina af vistuðu viðureignunum þínum.",
  "play.ai.eyebrow": "Viðureign við AI",
  "play.ai.title": "Spilaðu við AI",
  "play.ai.body":
    "Spilaðu við núverandi AI-mótherja, með kvikum upphafsdrætti.",
  "play.ai.preparing": "Undirbý viðureign...",
  "play.rival.unavailable": "Enginn mótherji í boði",
  "play.humanQueue.eyebrow": "Biðröð leikmanna",
  "play.humanQueue.title": "Finndu mótherja í beinni",
  "play.humanQueue.body":
    "Farðu í viðureign við fyrsta leikmanninn sem bíður. Ef enginn er þar bíður viðureignin þín í biðstofunni.",
  "play.humanQueue.joining": "Fer í biðröðina...",
  "play.saved.eyebrow": "Vistaðar viðureignir",
  "play.saved.title": "Haltu áfram þar sem þú hættir",
  "play.saved.note":
    "Viðureignir við AI og við fólk deila sama premium-yfirlitinu.",
  "play.error.catalogEmpty":
    "Mótherjaskráin er tóm. Fylltu gjaldfrjálsu skrána til að geta spilað við AI.",
  "play.error.catalogUnavailable":
    "Mótherjaskráin er ekki í boði í augnablikinu. Reyndu aftur eftir smá stund.",
  "play.error.variantUnavailable":
    "Ekkert spilanlegt afbrigði viðureignar er í boði. Ekki er hægt að búa til nýja viðureign fyrr en spilanlegt afbrigði hleðst.",
  "play.error.startAi": "Ekki var hægt að hefja viðureign við AI.",
  "play.error.joinQueue": "Ekki var hægt að fara í biðröð leikmanna.",
  "play.error.loadGames": "Ekki var hægt að hlaða viðureignunum þínum.",
  "history.filter.ai": "AI",
  "history.filter.human": "Fólk",
  "history.filter.all": "Allt",
  "history.sort.recent": "Nýjustu",
  "history.refresh": "Uppfæra",
  "history.loading": "Hleð viðureignum",
  "history.empty.title": "Engar viðureignir í þessari síu enn",
  "history.empty.body":
    "Byrjaðu nýja viðureign og hún birtist hér með premium-flettingu, úrslitamerkjum og hröðum tenglum til að halda áfram.",
  "history.noneYet": "Engar vistaðar viðureignir enn",
  // Its name lies about its scope: this is also the fallback for a MISSING USERNAME at
  // ProfileModal.tsx:220, not only for a missing date. Icelandic's unmarked standalone form is the
  // NEUTER, which happens to be correct for both `dagsetning` (f.) and `notandanafn` (n.), so this
  // trap costs Icelandic nothing. Splitting the key would be a `messages.en.ts` change.
  "history.unknownDate": "Óþekkt",
  "history.col.rival": "Mótherji",
  "history.col.mode": "Hamur",
  "history.col.result": "Úrslit",
  "history.col.score": "Stig",
  "history.col.moves": "Leikir",
  "history.col.updated": "Uppfært",
  // The eight outcome badges are NOUNS or invariable phrases, so none of them has to agree with
  // `viðureign` (f.) in one call site and an implied neuter in another.
  "history.outcome.waiting": "Í bið",
  "history.outcome.active": "Í gangi",
  "history.outcome.won": "Sigur",
  "history.outcome.lost": "Tap",
  "history.outcome.draw": "Jafntefli",
  "history.outcome.gaveUp": "Uppgjöf",
  "history.outcome.abandoned": "Yfirgefið",
  "history.outcome.unknown": "Óþekkt",
  "history.mode.ai": "Einvígi við AI",
  "history.mode.human": "Einvígi við fólk",
  "history.hint.waitingRoom": "Biðstofa",
  "history.hint.boardReady": "Viðureign tilbúin",
  // `poki` (m.) and `grind` (f.) are different genders, so the shared predicate takes the neuter
  // many-form, which is what Icelandic does with mixed-gender subjects.
  "history.endReason.bagEmpty": "Poki og grind tóm",
  "history.endReason.noMoves": "Enginn leikur í boði",
  "history.endReason.sixZero": "Sex leikir án stiga",
  "history.endReason.gaveUp": "Gefist upp",
  "history.endReason.queueCancelled": "Biðröð afturkölluð",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139. The
  // infinitive works in both roles, so this fixed call site cost nothing.
  "history.open": "Opna",
  "history.current": "Núverandi",
  // Pagination is a pair of adjectives agreeing with the implied `síða` (f.), so these two are the
  // one place the infinitive label style would be wrong.
  "history.prev": "Fyrri",
  "history.next": "Næsta",
  "history.modal.subtitle":
    "Skoðaðu gamlar viðureignir, veldu á milli AI og fólks og farðu hratt aftur í viðureignina.",
  "queue.title": "Bíð eftir mótherja",
  "queue.body":
    "Viðureignin þín er tilbúin. Hún byrjar um leið og annar leikmaður kemur.",
  "queue.leave": "Fara úr biðröð",
  "queue.leaving": "Fer úr biðröðinni...",
  "queue.error.dropped": "Rauntímatengingin slitnaði.",
  "queue.error.enter": "Ekki var hægt að fara inn í biðstofuna.",
  "queue.error.leave": "Ekki var hægt að fara úr biðröðinni.",
  "draw.eyebrow": "Upphafsdráttur",
  "draw.title": "Hver byrjar viðureignina",
  "draw.subtitle": "Sá byrjar sem dregur staf nær A. Jóker vinnur alltaf.",
  "draw.side.you": "Þú",
  "draw.side.ai": "AI",
  "draw.pending": "Dreg stafi úr pokanum...",
  "draw.blankCaption": "jóker",
  "draw.result.youStart": "Þú byrjar",
  "draw.result.aiStart": "AI byrjar",
  "draw.reason.blankYou": "Jókerinn þinn vinnur dráttinn.",
  "draw.reason.blankAi": "AI dró jókerinn.",
  "draw.reason.bothBlank": "Báðir stafirnir eru jókerar, svo þú byrjar.",
  "controls.play": "Spila",
  "controls.pass": "Passa",
  "controls.exchange": "Skipta",
  "controls.confirmExchange": "Staðfesta skipti",
  "controls.cancel": "Hætta við",
  // Rendered CSS-uppercased on the board and lowercase in the AI overlay, so the value stays
  // lowercase. Icelandic does not abbreviate `stig`; it is already four letters.
  "board.pts": "stig",
  "board.pinchToZoom": "Klíptu til að þysja",
  "board.dragToPan": "Dragðu til að færa",
  "board.hide": "Fela",
  "board.reset": "Endurstilla",
  "rack.empty": "Engir stafir í grindinni",
  "blank.chooseLetter": "Velja staf fyrir jókerinn",
  "chat.title": "Chat viðureignarinnar",
  "chat.empty": "Engin skilaboð enn.",
  "chat.you": "Þú",
  "chat.unavailable": "Chat er ekki í boði",
  "chat.placeholder": "Segðu eitthvað",
  "chat.send": "Senda",
  "game.lexicon.collins2019": "Ekki í Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Ekki í slóvakíska orðasafninu",
  "game.lexicon.czech": "Ekki í tékkneska orðasafninu",
  "game.lexicon.polish": "Ekki í pólska orðasafninu",
  // Twelve rows take the weak neuter form of the language adjective, which in Icelandic is
  // identical for every case and identical to the language noun of `settings.gameVariant.*` —
  // so the two families stay consistent for free, and Afrikaans needs no exception here.
  // Lowercase, because Icelandic writes a language word lowercase in running text.
  "game.lexicon.afrikaans": "Ekki í afríkanska orðasafninu",
  "game.lexicon.italian": "Ekki í ítalska orðasafninu",
  "game.lexicon.dutch": "Ekki í hollenska orðasafninu",
  "game.lexicon.german": "Ekki í þýska orðasafninu",
  "game.lexicon.portuguese": "Ekki í portúgalska orðasafninu",
  "game.lexicon.danish": "Ekki í danska orðasafninu",
  "game.lexicon.swedish": "Ekki í sænska orðasafninu",
  "game.lexicon.icelandic": "Ekki í íslenska orðasafninu",
  "game.lexicon.unknown": "Ekki í orðasafni viðureignarinnar",
  "game.blocker.auth.title": "Auðkenning mótherja mistókst",
  "game.blocker.auth.body":
    "Þessi gjaldfrjálsi mótherji gat ekki auðkennt sig. Veldu annan gjaldfrjálsan mótherja eða reyndu aftur síðar.",
  "game.blocker.rate.title": "Mótherjinn hefur náð fyrirspurnamarki",
  "game.blocker.rate.body":
    "Þessi gjaldfrjálsi mótherji hefur náð fyrirspurnamarki. Veldu annan gjaldfrjálsan mótherja eða reyndu aftur síðar.",
  "game.blocker.unavail.title": "Mótherjinn er ekki í boði",
  "game.blocker.unavail.body":
    "Þessi gjaldfrjálsi mótherji er ekki í boði í augnablikinu. Veldu annan gjaldfrjálsan mótherja eða reyndu aftur síðar.",
  "game.blocker.badge.auth": "Auðkenning",
  "game.blocker.badge.rate": "Fyrirspurnamark",
  "game.blocker.badge.unavail": "Ekki í boði",
  "game.blocker.close": "Loka",
  "game.blocker.openSettings": "Opna stillingar",
  "game.toast.invalidPlacement": "Ógild staðsetning",
  "game.toast.invalidWords": "Ógild orð",
  "game.toast.moveRejected": "Leik hafnað",
  "game.toast.exchangeRejected": "Skiptum hafnað",
  // No noun form: Icelandic `passi` is a passport, so the frozen pass term stays a verb and this
  // heading is phrased verbally instead of mirroring the English noun.
  "game.toast.passRejected": "Ekki hægt að passa",
  "game.toast.chatOffline": "Chat er ótengt",
  "game.toast.aiPasses": "AI passar",
  "game.toast.aiExchanged": "AI skipti um stafi",
  "game.toast.aiExchangedBody": "AI endurnýjaði grindina og notaði leikinn.",
  "game.toast.aiPassedBody": "Enginn gildur leikur fannst — þú átt leik!",
  // The call site composes these two into `[before] <span>{score}</span> [points]`, with the score
  // FIXED in the middle. Icelandic puts the verb before the number and the counted noun after it,
  // so this order costs nothing: "AI fékk 34 stig".
  "game.aiPlayedFor.before": "AI fékk",
  "game.aiPlayedFor.points": "stig",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation. The bare noun and no article,
  // because Icelandic has no indefinite article at all; `orð` is neuter, so its accusative after
  // `spilaði` is identical to its nominative and the composed sentence works either way.
  "game.aWord": "orð",
  "game.status.selectExchange": "Veldu stafi sem þú vilt skipta um",
  "game.status.aiMoveReady": "Leikur AI er tilbúinn",
  "game.status.aiThinking": "AI er að hugsa",
  "game.status.yourTurn": "Þú átt leik",
  "game.status.waitingForAi": "Bíð eftir AI",
  "game.opponentFallback": "Mótherji",
  "game.waitingSlot": "Í bið",
  "game.sessionExpired": "Innskráning útrunnin",
  "game.lastError": "Síðasta villa:",
  "game.newGame": "Ný viðureign",
  "game.starting": "Byrja...",
  "game.victory": "Sigur!",
  "game.draw": "Jafntefli!",
  "game.gameOver": "Viðureign lokið",
  // The one place `AI`'s gender is visible: `úrskurðuð` is feminine, matching `gervigreind`.
  "game.giveUp.ai":
    "Gefast upp í þessari viðureign? AI verður úrskurðuð sigurvegari.",
  "game.giveUp.human":
    "Gefast upp í þessari viðureign? Mótherjinn þinn verður úrskurðaður sigurvegari.",
  "game.gaveUp": "Þú gafst upp í viðureigninni.",
  "game.error.giveUp": "Ekki var hægt að gefast upp í þessari viðureign",
  "game.error.newGame": "Ekki var hægt að hefja nýja viðureign",
  "game.error.loadGames": "Ekki var hægt að hlaða viðureignunum.",
  "game.password.updated": "Lykilorðinu var breytt.",
  "game.password.failed": "Ekki var hægt að breyta lykilorðinu.",
  "game.ai.noRival": "Enginn gildur gjaldfrjáls mótherji er í boði.",
  "game.ai.timeout": "Umhugsunartími AI er búinn.",
  "game.ai.moveFailed": "Leikur AI mistókst",
  "game.ws.syncFailed": "Rauntímasamstilling mistókst",
  "game.ws.connectFailed": "Rauntímatenging mistókst",
  "game.ws.authExpired":
    "Auðkenning fyrir rauntíma er útrunnin. Endurnýjaðu síðuna til að tengjast aftur.",
  "game.ws.invalidSession":
    "Þessi rauntímaseta er ekki gild. Endurnýjaðu síðuna til að tengjast aftur.",
  "game.ws.unavailable": "Rauntímaþjónustan er ekki í boði. Reyndu aftur.",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in that fixed order.
  // Icelandic wants exactly that order, so "Endurstilla þysjun" needs no workaround.
  "board.zoomNoun": "þysjun",
  "header.giveUp": "Gefast upp",
  "header.givingUp": "Gefst upp...",
  "header.giveUpTooltip": "Gefast upp í þessari viðureign",
  "header.logout": "Skrá út",
  "header.loggingOut": "Skrái út...",
  "header.backToBoards": "Aftur í viðureignirnar",
  "header.profile": "Prófíll",
  "header.games": "Viðureignir",
  "overlay.aiThinking": "AI hugsar",
  "overlay.searching": "Leita að leikjum...",
  "overlay.best": "Besti leikur",
  // A very narrow pill beside a truncating word and a score, so it takes the bare superlative
  // rather than the full label. `BESTI` and not `BEST`, so nobody reads it as untranslated English.
  "overlay.bestBadge": "BESTI",
  "overlay.filtering":
    "Sía út slaka og ógilda leiki áður en alvöru leikur er sýndur...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, two forms each. The helper imported above selects the
// `one` slot whenever i % 10 === 1 and i % 100 !== 11, so the `one` slot must read correctly at 21,
// 101 and 1001 and not only at 1:
//   point noun   stig / stig — Icelandic `stig` (n.) is SYNCRETIC: its nominative and accusative
//                are `stig` in both numbers ("1 stig", "21 stig", "11 stig"). The two slots
//                therefore carry the SAME word. That is the language, not an oversight: do not
//                invent a second form to make the slots look distinct.
//   minute noun  mínútu / mínútur — accusative, governed by `eftir um`, whose case this catalog
//                controls. "eftir um 1 mínútu", "eftir um 21 mínútu", "eftir um 11 mínútur".
//   tile noun    stafur valinn / stafir valdir — the slot carries a two-word PHRASE because an
//                Icelandic predicate participle agrees in number and gender with what it
//                describes, so `valinn` cannot be appended outside the selection the way German
//                appends `ausgewählt`.
export const isFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Stafur ${p.letter}, ${p.points} ` + pluralIs(p.points, "stig", "stig"),
  // Invariable neuter labels, so nothing has to agree with an arbitrary count.
  "overlay.stats.tried": (p) => `Prófað: ${p.count}`,
  "overlay.stats.valid": (p) => `Gilt: ${p.count}`,
  "overlay.stats.rejected": (p) => `Hafnað: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Of margar fyrirspurnir. Reyndu aftur eftir um ${p.minutes} ` +
    pluralIs(p.minutes, "mínútu", "mínútur") +
    ".",
  // `winner` and `loser` receive tile letters, never a person. `nær` is an invariable comparative
  // adverb, so neither opaque value has to be declined and neither needs a gender.
  "draw.reason.closer": (p) => `${p.winner} er nær A en ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` + pluralIs(p.count, "stafur valinn", "stafir valdir"),
  "game.ai.exploring": (p) => `Leita að gildum orðum með ${p.model}...`,
  "game.ai.attempt": (p) => `Tilraun ${p.index}/${p.total} · ${p.label}`,
  "game.toast.aiPlayedWord": (p) => `AI spilaði ${p.word}`,
  // `á leik` and not a participle: `name` is an opaque runtime value whose gender is unknown.
  "game.status.opponentPlaying": (p) => `${p.name} á leik`,
  // Two full forms, never a suffix trick, and unlike English the ADJECTIVE also changes:
  // `ógilt` for one word, `ógild` for more than one.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Ógild orð!" : "Ógilt orð!",
  "game.ai.routeFailed": (p) => `Kall á AI mistókst (${p.status}).`,
  "game.ai.routeFailedBeforeStream": (p) =>
    `Kall á AI mistókst (${p.status}) áður en streymið byrjaði.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `Kall á AI mistókst (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, so it stays in the nominative.
  "play.humanQueue.queueFor": (p) => `Biðröð: ${p.variant}`,
  "queue.room": (p) => `Herbergi ${p.code}`,
  "history.pageOf": (p) => `Síða ${p.page} af ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed noun here.
  "history.showing": (p) => `Sýni ${p.from}-${p.to} af ${p.total}`,
  "picker.flagAlt": (p) => `Fáni: ${p.language}`,
};
