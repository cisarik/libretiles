import type { FnKey, TextKey } from "./messages.en";
import { enFn } from "./messages.en";
import { pluralPl } from "./plural";

export const plText: Record<TextKey, string> = {
  "landing.brand": "Libre Tiles",
  "landing.titleLine1": "Premium Libre Tiles,",
  "landing.titleLine2": "ludzie i AI.",
  "landing.lead":
    "Open-source gra słowna z parowaniem na żywo, ostrymi rywalami AI, dopracowaną oprawą planszy i historią gotową na twoją następną partię.",
  "landing.card.ai.title": "Duele AI",
  "landing.card.ai.body": "Partie premium przeciw AI",
  "landing.card.queue.title": "Kolejka na żywo",
  "landing.card.queue.body": "Synchronizacja w czasie rzeczywistym i chat",
  "landing.card.saved.title": "Zapisane partie",
  "landing.card.saved.body": "Wróć do partii przeciw AI lub człowiekowi",
  "landing.footnote":
    "Open source • Collins Scrabble Words 2019 • 279\u00A0496 poprawnych słów",
  "auth.eyebrow": "Konto",
  "auth.heading.login": "Logowanie",
  "auth.heading.register": "Utworzenie konta",
  "auth.tab.login": "Zaloguj się",
  "auth.tab.register": "Zarejestruj się",
  "auth.field.username": "Nazwa użytkownika",
  "auth.field.password": "Hasło",
  "auth.submit.loading": "Logowanie...",
  "auth.submit.login": "Graj",
  "auth.submit.register": "Utwórz konto i graj",
  "meta.title":
    "Libre Tiles — gra słowna w przeglądarce z AI i multiplayerem na żywo",
  "meta.description":
    "Open-source gra słowna z rywalami AI, partiami na żywo przeciw ludziom, chatem i dopracowaną rozgrywką drag-and-drop.",
  "error.checkFields": "Sprawdź wprowadzone dane.",
  "error.invalidCredentials": "Nieprawidłowa nazwa użytkownika lub hasło",
  "error.sessionExpired": "Sesja wygasła. Zaloguj się ponownie.",
  "error.forbidden": "Nie masz uprawnień do tej akcji.",
  "error.notFound": "Nie znaleziono.",
  "error.conflict": "Ta akcja jest sprzeczna z aktualnym stanem partii.",
  "error.throttled.unknown": "Zbyt wiele żądań. Poczekaj chwilę i spróbuj ponownie.",
  "error.throttled.oneMinute": "Zbyt wiele żądań. Spróbuj ponownie za około minutę.",
  "error.unavailable": "Usługa jest chwilowo niedostępna. Spróbuj ponownie.",
  "error.generic": "Coś poszło nie tak. Spróbuj ponownie.",
  "settings.uiLanguage.title": "Język interfejsu",
  "settings.uiLanguage.description":
    "Menu, przyciski i komunikaty. Zmiana działa natychmiast i tylko na tym urządzeniu.",
  "settings.uiLanguage.en": "English",
  "settings.uiLanguage.sk": "Slovenčina",
  "settings.uiLanguage.cs": "Čeština",
  "settings.uiLanguage.pl": "Polski",
  "settings.gameVariant.title": "Wariant gry",
  "settings.gameVariant.description":
    "Płytki, woreczek i leksykon. Dotyczy tylko NOWYCH partii i nie zmienia trwającej partii. To nie jest język interfejsu.",
  "settings.gameVariant.english": "Angielski",
  "settings.gameVariant.slovak": "Słowacki",
  "settings.gameVariant.czech": "Czeski",
  "settings.gameVariant.polish": "Polski",
  "draw.eyebrow": "Losowanie o początek",
  "draw.title": "Kto zaczyna partię",
  "draw.subtitle":
    "Zaczyna ten, kto wyciągnie płytkę bliżej A. Blank zawsze wygrywa.",
  "draw.side.you": "Ty",
  "draw.side.ai": "AI",
  "draw.pending": "Wyciągam płytki z woreczka...",
  "draw.blankCaption": "blank",
  "draw.result.youStart": "Zaczynasz ty",
  "draw.result.aiStart": "Zaczyna AI",
  "draw.reason.blankYou": "Twój blank wygrywa losowanie.",
  "draw.reason.blankAi": "Blanka ma AI.",
  "draw.reason.bothBlank": "Obie płytki to blanki, więc zaczynasz ty.",
};

export const plFn: { [K in FnKey]: (typeof enFn)[K] } = {
  "error.throttled.minutes": (p) =>
    `Zbyt wiele żądań. Spróbuj ponownie za około ${p.minutes} ` +
    pluralPl(p.minutes, "minutę", "minuty", "minut") +
    ".",
  "draw.reason.closer": (p) => `${p.winner} jest bliżej A niż ${p.loser}.`,
};
