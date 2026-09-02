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
| game.ws.syncFailed | Realtime sync failed | Synchronizácia zlyhala |
| game.ws.connectFailed | Realtime connection failed | Realtime spojenie zlyhalo |
| game.ws.authExpired | Realtime authentication expired. Refresh the page to reconnect. | Prihlásenie pre realtime vypršalo. Obnov stránku a pripoj sa znova. |
| game.ws.invalidSession | This realtime session is not valid. Refresh the page to reconnect. | Toto realtime spojenie nie je platné. Obnov stránku a pripoj sa znova. |
| game.ws.unavailable | The realtime service is unavailable. Please try again. | Realtime služba je nedostupná. Skús to znova. |
| game.ai.exploring (fn) | Exploring legal words with {model}... | Hľadám platné slová cez {model}... |
| game.ai.attempt (fn) | Attempt {index}/{total} · {label} | Pokus {index}/{total} · {label} |
| game.toast.aiPlayedWord (fn) | AI played {word} | AI zahralo {word} |
| game.status.opponentPlaying (fn) | {name} is playing | {name} je na ťahu |
