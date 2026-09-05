// ⛔ MACHINE-AUTHORED, NOT REVIEWED BY A NATIVE SPEAKER.
// Every string below was written by a language model. No speaker of this language has read it.
// It is PRESENTATION COPY ONLY: no lexicon entry, no tile distribution and no game rule is
// authored here. That distinction is a standing campaign condition — a UI string may be
// model-authored; a word list may never be.
// Terminology and register follow frontend/src/lib/i18n/GLOSSARY.md, sections D6 and D7.
// Replace with reviewed copy before presenting this locale as production quality.

import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralIt } from "./plural";

// Frozen ITALIAN game terminology (GLOSSARY D6), chosen once and reused everywhere:
//   tile tessera (f.) · letter lettera (f.) · rack leggio (m.) · blank jolly (m., invariable) ·
//   bag sacchetto (m.) · board = tabellone (the physical playing surface) AND partita (a saved
//   game) · pass passare (VERB only) · points punti, abbreviated pt. · rival = opponent
//   avversario (m.).
//
// `tabellone` really is two words. `tabellone` is the surface a tessera sits on; `partita` is the
// metonym for a stored game ("Partite salvate", "Torna alle partite"). `passare` and `scambiare`
// are different moves and keep different words. A `tessera jolly` is a tessera carrying no lettera
// and becoming one. tile and letter are NOT collapsed: Italian word-game usage keeps `tessera`
// (the piece) apart from `lettera` (the character it carries), so both terms stay.
// `jolly` is always carried by the full `tessera jolly`, or stands alone as a predicate noun
// ("sono jolly") or a caption. That is deliberate: it means no article ever precedes `jolly`, so
// this catalog never has to settle whether Italian writes `il jolly` or `lo jolly`.
// `passare` is frozen as a VERB. Italian has no settled noun for the pass MOVE — `passo` is a
// step, `passaggio` is a sports pass — so every noun-shaped pass site is phrased verbally; see
// `game.toast.passRejected`.
//
// Register: informal `tu` throughout, second-person singular, error messages included. Never
// `Lei` / `Suo` / `Vi`. The subject pronoun is dropped wherever Italian idiom drops it, which is
// nearly everywhere, and kept only where it carries contrast ("Inizi tu").
// Label style: SECOND-PERSON SINGULAR IMPERATIVE for every control, action label, column heading
// and accessible name (Gioca · Passa · Scambia · Annulla · Esci · Apri · Cerca · Invia). That is
// what Italian UI actually does — the infinitive (`Giocare`) reads like a manual heading, not a
// button — and it is also the form the informal `tu` register already uses in prose, so unlike
// the three catalogs before this one the control style and the prose style COINCIDE here and
// cannot be mixed inside one strip. Pre-authorized exceptions used: the PAGINATION PAIR
// (`history.prev` / `history.next` are adjectives of the implied `pagina`), the TOGGLE STATE
// WORDS (`settings.toggle.on` / `.off`), and the BADGE WORDS (`settings.board.active` is an
// invariable phrase; `overlay.bestBadge`).
//
// Elision and euphony are applied everywhere and never spaced: `l'AI`, `dell'AI`, `all'AI`,
// `l'interfaccia`, `l'account`, `un'occhiata`-shaped forms, `sala d'attesa`; euphonic `lo` /
// `gli` / `uno` / `dello` before s+consonant, z, gn, ps, x, y (`lo stato`, `uno storico`,
// `dello stream`); and prepositional articles are always contracted (`del`, `al`, `dalla`,
// `nella`, `sulla`). No article ever precedes an interpolated runtime value, because the value's
// initial sound is unknown.
// `AI` is a preserved product token, never rewritten to `IA`, and it takes FEMININE agreement
// throughout, matching `l'intelligenza artificiale`. Keeping it in English forces the elision
// `l'AI` / `dell'AI` / `all'AI`, since the token opens on a vowel however it is read. Its gender
// is visible at `game.giveUp.ai` ("dichiarata vincitrice").
// Thousands separator is a PERIOD (`279.496`), measured with Intl.NumberFormat("it"). In Italian
// the comma is the decimal separator, so the English comma would change the number.
export const itText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  // Italian puts the modifier after the noun, and `premium` is an invariable loan.
  "landing.titleLine1": "Libre Tiles premium,",
  "landing.titleLine2": "umani e AI.",
  "landing.lead":
    "Gioco di parole open-source con abbinamento in diretta, avversari AI implacabili, grafica premium del tabellone e uno storico pronto per la tua prossima partita.",
  "landing.card.ai.title": "Duelli con l'AI",
  // `model` is TRANSLATED here: on a landing card it is an ordinary noun and Italian `modello`
  // carries no competing reading in this context. The five `chat` sites below keep the English
  // token, because each of them names the product's chat panel that the player matches against
  // `chat.title`, and `la chat` is fully naturalized Italian anyway.
  "landing.card.ai.body": "Partite premium con scelta del modello",
  "landing.card.queue.title": "Coda in diretta",
  "landing.card.queue.body": "Sincronizzazione in tempo reale e chat",
  "landing.card.saved.title": "Partite salvate",
  "landing.card.saved.body": "Riprendi le partite con l'AI o con umani",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279.496 parole valide",
  // `Account` is byte-identical to English at both this eyebrow and `nav.account`, and it is the
  // ordinary Italian noun (un account) — Italian has no competing native term in software UI.
  "auth.eyebrow": "Account",
  "auth.heading.login": "Accesso",
  "auth.heading.register": "Nuovo account",
  "auth.tab.login": "Accedi",
  "auth.tab.register": "Registrati",
  "auth.field.username": "Nome utente",
  // Byte-identical to English and correct Italian: `password` (la password) is the standard term;
  // `parola d'ordine` exists but reads as military rather than as a login field.
  "auth.field.password": "Password",
  "a11y.chatInput": "Messaggio della chat",
  "a11y.dialog.profile": "Profilo",
  "a11y.dialog.games": "Partite salvate",
  "a11y.dialog.blank": "Scegli una lettera",
  "a11y.dialog.rival": "Avversario non disponibile",
  "a11y.status.turn": "Stato del turno",
  "a11y.status.aiThinking": "Avanzamento dell'AI",
  "a11y.rackBlank": "Tessera jolly",
  "auth.submit.loading": "Accesso in corso...",
  "auth.submit.login": "Gioca ora",
  "auth.submit.register": "Crea l'account e gioca",
  "meta.title":
    "Libre Tiles — gioco di parole sul web con AI e multigiocatore in diretta",
  "meta.description":
    "Gioco di parole open-source con avversari AI, partite in diretta contro altre persone, chat e un drag-and-drop curato nei dettagli.",
  "error.checkFields": "Controlla i dati che hai inviato.",
  // Login 401 must not distinguish an unknown user from a wrong password.
  "error.invalidCredentials": "Nome utente o password non corretti",
  "error.sessionExpired": "La tua sessione è scaduta. Accedi di nuovo.",
  "error.forbidden": "Non hai i permessi per farlo.",
  "error.notFound": "Non trovato.",
  // `lo stato` and not `il stato`: euphonic `lo` before s+consonant.
  "error.conflict":
    "Questa azione è in conflitto con lo stato attuale della partita.",
  "error.throttled.unknown":
    "Troppe richieste. Attendi un momento e riprova.",
  "error.throttled.oneMinute":
    "Troppe richieste. Riprova tra circa un minuto.",
  "error.unavailable":
    "Il servizio non è momentaneamente disponibile. Riprova.",
  "error.generic": "Qualcosa è andato storto. Riprova.",
  "settings.timeout.title": "Tempo di riflessione dell'AI",
  "settings.timeout.30": "Lettura rapida del tabellone",
  "settings.timeout.60": "Ricerca equilibrata",
  "settings.timeout.120": "Tempo di riflessione predefinito",
  "settings.timeout.180": "Ritmo da torneo",
  "settings.timeout.300": "Riflessione più lunga",
  "settings.steps.title": "Passi di ricerca",
  "settings.steps.10": "Strumenti rapidi",
  "settings.steps.20": "Più tentativi",
  "settings.steps.30": "Ricerca mirata",
  "settings.steps.50": "Profondità di ricerca predefinita",
  "settings.steps.80": "Pressione massima",
  "settings.board.title": "Superficie del tabellone",
  "settings.board.description":
    "Salvata su questo dispositivo e usata nel tabellone di gioco.",
  "settings.board.wood": "Legno",
  "settings.board.woodDesc": "Venatura classica di noce",
  "settings.board.black": "Nero",
  "settings.board.blackDesc": "Lacca notturna lucida",
  "settings.board.green": "Verde",
  "settings.board.greenDesc": "Feltro scuro da torneo",
  // Measured, and NOT the trap the other catalogs hit: all three Italian surface names above are
  // MASCULINE (Legno, Nero, Verde), so an agreeing adjective would in fact be correct today.
  // The invariable badge phrase is chosen anyway: it is the same length as `Attivo`, it reads
  // better on a pill, and it stays correct if a future surface name is feminine.
  "settings.board.active": "In uso",
  // Toggle state words, not action labels: the pre-authorized exception to the imperative style.
  // Both toggled features are masculine (`effetto lucido`, `aspetto premium`), and these render
  // as standalone card labels, so no agreement is at stake either way.
  "settings.toggle.on": "Acceso",
  "settings.toggle.off": "Spento",
  "settings.shiny.title": "Effetto lucido",
  "settings.shiny.description":
    "Spegni il riflesso animato se vuoi alleggerire il carico sulla GPU.",
  "settings.shiny.onDesc": "Riflesso animato sul tabellone",
  "settings.shiny.offDesc": "Minor carico sulla GPU",
  "settings.premium.title": "Aspetto premium",
  "settings.premium.description":
    "Luce ambra interattiva per l'intestazione della partita e per il leggio.",
  "settings.premium.onDesc": "Pannelli interattivi premium",
  "settings.premium.offDesc": "Superfici scure classiche",
  "settings.backToGame": "Torna alla partita",
  "settings.error.newGame":
    "Non è stato possibile avviare una nuova partita in questo momento.",
  "settings.warn.accountSync":
    "La sincronizzazione dell'account non è disponibile in questo momento. Le impostazioni continuano a funzionare in locale su questo dispositivo.",
  "settings.warn.rivalRepair":
    "Su questo dispositivo è selezionato un avversario gratuito. Non è stato ancora possibile correggere la preferenza dell'account.",
  "settings.uiLanguage.title": "Lingua dell'interfaccia",
  "settings.uiLanguage.description":
    "Menu, pulsanti e messaggi. Si applica subito e solo su questo dispositivo.",
  // Endonyms, identical in every catalog by project rule. Never Italian exonyms.
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
  "picker.search": "Cerca",
  "picker.noMatch": "Nessun risultato",
  "picker.uiLanguageLabel": "Lingua dell'interfaccia",
  "picker.gameVariantLabel": "Variante di gioco",
  "settings.gameVariant.title": "Variante di gioco",
  "settings.gameVariant.description":
    "Tessere, sacchetto e lessico. Vale solo per le NUOVE partite e non modifica mai una partita in corso. Non è la lingua dell'interfaccia.",
  // Translated exonyms, unlike the endonyms above, and CAPITALIZED because these are standalone
  // picker rows sitting beside the capitalized endonyms. Italian writes a language name lowercase
  // in RUNNING TEXT, which is what the `game.lexicon.*` family below does with the same words.
  // Measured with Intl.DisplayNames("it") and then checked as a set: these twelve have ZERO
  // case-insensitive substring collisions, so no variant label contains another variant's name.
  // `Afrikaans` is byte-identical to English because Italian has no separate exonym for it; that
  // is correct, not a missing translation.
  "settings.gameVariant.english": "Inglese",
  "settings.gameVariant.slovak": "Slovacco",
  "settings.gameVariant.czech": "Ceco",
  "settings.gameVariant.polish": "Polacco",
  "settings.gameVariant.afrikaans": "Afrikaans",
  "settings.gameVariant.italian": "Italiano",
  "settings.gameVariant.dutch": "Olandese",
  "settings.gameVariant.german": "Tedesco",
  "settings.gameVariant.portuguese": "Portoghese",
  "settings.gameVariant.danish": "Danese",
  "settings.gameVariant.swedish": "Svedese",
  "settings.gameVariant.icelandic": "Islandese",
  "settings.rival.title": "Il tuo avversario",
  "settings.rival.description":
    "L'avversario delle nuove partite è scelto dall'amministratore.",
  "nav.settings": "Impostazioni",
  // Byte-identical to English, same naturalized noun as `auth.eyebrow` above.
  "nav.account": "Account",
  "profile.subtitle":
    "Dati dell'account e sicurezza della password in un unico posto.",
  // Byte-identical to English and correct Italian: `email` (la email) is the standard form.
  // ⚠ NOT `e-mail` — Italian has settled on the unhyphenated spelling, unlike German and Dutch.
  "profile.email": "Email",
  "profile.noEmail": "Nessuna email impostata",
  "profile.memberSince": "Membro dal",
  "profile.password.subtitle":
    "Cambia la password di accesso senza uscire dalla partita.",
  "profile.password.footnote":
    "Password più robuste rendono più sicuri gli account multigiocatore.",
  "profile.field.current": "Password attuale",
  "profile.field.new": "Nuova password",
  "profile.field.confirm": "Conferma la nuova password",
  // Deliberately identical to `profile.field.current`: a visible label and a placeholder are
  // distinct UI roles, so they stay distinct keys.
  "profile.ph.current": "Password attuale",
  "profile.ph.new": "Almeno 8 caratteri",
  "profile.ph.confirm": "Ripeti la nuova password",
  "profile.submit": "Cambia password",
  "profile.submitting": "Aggiornamento...",
  "profile.error.allFields": "Compila tutti i campi della password.",
  "profile.error.mismatch": "Le nuove password non corrispondono.",
  "play.title": "Scegli la prossima partita",
  "play.lead":
    "Inizia un duello premium con l'AI, entra nella coda in diretta o riapri una delle tue partite salvate.",
  "play.ai.eyebrow": "Partita con l'AI",
  "play.ai.title": "Gioca contro l'AI",
  "play.ai.body":
    "Gioca contro l'avversario AI attuale, con il sorteggio iniziale animato.",
  "play.ai.preparing": "Preparazione partita...",
  "play.rival.unavailable": "Nessun avversario disponibile",
  "play.humanQueue.eyebrow": "Coda dei giocatori",
  "play.humanQueue.title": "Trova un avversario in diretta",
  "play.humanQueue.body":
    "Unisciti al primo giocatore in attesa. Se non c'è nessuno, la tua partita resta in attesa nella stanza.",
  "play.humanQueue.joining": "Ingresso in coda...",
  "play.saved.eyebrow": "Partite salvate",
  "play.saved.title": "Riprendi da dove hai smesso",
  "play.saved.note":
    "Le partite con l'AI e quelle con altre persone condividono un unico storico premium.",
  "play.error.catalogEmpty":
    "Il catalogo degli avversari è vuoto. Popola il catalogo gratuito per poter giocare contro l'AI.",
  "play.error.catalogUnavailable":
    "Il catalogo degli avversari non è disponibile in questo momento. Riprova tra un istante.",
  "play.error.variantUnavailable":
    "Non è disponibile nessuna variante di gioco giocabile. La creazione di partite è bloccata finché non si riesce a caricare una variante giocabile.",
  "play.error.startAi": "Non è stato possibile avviare una partita con l'AI.",
  "play.error.joinQueue":
    "Non è stato possibile entrare nella coda dei giocatori.",
  "play.error.loadGames": "Non è stato possibile caricare le tue partite.",
  "history.filter.ai": "AI",
  "history.filter.human": "Umani",
  "history.filter.all": "Tutte",
  "history.sort.recent": "Recenti",
  "history.refresh": "Aggiorna",
  "history.loading": "Caricamento partite",
  "history.empty.title": "Ancora nessuna partita in questo filtro",
  "history.empty.body":
    "Inizia una nuova partita e comparirà qui, con impaginazione premium, distintivi di risultato e link rapidi per riprendere.",
  "history.noneYet": "Ancora nessuna partita salvata",
  // Its name lies about its scope. Measured at four call sites: three of them are a missing DATE
  // (`data`, f.) and the fourth is a missing USERNAME (`nome utente`, m.) at ProfileModal.tsx:220,
  // so no gendered form is correct at both. Italian has a genuinely invariable answer here —
  // `disponibile` is an -e adjective with one form for both genders — which is why this is a
  // phrase rather than `Sconosciuto` / `Sconosciuta`. Splitting the key would be a
  // `messages.en.ts` change and is not in this slice.
  "history.unknownDate": "Non disponibile",
  "history.col.rival": "Avversario",
  "history.col.mode": "Modalità",
  "history.col.result": "Risultato",
  "history.col.score": "Punti",
  "history.col.moves": "Mosse",
  "history.col.updated": "Aggiornata",
  // The eight outcome badges are NOUNS or invariable phrases, so none of them has to agree with
  // `partita` (f.) in the row and with the masculine column heading `Risultato` in the header.
  "history.outcome.waiting": "In attesa",
  "history.outcome.active": "In corso",
  "history.outcome.won": "Vittoria",
  "history.outcome.lost": "Sconfitta",
  "history.outcome.draw": "Pareggio",
  "history.outcome.gaveUp": "Resa",
  "history.outcome.abandoned": "Abbandono",
  // DEAD KEY: `OUTCOME_META` at GameHistoryPanel.tsx:36-75 has exactly seven arms and no
  // `unknown`, so the product cannot render this. The value is correct but deliberately takes the
  // unmarked masculine without further agreement work. Its removal belongs to a later slice.
  "history.outcome.unknown": "Sconosciuto",
  "history.mode.ai": "Duello con l'AI",
  "history.mode.human": "Duello tra umani",
  "history.hint.waitingRoom": "Sala d'attesa",
  "history.hint.boardReady": "Partita pronta",
  // `sacchetto` and `leggio` are both masculine, so the shared predicate takes the masculine
  // plural without a mixed-gender problem.
  "history.endReason.bagEmpty": "Sacchetto e leggio vuoti",
  "history.endReason.noMoves": "Nessuna mossa disponibile",
  "history.endReason.sixZero": "Sei turni senza punti",
  "history.endReason.gaveUp": "Per resa",
  "history.endReason.queueCancelled": "Coda annullata",
  // One value serves a COLUMN HEADING at GameHistoryPanel.tsx:295 and a BUTTON at :139, where it
  // alternates in the same slot with `history.current` — a verb against an adjective in one
  // position. The imperative works in both roles, and `Attuale` is gender-invariable, so this
  // fixed call site cost Italian nothing.
  "history.open": "Apri",
  "history.current": "Attuale",
  // Pagination is a pair of adjectives of the implied `pagina` (f.), so these two are the one
  // place the imperative label style would be wrong.
  "history.prev": "Precedente",
  "history.next": "Successiva",
  "history.modal.subtitle":
    "Rivedi le partite passate, alterna tra AI e umani e torna subito in gioco.",
  "queue.title": "In attesa di un avversario",
  "queue.body":
    "La tua partita è pronta. Inizia appena si aggiunge un altro giocatore.",
  "queue.leave": "Esci dalla coda",
  "queue.leaving": "Uscita dalla coda...",
  "queue.error.dropped": "La connessione in tempo reale è caduta.",
  "queue.error.enter":
    "Non è stato possibile entrare nella sala d'attesa.",
  "queue.error.leave": "Non è stato possibile uscire dalla coda.",
  "draw.eyebrow": "Sorteggio iniziale",
  "draw.title": "Chi apre la partita",
  // `vicina` agrees with `tessera`, which is fixed here and not a runtime value, so the adjective
  // is safe. The interpolated variant of this sentence is `draw.reason.closer`, which is not.
  "draw.subtitle":
    "Inizia chi pesca la tessera più vicina ad A. Una tessera jolly vince sempre.",
  "draw.side.you": "Tu",
  "draw.side.ai": "AI",
  "draw.pending": "Estrazione delle tessere dal sacchetto...",
  // The frozen term is `tessera jolly`, but this caption renders directly under the tessera it
  // describes, in a very narrow tracked pill, so the noun would be redundant there.
  "draw.blankCaption": "jolly",
  "draw.result.youStart": "Inizi tu",
  "draw.result.aiStart": "Inizia l'AI",
  "draw.reason.blankYou": "La tua tessera jolly vince il sorteggio.",
  "draw.reason.blankAi": "L'AI ha pescato la tessera jolly.",
  "draw.reason.bothBlank":
    "Entrambe le tessere sono jolly, quindi inizi tu.",
  "controls.play": "Gioca",
  "controls.pass": "Passa",
  "controls.exchange": "Scambia",
  "controls.confirmExchange": "Conferma scambio",
  "controls.cancel": "Annulla",
  // Rendered CSS-uppercased on the board and lowercase in the AI overlay, so the value stays
  // lowercase and reads correctly either way. The full noun `punti` is used at
  // `game.aiPlayedFor.points`, where the surface is a sentence rather than a pill.
  "board.pts": "pt.",
  "board.pinchToZoom": "Zoom con due dita",
  "board.dragToPan": "Trascina per spostare",
  "board.hide": "Nascondi",
  "board.reset": "Reimposta",
  "rack.empty": "Nessuna tessera nel leggio",
  "blank.chooseLetter": "Scegli una lettera per la tessera jolly",
  "chat.title": "Chat della partita",
  "chat.empty": "Ancora nessun messaggio.",
  "chat.you": "Tu",
  "chat.unavailable": "Chat non disponibile",
  "chat.placeholder": "Scrivi qualcosa",
  "chat.send": "Invia",
  "game.lexicon.collins2019": "Non è nel Collins Scrabble Words 2019",
  "game.lexicon.slovak": "Non è nel lessico slovacco",
  "game.lexicon.czech": "Non è nel lessico ceco",
  "game.lexicon.polish": "Non è nel lessico polacco",
  // Twelve rows take the masculine singular language adjective, agreeing with `lessico`. In
  // Italian that adjective is the same word as the language noun of `settings.gameVariant.*`, so
  // the two families stay consistent for free; the only difference is case, because Italian writes
  // a language word lowercase in running text. `afrikaans` is invariable and is the one row that
  // carries a bare language name rather than an inflected adjective.
  "game.lexicon.afrikaans": "Non è nel lessico afrikaans",
  "game.lexicon.italian": "Non è nel lessico italiano",
  "game.lexicon.dutch": "Non è nel lessico olandese",
  "game.lexicon.german": "Non è nel lessico tedesco",
  "game.lexicon.portuguese": "Non è nel lessico portoghese",
  "game.lexicon.danish": "Non è nel lessico danese",
  "game.lexicon.swedish": "Non è nel lessico svedese",
  "game.lexicon.icelandic": "Non è nel lessico islandese",
  "game.lexicon.unknown": "Non è nel lessico del gioco",
  "game.blocker.auth.title": "Autenticazione dell'avversario non riuscita",
  // `ad autenticarsi` and not `a autenticarsi`: euphonic `ad` before an initial vowel.
  "game.blocker.auth.body":
    "Questo avversario gratuito non è riuscito ad autenticarsi. Passa a un altro avversario gratuito o riprova più tardi.",
  "game.blocker.rate.title": "L'avversario ha raggiunto il limite",
  "game.blocker.rate.body":
    "Questo avversario gratuito ha raggiunto il limite di richieste. Passa a un altro avversario gratuito o riprova più tardi.",
  "game.blocker.unavail.title": "L'avversario non è disponibile",
  "game.blocker.unavail.body":
    "Questo avversario gratuito non è disponibile in questo momento. Passa a un altro avversario gratuito o riprova più tardi.",
  "game.blocker.badge.auth": "Autenticazione",
  "game.blocker.badge.rate": "Limite raggiunto",
  "game.blocker.badge.unavail": "Non disponibile",
  "game.blocker.close": "Chiudi",
  "game.blocker.openSettings": "Apri le impostazioni",
  "game.toast.invalidPlacement": "Posizionamento non valido",
  "game.toast.invalidWords": "Parole non valide",
  "game.toast.moveRejected": "Mossa rifiutata",
  "game.toast.exchangeRejected": "Scambio rifiutato",
  // No noun form: Italian has no settled noun for the pass MOVE, so the frozen term stays a verb
  // and this heading is phrased verbally instead of mirroring the English noun. `passo` is a step
  // and `passaggio` is a sports pass; neither reads as a rejected turn.
  "game.toast.passRejected": "Impossibile passare il turno",
  "game.toast.chatOffline": "La chat è offline",
  "game.toast.aiPasses": "L'AI passa il turno",
  "game.toast.aiExchanged": "L'AI ha scambiato le tessere",
  "game.toast.aiExchangedBody": "L'AI ha rinnovato il leggio e ha usato il turno.",
  "game.toast.aiPassedBody":
    "Non ha trovato nessuna mossa valida — tocca a te!",
  // The call site composes these two into `[before] <span>{score}</span> [points]`, with the score
  // FIXED in the middle. Italian puts the participle before the number and the counted noun after
  // it, so this order costs nothing: "L'AI ha segnato 34 punti". The full noun is used here
  // rather than the `board.pts` abbreviation, because this surface is a sentence.
  "game.aiPlayedFor.before": "L'AI ha segnato",
  "game.aiPlayedFor.points": "punti",
  // Composed INSIDE `game.toast.aiPlayedWord`'s interpolation at page.tsx:1003. The indefinite
  // article is carried here, so the fallback reads "L'AI ha giocato una parola" while a real word
  // reads "L'AI ha giocato CASA" — Italian needs no article before a bare cited word.
  "game.aWord": "una parola",
  "game.status.selectExchange": "Scegli le tessere da scambiare",
  "game.status.aiMoveReady": "Mossa dell'AI pronta",
  "game.status.aiThinking": "L'AI sta pensando",
  "game.status.yourTurn": "Tocca a te",
  "game.status.waitingForAi": "In attesa dell'AI",
  "game.opponentFallback": "Avversario",
  "game.waitingSlot": "In attesa",
  "game.sessionExpired": "Sessione scaduta",
  "game.lastError": "Ultimo errore:",
  "game.newGame": "Nuova partita",
  "game.starting": "Avvio...",
  "game.victory": "Vittoria!",
  "game.draw": "Pareggio!",
  "game.gameOver": "Partita finita",
  // The one place `AI`'s gender is visible: `dichiarata vincitrice` is feminine, matching
  // `l'intelligenza artificiale`. The human line below is masculine, matching `avversario`.
  "game.giveUp.ai":
    "Vuoi arrenderti in questa partita? L'AI sarà dichiarata vincitrice.",
  "game.giveUp.human":
    "Vuoi arrenderti in questa partita? Il tuo avversario sarà dichiarato vincitore.",
  // Italian would normally say "ti sei arreso", but a reflexive past participle agrees with the
  // SUBJECT — here the player, whose gender this catalog cannot know. `avere` + `perso` with the
  // object following it is invariable, so this phrasing needs no gender.
  "game.gaveUp": "Hai perso la partita per resa.",
  "game.error.giveUp":
    "Non è stato possibile arrendersi in questa partita",
  "game.error.newGame": "Non è stato possibile avviare una nuova partita",
  "game.error.loadGames": "Non è stato possibile caricare le partite.",
  "game.password.updated": "Password aggiornata.",
  "game.password.failed":
    "Non è stato possibile aggiornare la password.",
  "game.ai.noRival": "Non è disponibile nessun avversario gratuito idoneo.",
  "game.ai.timeout": "Il tempo di riflessione dell'AI è scaduto.",
  "game.ai.moveFailed": "Mossa dell'AI non riuscita",
  "game.ws.syncFailed": "Sincronizzazione in tempo reale non riuscita",
  "game.ws.connectFailed": "Connessione in tempo reale non riuscita",
  "game.ws.authExpired":
    "L'autenticazione in tempo reale è scaduta. Ricarica la pagina per riconnetterti.",
  "game.ws.invalidSession":
    "Questa sessione in tempo reale non è valida. Ricarica la pagina per riconnetterti.",
  "game.ws.unavailable":
    "Il servizio in tempo reale non è disponibile. Riprova.",
  // `board.reset` and `board.zoomNoun` render in two adjacent spans in that fixed order at
  // Board.tsx:692-693. Italian wants exactly that order, so "Reimposta zoom" needs no workaround.
  "board.zoomNoun": "zoom",
  "header.giveUp": "Arrenditi",
  "header.givingUp": "Resa in corso...",
  "header.giveUpTooltip": "Arrenditi in questa partita",
  // Four characters, shorter than the English six: `Esci` is the standard Italian UI word for
  // leaving a session, so the non-wrapping header cluster gains room here rather than losing it.
  "header.logout": "Esci",
  "header.loggingOut": "Uscita...",
  "header.backToBoards": "Torna alle partite",
  "header.profile": "Profilo",
  "header.games": "Partite",
  "overlay.aiThinking": "L'AI pensa",
  "overlay.searching": "Ricerca di mosse...",
  "overlay.best": "Migliore",
  // A very narrow pill beside a truncating word and a score. `MIGLIORE` is kept correct rather
  // than shortened to a badge word that reads like untranslated English; if rendered review finds
  // it steals room from the candidate word, the shortest honest Italian alternative is `TOP`.
  "overlay.bestBadge": "MIGLIORE",
  "overlay.filtering":
    "Filtraggio delle mosse deboli o non valide prima di mostrare una mossa seria...",
};

// COUNTED NOUNS (GLOSSARY D7). Three sites, and the helper takes FOUR arguments at each of them,
// so this catalog has nine slot fillers. CLDR it selects `one` only at exactly 1, `many` only at
// exact non-zero millions, and `other` for everything else INCLUDING ZERO — measured on
// node v26.4.0 / ICU 78.3 and pinned by plural.test.ts. Italian therefore writes "0 punti", NOT
// the "0 punto" that CLDR Portuguese produces next door; the `one` slot must never be reachable
// from zero here.
//   point noun   punto / punti / punti — pure nouns. The `many` slot repeats the `other` word,
//                because CLDR distinguishes the categories and Italian does not distinguish the
//                words. No third form is invented to make the slots look distinct.
//   minute noun  minuto / minuti / minuti — same repetition, same reason.
//   tile phrase  tessera selezionata / tessere selezionate / tessere selezionate — the slot
//                carries a two-word PHRASE, because an Italian predicate participle agrees in
//                number with what it describes, so `selezionata` cannot be appended outside the
//                selection the way German appends `ausgewählt`. The colon-label shape that keeps
//                the slots pure nouns was available and is deliberately not used: this surface is
//                a full-width centred line that wraps freely and is bounded by rack size 7, so
//                the natural Italian sentence fits and reads better than a label.
export const itFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "a11y.rackTile": (p) =>
    `Tessera ${p.letter}, ${p.points} ` +
    pluralIt(p.points, "punto", "punti", "punti"),
  // Category labels agreeing with the implied `mosse` (f. pl.), which is fixed at author time, so
  // nothing has to agree with an arbitrary runtime count.
  "overlay.stats.tried": (p) => `Provate: ${p.count}`,
  "overlay.stats.valid": (p) => `Valide: ${p.count}`,
  "overlay.stats.rejected": (p) => `Rifiutate: ${p.count}`,
  "error.throttled.minutes": (p) =>
    `Troppe richieste. Riprova tra circa ${p.minutes} ` +
    pluralIt(p.minutes, "minuto", "minuti", "minuti") +
    ".",
  // `winner` and `loser` receive TILE LETTERS, never a person (draw-result.ts:29-30), and a bare
  // letter's gender is unsettled in Italian. `si avvicina` is an invariable third-person verb, so
  // neither opaque value needs a gender and no adjective has to agree. `ad A` and not `a A`:
  // euphonic `ad` before the same initial vowel.
  "draw.reason.closer": (p) =>
    `${p.winner} si avvicina ad A più di ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `${p.count} ` +
    pluralIt(
      p.count,
      "tessera selezionata",
      "tessere selezionate",
      "tessere selezionate",
    ),
  // `model` is an opaque runtime id, so `con` carries it with no article before it.
  "game.ai.exploring": (p) => `Ricerca di parole valide con ${p.model}...`,
  "game.ai.attempt": (p) => `Tentativo ${p.index}/${p.total} · ${p.label}`,
  "game.toast.aiPlayedWord": (p) => `L'AI ha giocato ${p.word}`,
  // `sta giocando` and not a participle: `name` is an opaque runtime value whose gender is
  // unknown, and the Italian progressive gerund is invariable.
  "game.status.opponentPlaying": (p) => `${p.name} sta giocando`,
  // Two full forms, never a suffix trick, and unlike English the ADJECTIVE also changes:
  // `valida` for one word, `valide` for more than one.
  "game.toast.invalidWordHeading": (p) =>
    p.count > 1 ? "Parole non valide!" : "Parola non valida!",
  "game.ai.routeFailed": (p) =>
    `Chiamata all'AI non riuscita (${p.status}).`,
  // `dello stream` and not `del stream`: euphonic `lo` before s+consonant.
  "game.ai.routeFailedBeforeStream": (p) =>
    `Chiamata all'AI non riuscita (${p.status}) prima dell'avvio dello stream.`,
  "game.ai.routeFailedWithPreview": (p) =>
    `Chiamata all'AI non riuscita (${p.status}): ${p.preview}`,
  // Colon form: `variant` is a resolved display name, and an Italian preposition plus article
  // cannot precede a value whose initial sound and gender are unknown.
  "play.humanQueue.queueFor": (p) => `Coda: ${p.variant}`,
  "queue.room": (p) => `Stanza ${p.code}`,
  "history.pageOf": (p) => `Pagina ${p.page} di ${p.total}`,
  // Noun-free: an arbitrary count cannot agree with a fixed participle, and the English counted
  // noun is dropped the way the four catalogs before this one dropped it.
  "history.showing": (p) => `Risultati ${p.from}-${p.to} di ${p.total}`,
  // Colon form for the same reason as `play.humanQueue.queueFor`: `language` is opaque.
  "picker.flagAlt": (p) => `Bandiera: ${p.language}`,
};
