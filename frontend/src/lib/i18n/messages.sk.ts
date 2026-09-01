import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralSk } from "./plural";

export const skText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "ľudia aj AI.",
  "landing.lead":
    "Open-source slovná hra so živým párovaním, ostrými AI súpermi, prémiovou grafikou plochy a históriou pripravenou na tvoju ďalšiu partiu.",
  "landing.card.ai.title": "AI duely",
  "landing.card.ai.body": "Prémiové partie proti AI",
  "landing.card.queue.title": "Živý front",
  "landing.card.queue.body": "Synchronizácia v reálnom čase a chat",
  "landing.card.saved.title": "Uložené partie",
  "landing.card.saved.body": "Pokračuj v partii proti AI alebo človeku",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 platných slov",
  "auth.eyebrow": "Účet",
  "auth.heading.login": "Prihlásenie",
  "auth.heading.register": "Vytvorenie účtu",
  "auth.tab.login": "Prihlásiť sa",
  "auth.tab.register": "Registrovať",
  "auth.field.username": "Používateľské meno",
  "auth.field.password": "Heslo",
  "auth.submit.loading": "Prihlasujem...",
  "auth.submit.login": "Hrať",
  "auth.submit.register": "Vytvoriť účet a hrať",
  "meta.title": "Libre Tiles — slovná hra na webe s AI a živým multiplayerom",
  "meta.description":
    "Open-source slovná hra s AI súpermi, živými partiami proti ľuďom, chatom a vyladeným drag-and-drop hraním.",
  "error.checkFields": "Skontroluj zadané údaje.",
  "error.invalidCredentials": "Nesprávne používateľské meno alebo heslo",
  "error.sessionExpired": "Prihlásenie vypršalo. Prihlás sa znova.",
  "error.forbidden": "Na túto akciu nemáš oprávnenie.",
  "error.notFound": "Nenašlo sa.",
  "error.conflict": "Táto akcia je v rozpore s aktuálnym stavom partie.",
  "error.throttled.unknown": "Priveľa požiadaviek. Chvíľu počkaj a skús znova.",
  "error.throttled.oneMinute": "Priveľa požiadaviek. Skús znova asi za minútu.",
  "error.unavailable": "Služba je momentálne nedostupná. Skús to znova.",
  "error.generic": "Niečo sa pokazilo. Skús to znova.",
  "settings.uiLanguage.title": "Jazyk rozhrania",
  "settings.uiLanguage.description":
    "Menu, tlačidlá a správy. Zmena platí okamžite a len na tomto zariadení.",
  "settings.uiLanguage.en": "Angličtina",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.gameVariant.title": "Variant hry",
  "settings.gameVariant.description":
    "Písmená, vrecko a lexikón. Platí pre NOVÉ partie a nemení prebiehajúcu partiu. Toto nie je jazyk rozhrania.",
  "settings.gameVariant.english": "Angličtina",
  "settings.gameVariant.slovak": "Slovenčina",
  "settings.gameVariant.czech": "Čeština",
  "settings.gameVariant.polish": "Poľština",
  "draw.eyebrow": "Ťah o poradie",
  "draw.title": "Kto začína partiu",
  "draw.subtitle":
    "Začína ten, kto vytiahne písmeno bližšie k A. Žolík vyhráva vždy.",
  "draw.side.you": "Ty",
  "draw.side.ai": "AI",
  "draw.pending": "Ťahám písmená z vrecka...",
  "draw.blankCaption": "žolík",
  "draw.result.youStart": "Začínaš ty",
  "draw.result.aiStart": "Začína AI",
  "draw.reason.blankYou": "Tvoj žolík vyhráva ťah o poradie.",
  "draw.reason.blankAi": "Žolíka vytiahlo AI.",
  "draw.reason.bothBlank": "Obidve písmená sú žolíky, takže začínaš ty.",
};

export const skFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "error.throttled.minutes": (p) =>
    `Priveľa požiadaviek. Skús znova asi za ${p.minutes} ` +
    pluralSk(p.minutes, "minútu", "minúty", "minút") +
    ".",
  "draw.reason.closer": (p) => `${p.winner} je bližšie k A ako ${p.loser}.`,
};
