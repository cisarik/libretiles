import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralCs } from "./plural";

export const csText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "lidé i AI.",
  "landing.lead":
    "Open-source slovní hra s párováním naživo, ostrými AI soupeři, dopracovanou grafikou desky a historií připravenou na tvou další partii.",
  "landing.card.ai.title": "AI duely",
  "landing.card.ai.body": "Prémiové partie proti AI",
  "landing.card.queue.title": "Živá fronta",
  "landing.card.queue.body": "Synchronizace v reálném čase a chat",
  "landing.card.saved.title": "Uložené partie",
  "landing.card.saved.body": "Pokračuj v partii proti AI nebo člověku",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 platných slov",
  "auth.eyebrow": "Účet",
  "auth.heading.login": "Přihlášení",
  "auth.heading.register": "Vytvoření účtu",
  "auth.tab.login": "Přihlásit se",
  "auth.tab.register": "Registrovat",
  "auth.field.username": "Uživatelské jméno",
  "auth.field.password": "Heslo",
  "auth.submit.loading": "Přihlašuji...",
  "auth.submit.login": "Hrát",
  "auth.submit.register": "Vytvořit účet a hrát",
  "meta.title": "Libre Tiles — slovní hra na webu s AI a živým multiplayerem",
  "meta.description":
    "Open-source slovní hra s AI soupeři, živými partiemi proti lidem, chatem a vyladěným drag-and-drop hraním.",
  "error.checkFields": "Zkontroluj zadané údaje.",
  "error.invalidCredentials": "Nesprávné uživatelské jméno nebo heslo",
  "error.sessionExpired": "Přihlášení vypršelo. Přihlas se znovu.",
  "error.forbidden": "K této akci nemáš oprávnění.",
  "error.notFound": "Nenalezeno.",
  "error.conflict": "Tato akce je v rozporu s aktuálním stavem partie.",
  "error.throttled.unknown": "Příliš mnoho požadavků. Chvíli počkej a zkus to znovu.",
  "error.throttled.oneMinute": "Příliš mnoho požadavků. Zkus to znovu asi za minutu.",
  "error.unavailable": "Služba je momentálně nedostupná. Zkus to znovu.",
  "error.generic": "Něco se pokazilo. Zkus to znovu.",
  "settings.uiLanguage.title": "Jazyk rozhraní",
  "settings.uiLanguage.description":
    "Menu, tlačítka a zprávy. Změna platí okamžitě a jen na tomto zařízení.",
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "settings.gameVariant.title": "Varianta hry",
  "settings.gameVariant.description":
    "Kameny, sáček a lexikon. Platí pro NOVÉ partie a nemění probíhající partii. Toto není jazyk rozhraní.",
  "settings.gameVariant.english": "Angličtina",
  "settings.gameVariant.slovak": "Slovenština",
  "settings.gameVariant.czech": "Čeština",
  "settings.gameVariant.polish": "Polština",
  "draw.eyebrow": "Losování o začátek",
  "draw.title": "Kdo začíná partii",
  "draw.subtitle":
    "Začíná ten, kdo vytáhne kámen blíž k A. Žolík vyhrává vždy.",
  "draw.side.you": "Ty",
  "draw.side.ai": "AI",
  "draw.pending": "Tahám kameny ze sáčku...",
  "draw.blankCaption": "žolík",
  "draw.result.youStart": "Začínáš ty",
  "draw.result.aiStart": "Začíná AI",
  "draw.reason.blankYou": "Tvůj žolík vyhrává losování.",
  "draw.reason.blankAi": "Žolíka vytáhlo AI.",
  "draw.reason.bothBlank": "Oba kameny jsou žolíci, takže začínáš ty.",
  "controls.play": "Zahrát",
  "controls.pass": "Vzdát tah",
  "controls.exchange": "Vyměnit",
  "controls.confirmExchange": "Potvrdit výměnu",
  "controls.cancel": "Zrušit",
  "board.pts": "b.",
  "board.pinchToZoom": "Zoom dvěma prsty",
  "board.dragToPan": "Posuň tažením",
  "board.hide": "Skrýt",
  "board.reset": "Reset",
  "rack.empty": "Zásobník je prázdný",
  "blank.chooseLetter": "Vyber písmeno pro žolíka",
  "chat.title": "Chat partie",
  "chat.empty": "Zatím žádné zprávy.",
  "chat.you": "Ty",
  "chat.unavailable": "Chat je nedostupný",
  "chat.placeholder": "Napiš něco",
  "chat.send": "Poslat",
};

export const csFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "error.throttled.minutes": (p) =>
    `Příliš mnoho požadavků. Zkus to znovu asi za ${p.minutes} ` +
    pluralCs(p.minutes, "minutu", "minuty", "minut") +
    ".",
  "draw.reason.closer": (p) => `${p.winner} je blíž k A než ${p.loser}.`,
  "controls.tilesSelected": (p) =>
    `Výběr: ${p.count} ` + pluralCs(p.count, "kámen", "kameny", "kamenů"),
};
