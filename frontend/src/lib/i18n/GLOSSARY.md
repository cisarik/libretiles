# Libre Tiles interface-language glossary

Project rules for later localization slices. English is the default locale and
the shape-defining catalog. No new runtime i18n dependency: a missing key in
any of `en` / `sk` / `cs` / `pl` is a TypeScript error.

Interface-language names (`settings.uiLanguage.*`) are **endonyms**, identical
in every catalog (`English`, `Slovenčina`, `Čeština`, `Polski`), so a user who
cannot read the current UI can still find their own language. Game-variant
names remain translated exonyms.

## D2 — Informal Slavic register

Slovak, Czech, and Polish copy uses informal 2nd person singular (`ty` /
tykanie; Czech `ty`; Polish 2nd person singular). Never `Vy` / `Pan` /
`Państwo`.

- Correct: `Tvoj ťah`, `Prihlás sa znova`, `Skús to znova.`
- Incorrect: `Váš ťah`, `Prihláste sa znova.`

This applies to error messages as well as chrome.

## D6 — Fixed game terminology

Czech deliberately differs from Slovak on the tile: Czech uses `kámen` for the
tile and reserves `písmeno` for the letter, per the Česká asociace Scrabble
rules. Do not harmonize Czech to Slovak.

| | tile | letter | rack | blank | bag | board | pass | points |
|---|---|---|---|---|---|---|---|---|
| en | tile | letter | rack | blank | bag | board | Pass | pts |
| sk | písmeno | písmeno | zásobník | žolík | vrecko | hracia plocha | Vynechať | b. |
| cs | kámen | písmeno | zásobník | žolík | sáček | hrací deska | Vzdát tah | b. |
| pl | płytka | litera | stojak | blank | woreczek | plansza | Pauza | pkt |

Polish `pass` is `Pauza`. The word `pas` does not appear in the Polska
Federacja Scrabble regulations at all.

Sources, retrieved 2026-09-02:

- Polska Federacja Scrabble regulations: https://pfs.org.pl/regulaminy.php
- Česká asociace Scrabble rules: https://scrabble.hrejsi.cz/pravidla

Do not translate these terms; keep them in English in every catalog:

`provider`, `model`, `prompt`, `fallback`, `token`, `chat`, `API`

## D7 — Counted nouns

Slovak and Czech share the integer rule `1 / 2..4 / otherwise`. Polish keys on
the last digit with a 12–14 exception, so `pluralSk` is wrong for Polish at
22, 23, 24, 122, 123, 124. Named helpers: `pluralEn`, `pluralSk`, `pluralCs`
(= `pluralSk`, deliberately), `pluralPl`. Do not fold them into one
table-driven function.

| n | sk | cs | pl |
|---|---|---|---|
| 1 | minútu | minutu | minutę |
| 2, 3, 4 | minúty | minuty | minuty |
| 5 .. 21 | minút | minut | minut |
| 22, 23, 24 | minút | minut | minuty |
| 122 .. 124 | minút | minut | minuty |

This codebase must not use a one-character `s` suffix for counts.

English counted nouns use `pluralEn` (`one` / `other`).

Slovak, Czech, and Polish thousands separator is a non-breaking space (U+00A0):
`279 496`.

## Landing and auth

| Key | English | Slovak |
|---|---|---|
| landing.brand | Libre Tiles | Libre Tiles |
| landing.titleLine1 | Premium Libre Tiles, | Premium Libre Tiles, |
| landing.titleLine2 | human and AI. | ľudia aj AI. |
| landing.lead | Open-source wordplay with live matchmaking, sharp AI rivals, premium board chrome, and a history surface ready for your next board. | Open-source slovná hra so živým párovaním, ostrými AI súpermi, prémiovou grafikou plochy a históriou pripravenou na tvoju ďalšiu partiu. |
| landing.card.ai.title | AI duels | AI duely |
| landing.card.ai.body | Model-aware premium games | Prémiové partie proti AI |
| landing.card.queue.title | Live queue | Živý front |
| landing.card.queue.body | Realtime sync and chat | Synchronizácia v reálnom čase a chat |
| landing.card.saved.title | Saved boards | Uložené partie |
| landing.card.saved.body | Resume AI or human games | Pokračuj v partii proti AI alebo človeku |
| landing.footnote | Open source • Collins Scrabble Words 2019 • 279,496 valid words | Open source • Collins Scrabble Words 2019 • 279 496 platných slov |
| auth.eyebrow | Account | Účet |
| auth.heading.login | Sign in | Prihlásenie |
| auth.heading.register | Create account | Vytvorenie účtu |
| auth.tab.login | Sign In | Prihlásiť sa |
| auth.tab.register | Register | Registrovať |
| auth.field.username | Username | Používateľské meno |
| auth.field.password | Password | Heslo |
| auth.submit.loading | Signing in... | Prihlasujem... |
| auth.submit.login | Play now | Hrať |
| auth.submit.register | Create account & play | Vytvoriť účet a hrať |
| meta.title | Libre Tiles — Web Libre Tiles with AI and Live Multiplayer | Libre Tiles — slovná hra na webe s AI a živým multiplayerom |
| meta.description | Open-source Libre Tiles with AI rivals, live human matches, chat, and polished drag-and-drop play. | Open-source slovná hra s AI súpermi, živými partiami proti ľuďom, chatom a vyladeným drag-and-drop hraním. |

## API errors

Login 401 must not distinguish an unknown user from a wrong password.

| Key | English | Slovak |
|---|---|---|
| error.checkFields | Please check the submitted fields. | Skontroluj zadané údaje. |
| error.invalidCredentials | Invalid username or password | Nesprávne používateľské meno alebo heslo |
| error.sessionExpired | Your session expired. Please sign in again. | Prihlásenie vypršalo. Prihlás sa znova. |
| error.forbidden | You do not have permission to do that. | Na túto akciu nemáš oprávnenie. |
| error.notFound | Not found. | Nenašlo sa. |
| error.conflict | This action conflicts with the current game state. | Táto akcia je v rozpore s aktuálnym stavom partie. |
| error.throttled.unknown | Too many requests. Please wait and try again. | Priveľa požiadaviek. Chvíľu počkaj a skús znova. |
| error.throttled.oneMinute | Too many requests. Try again in about a minute. | Priveľa požiadaviek. Skús znova asi za minútu. |
| error.unavailable | The service is temporarily unavailable. Please try again. | Služba je momentálne nedostupná. Skús to znova. |
| error.generic | Something went wrong. Please try again. | Niečo sa pokazilo. Skús to znova. |
| error.throttled.minutes | Too many requests. Try again in about {n} minutes. | Priveľa požiadaviek. Skús znova asi za {n} minútu/minúty/minút. |

## Settings panels in this slice

| Key | English | Slovak |
|---|---|---|
| settings.uiLanguage.title | Interface language | Jazyk rozhrania |
| settings.uiLanguage.description | Menus, buttons, and messages. Changes immediately, on this device only. | Menu, tlačidlá a správy. Zmena platí okamžite a len na tomto zariadení. |
| settings.uiLanguage.en | English | English |
| settings.uiLanguage.sk | Slovenčina | Slovenčina |
| settings.uiLanguage.cs | Čeština | Čeština |
| settings.uiLanguage.pl | Polski | Polski |
| settings.gameVariant.title | Game variant | Variant hry |
| settings.gameVariant.description | Tiles, bag, and lexicon. Applies to NEW games only and never changes a running game. This is not the interface language. | Písmená, vrecko a lexikón. Platí pre NOVÉ partie a nemení prebiehajúcu partiu. Toto nie je jazyk rozhrania. |
| settings.gameVariant.english | English | Angličtina |
| settings.gameVariant.slovak | Slovak | Slovenčina |
| settings.rival.title | Your rival | Tvoj súper |
| settings.rival.description | The administrator picks the rival for new games. | Súpera pre nové partie vyberá správca. |
| settings.timeout.title | AI Thinking Time | Čas na rozmýšľanie AI |
| settings.timeout.30 | Fast board read | Rýchle prečítanie plochy |
| settings.timeout.60 | Balanced search | Vyvážené hľadanie |
| settings.timeout.120 | Default thinking time | Predvolený čas na rozmýšľanie |
| settings.timeout.180 | Tournament pace | Turnajové tempo |
| settings.timeout.300 | Longest think | Najdlhšie rozmýšľanie |
| settings.steps.title | Search Steps | Kroky hľadania |
| settings.steps.10 | Quick tools | Rýchly priebeh |
| settings.steps.20 | More tries | Viac pokusov |
| settings.steps.30 | Focused search | Zamerané hľadanie |
| settings.steps.50 | Default search depth | Predvolená hĺbka hľadania |
| settings.steps.80 | Max pressure | Maximálny tlak |
| settings.board.title | Board Surface | Povrch plochy |
| settings.board.description | Saved on this device and used in the game board. | Uložené na tomto zariadení a použité v hracej ploche. |
| settings.board.wood | Wood | Drevo |
| settings.board.woodDesc | Classic walnut grain | Klasická orechová kresba |
| settings.board.black | Black | Čierna |
| settings.board.blackDesc | Glossy night lacquer | Lesklý nočný lak |
| settings.board.green | Green | Zelená |
| settings.board.greenDesc | Dark tournament felt | Tmavá turnajová plsť |
| settings.board.active | Active | Aktívne |
| settings.toggle.on | On | Zapnuté |
| settings.toggle.off | Off | Vypnuté |
| settings.shiny.title | Shiny Effect | Lesklý efekt |
| settings.shiny.description | Turn the live sheen off when you want a lighter GPU load. | Vypni živý lesk, ak chceš menšiu záťaž GPU. |
| settings.shiny.onDesc | Animated board sheen | Animovaný lesk plochy |
| settings.shiny.offDesc | Lower GPU load | Menšia záťaž GPU |
| settings.premium.title | Premium Look | Premium vzhľad |
| settings.premium.description | Interactive amber spotlight for the game header and rack panel. | Interaktívne jantárové svetlo pre hlavičku hry a zásobník. |
| settings.premium.onDesc | Premium interactive panels | Interaktívne premium panely |
| settings.premium.offDesc | Classic dark surfaces | Klasické tmavé povrchy |
| settings.backToGame | Back to game | Späť do hry |
| settings.error.newGame | Could not start a fresh game right now. | Novú partiu sa teraz nepodarilo spustiť. |
| settings.warn.accountSync | Account sync is unavailable right now. Settings still work locally on this device. | Synchronizácia účtu je momentálne nedostupná. Nastavenia fungujú lokálne na tomto zariadení. |
| settings.warn.rivalRepair | A free rival is selected on this device. Account preference could not be repaired yet. | Súper je vybraný na tomto zariadení. Preferenciu účtu sa zatiaľ nepodarilo opraviť. |
| draw.eyebrow | Starting draw | Ťah o poradie |
| draw.title | Who opens the board | Kto začína partiu |
| draw.subtitle | Whoever draws the tile closer to A starts. A blank always wins. | Začína ten, kto vytiahne písmeno bližšie k A. Žolík vyhráva vždy. |
| draw.side.you | You | Ty |
| draw.side.ai | AI | AI |
| draw.pending | Drawing tiles from the bag... | Ťahám písmená z vrecka... |
| draw.blankCaption | blank | žolík |
| draw.result.youStart | You start | Začínaš ty |
| draw.result.aiStart | AI starts | Začína AI |
| draw.reason.blankYou | Your blank wins the draw. | Tvoj žolík vyhráva ťah o poradie. |
| draw.reason.blankAi | The AI drew the blank. | Žolíka vytiahlo AI. |
| draw.reason.bothBlank | Both tiles are blanks, so you start. | Obidve písmená sú žolíky, takže začínaš ty. |
| draw.reason.closer (fn) | {winner} is closer to A than {loser}. | {winner} je bližšie k A ako {loser}. |

## Lobby and waiting room

`play.humanQueue.queueFor` receives a resolved variant DISPLAY NAME from
`variantDisplayName(...)` (for example `Slovenčina` / `Čeština`) and never a
slug. That is the `uii-01-F14` fix: a two-value english/slovak ternary cannot
come back when a fifth variant is added.

| Key | English | Slovak |
|---|---|---|
| nav.settings | Settings | Nastavenia |
| nav.account | Account | Účet |
| play.title | Choose the next board | Vyber si ďalšiu partiu |
| play.lead | Start a premium AI duel, jump into the live queue, or reopen one of your saved boards. | Spusti prémiový duel proti AI, skoč do živého frontu alebo si otvor niektorú z uložených partií. |
| play.ai.eyebrow | AI Match | AI partia |
| play.ai.title | Play the house | Hraj proti AI |
| play.ai.body | Use the current AI rival and keep the animated opening draw. | Zahraj si proti aktuálnemu súperovi aj s animovaným ťahom o poradie. |
| play.ai.preparing | Preparing game... | Pripravujem partiu... |
| play.rival.unavailable | No rival available | Žiadny súper nie je dostupný |
| play.humanQueue.eyebrow | Human Queue | Front hráčov |
| play.humanQueue.title | Find a live opponent | Nájdi živého súpera |
| play.humanQueue.body | Join the first waiting player. If nobody is there, your board waits in the room. | Pripoj sa k prvému čakajúcemu hráčovi. Ak tam nikto nie je, tvoja partia počká v čakárni. |
| play.humanQueue.joining | Joining queue... | Pripájam sa do frontu... |
| play.humanQueue.queueFor (fn) | {variant} queue | Front: {variant} |
| play.saved.eyebrow | Saved boards | Uložené partie |
| play.saved.title | Resume where you left off | Pokračuj tam, kde si skončil |
| play.saved.note | AI and human games share one premium history surface. | Partie proti AI aj proti ľuďom majú jednu spoločnú históriu. |
| play.error.catalogEmpty | The rival catalog is empty. Seed the free catalog to play AI matches. | Katalóg súperov je prázdny. Naplň katalóg, aby sa dali hrať partie proti AI. |
| play.error.variantUnavailable | No playable game variant is available. Game creation is blocked until a playable variant can be loaded. | Nie je dostupný žiadny hrateľný variant hry. Nová partia sa nedá vytvoriť, kým sa nejaký nenačíta. |
| play.error.startAi | Could not start an AI game. | Partiu proti AI sa nepodarilo spustiť. |
| play.error.joinQueue | Could not join the human queue. | Do frontu hráčov sa nepodarilo pripojiť. |
| play.error.loadGames | Unable to load your games. | Tvoje partie sa nepodarilo načítať. |
| queue.title | Waiting for an opponent | Čakám na súpera |
| queue.body | Your board is ready. The match starts as soon as another player joins. | Tvoja partia je pripravená. Začne, len čo sa pripojí ďalší hráč. |
| queue.leave | Leave queue | Opustiť front |
| queue.leaving | Leaving queue... | Opúšťam front... |
| queue.error.dropped | Realtime connection dropped. | Realtime spojenie sa prerušilo. |
| queue.error.enter | Could not enter the waiting room. | Do čakárne sa nepodarilo vstúpiť. |
| queue.error.leave | Could not leave the queue. | Front sa nepodarilo opustiť. |
| queue.room (fn) | Room {code} | Miestnosť {code} |

## Turn chrome

| Key | English | Slovak |
|---|---|---|
| controls.play | Play | Zahrať |
| controls.pass | Pass | Vynechať |
| controls.exchange | Exchange | Vymeniť |
| controls.confirmExchange | Confirm exchange | Potvrdiť výmenu |
| controls.cancel | Cancel | Zrušiť |
| controls.tilesSelected (fn) | {n} tile(s) selected | Výber: {n} písmeno/písmená/písmen |
| board.pts | PTS | b. |
| board.pinchToZoom | Pinch to zoom | Zoom dvoma prstami |
| board.dragToPan | Drag to pan | Posuň ťahaním |
| board.hide | Hide | Skryť |
| board.reset | Reset | Reset |
| board.zoomNoun | zoom | zoomu |
| rack.empty | No tiles on rack | Zásobník je prázdny |
| blank.chooseLetter | Choose a letter for blank tile | Vyber písmeno pre žolíka |
| chat.title | Game Chat | Chat partie |
| chat.empty | No messages yet. | Ešte žiadne správy. |
| chat.you | You | Ty |
| chat.unavailable | Chat unavailable | Chat je nedostupný |
| chat.placeholder | Say something | Napíš niečo |
| chat.send | Send | Poslať |

## Game screen

`game.lexicon.*` is keyed on the GAME VARIANT's `lexicon_id` (`collins2019` /
`slovak` / `czech` / `polish`) and not on the interface locale. Those are two
independent axes; this is the first key family that depends on the other one.

| Key | English | Slovak |
|---|---|---|
| game.lexicon.collins2019 | Not in Collins Scrabble Words 2019 | Nie je v Collins Scrabble Words 2019 |
| game.lexicon.slovak | Not in the Slovak lexicon | Nie je v slovenskom lexikóne |
| game.lexicon.czech | Not in the Czech lexicon | Nie je v českom lexikóne |
| game.lexicon.polish | Not in the Polish lexicon | Nie je v poľskom lexikóne |
| game.lexicon.unknown | Not in the game lexicon | Nie je v lexikóne hry |
| game.blocker.auth.title | Rival authentication failed | Prihlásenie súpera zlyhalo |
| game.blocker.auth.body | This free rival could not authenticate. Switch to another free rival or retry later. | Tento súper sa nedokázal prihlásiť. Vyber iného súpera alebo to skús neskôr. |
| game.blocker.rate.title | Rival is rate limited | Súper má vyčerpaný limit |
| game.blocker.rate.body | This free rival is rate limited. Switch to another free rival or retry later. | Tento súper má momentálne vyčerpaný limit. Vyber iného súpera alebo to skús neskôr. |
| game.blocker.unavail.title | Rival is unavailable | Súper je nedostupný |
| game.blocker.unavail.body | This free rival is temporarily unavailable. Switch to another free rival or retry later. | Tento súper je momentálne nedostupný. Vyber iného súpera alebo to skús neskôr. |
| game.blocker.badge.auth | Authentication | Prihlásenie |
| game.blocker.badge.rate | Rate Limited | Limit vyčerpaný |
| game.blocker.badge.unavail | Unavailable | Nedostupné |
| game.blocker.close | Close | Zavrieť |
| game.blocker.openSettings | Open settings | Otvoriť nastavenia |
| game.toast.invalidPlacement | Invalid Placement | Neplatné umiestnenie |
| game.toast.invalidWords | Invalid words | Neplatné slová |
| game.toast.moveRejected | Move rejected | Ťah zamietnutý |
| game.toast.exchangeRejected | Exchange rejected | Výmena zamietnutá |
| game.toast.passRejected | Pass rejected | Vynechanie zamietnuté |
| game.toast.chatOffline | Chat is offline | Chat je offline |
| game.toast.aiPasses | AI passes | AI vynechalo ťah |
| game.toast.aiExchanged | AI exchanged tiles | AI vymenilo písmená |
| game.toast.aiExchangedBody | AI refreshed the rack and spent the turn. | AI si obnovilo zásobník a spotrebovalo ťah. |
| game.toast.aiPassedBody | Couldn't find a valid move - your turn! | Nenašlo platný ťah — si na ťahu! |
| game.toast.invalidWordHeading (fn) | Invalid Word! / Invalid Words! | Neplatné slovo! / Neplatné slová! |
| game.aiPlayedFor.before | AI played for | AI zahralo za |
| game.aiPlayedFor.points | pts | b. |
| game.aWord | a word | slovo |
| game.status.selectExchange | Select tiles to exchange | Vyber písmená na výmenu |
| game.status.aiMoveReady | AI move ready | Ťah AI je pripravený |
| game.status.aiThinking | AI is thinking | AI premýšľa |
| game.status.yourTurn | Your turn | Tvoj ťah |
| game.status.waitingForAi | Waiting for the AI | Čakám na AI |
| game.opponentFallback | Opponent | Súper |
| game.waitingSlot | Waiting | Čaká sa |
| game.sessionExpired | Session expired | Prihlásenie vypršalo |
| game.lastError | Last error: | Posledná chyba: |
| game.newGame | New Game | Nová partia |
| game.starting | Starting... | Spúšťam... |
| game.victory | Victory! | Vyhral si! |
| game.draw | Draw! | Remíza! |
| game.gameOver | Game Over | Koniec partie |
| game.giveUp.ai | Give up this game? The AI will be declared the winner. | Vzdať túto partiu? Za víťaza bude vyhlásené AI. |
| game.giveUp.human | Give up this game? Your opponent will be declared the winner. | Vzdať túto partiu? Za víťaza bude vyhlásený súper. |
| game.gaveUp | You gave up the game. | Vzdal si partiu. |
| game.error.giveUp | Could not give up this game | Partiu sa nepodarilo vzdať |
| game.error.newGame | Could not start a new game | Novú partiu sa nepodarilo spustiť |
| game.error.loadGames | Unable to load games. | Partie sa nepodarilo načítať. |
| game.password.updated | Password updated. | Heslo je zmenené. |
| game.password.failed | Unable to update password. | Heslo sa nepodarilo zmeniť. |
| game.ai.noRival | No eligible free rival is available. | Nie je dostupný žiadny vhodný súper. |
| game.ai.timeout | AI thinking time ran out. | AI vypršal čas na rozmýšľanie. |
| game.ai.moveFailed | AI move failed | Ťah AI zlyhal |
| game.ai.routeFailed (fn) | AI route failed ({status}). | Volanie AI zlyhalo ({status}). |
| game.ai.routeFailedBeforeStream (fn) | AI route failed ({status}) before the stream started. | Volanie AI zlyhalo ({status}) ešte pred začiatkom streamu. |
| game.ai.routeFailedWithPreview (fn) | AI route failed ({status}): {preview} | Volanie AI zlyhalo ({status}): {preview} |
| game.ws.syncFailed | Realtime sync failed | Synchronizácia zlyhala |
| game.ws.connectFailed | Realtime connection failed | Realtime spojenie zlyhalo |
| game.ws.authExpired | Realtime authentication expired. Refresh the page to reconnect. | Prihlásenie pre realtime vypršalo. Obnov stránku a pripoj sa znova. |
| game.ws.invalidSession | This realtime session is not valid. Refresh the page to reconnect. | Toto realtime spojenie nie je platné. Obnov stránku a pripoj sa znova. |
| game.ws.unavailable | The realtime service is unavailable. Please try again. | Realtime služba je nedostupná. Skús to znova. |
| game.ai.exploring (fn) | Exploring legal words with {model}... | Hľadám platné slová cez {model}... |
| game.ai.attempt (fn) | Attempt {index}/{total} · {label} | Pokus {index}/{total} · {label} |
| game.toast.aiPlayedWord (fn) | AI played {word} | AI zahralo {word} |
| game.status.opponentPlaying (fn) | {name} is playing | {name} je na ťahu |

## Header cluster and AI overlay

`overlay.bestBadge` exists separately from `overlay.best` because the badge
carries its own uppercased value; Slavic diacritics are not reliably uppercased
by a CSS `uppercase` class across these fonts.

`{humanState}` in the AI overlay is deliberately not localized pending the
enum-keyed telemetry slice. Those English states are produced in the locked
AI move route and re-derived by `describeAiTurnTelemetry`.

| Key | English | Slovak |
|---|---|---|
| header.giveUp | Give up | Vzdať sa |
| header.givingUp | Giving up... | Vzdávam sa... |
| header.giveUpTooltip | Give up current game | Vzdať túto partiu |
| header.logout | Logout | Odhlásiť sa |
| header.loggingOut | Logging out... | Odhlasujem... |
| header.backToBoards | Back to boards | Späť na partie |
| header.profile | Profile | Profil |
| header.games | Games | Partie |
| overlay.aiThinking | AI Thinking | AI premýšľa |
| overlay.searching | Searching for moves... | Hľadám ťahy... |
| overlay.best | Best | Najlepší |
| overlay.bestBadge | BEST | NAJLEPŠÍ |
| overlay.filtering | Filtering weak or invalid lines before showing a serious move... | Odfiltrúvam slabé a neplatné ťahy, kým nenájdem vážny ťah... |
| overlay.stats.tried (fn) | {count} tried | Skúsené: {count} |
| overlay.stats.valid (fn) | {count} valid | Platné: {count} |
| overlay.stats.rejected (fn) | {count} rejected | Zamietnuté: {count} |

The three `overlay.stats.*` keys use colon-labels for the same grammatical
reason as `controls.tilesSelected`: one adjective form cannot agree correctly
across all counted forms.

The `TIMEOUT_CHOICES` and `STEP_CHOICES` labels are deliberately not localized;
they are compact unit abbreviations and numbers.
