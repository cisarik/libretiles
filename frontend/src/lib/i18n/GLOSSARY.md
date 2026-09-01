# Libre Tiles interface-language glossary

Project rules for later localization slices. English is the default locale and
the shape-defining catalog. No new runtime i18n dependency: missing Slovak keys
are TypeScript errors.

## D2 — Informal Slovak register

Slovak copy uses informal **ty** (tykanie), never **vy**.

- Correct: `Tvoj ťah`, `Prihlás sa znova`, `Skús to znova.`
- Incorrect: `Váš ťah`, `Prihláste sa znova.`

This applies to error messages as well as chrome.

## D6 — Fixed game terminology

| English | Slovak | Notes |
|---|---|---|
| tile | písmeno | Never kameň, never dlaždica |
| rack | zásobník | |
| blank | žolík | |

Do not translate these terms; keep them in English in both catalogs:

`provider`, `model`, `prompt`, `fallback`, `token`, `chat`, `API`

## D7 — Counted nouns

Slovak has three plural forms. This codebase must not use a one-character `s`
suffix for counts. Every counted noun goes through `pluralSk`:

| Form | Rule | Example (`minúta`) |
|---|---|---|
| one | `\|trunc(n)\| === 1` | minútu |
| few | `\|trunc(n)\|` in 2..4 | minúty |
| many | otherwise, including 0 | minút |

English counted nouns use `pluralEn` (`one` / `other`).

Slovak thousands separator is a non-breaking space (U+00A0): `279 496`.

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
| settings.uiLanguage.en | English | Angličtina |
| settings.uiLanguage.sk | Slovak | Slovenčina |
| settings.gameVariant.title | Game variant | Variant hry |
| settings.gameVariant.description | Tiles, bag, and lexicon. Applies to NEW games only and never changes a running game. This is not the interface language. | Písmená, vrecko a lexikón. Platí pre NOVÉ partie a nemení prebiehajúcu partiu. Toto nie je jazyk rozhrania. |
| settings.gameVariant.english | English | Angličtina |
| settings.gameVariant.slovak | Slovak | Slovenčina |
