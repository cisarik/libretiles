import type { Metadata } from "next";
import { cookies } from "next/headers";
import {
  LOCALE_COOKIE_NAME,
  localeFromCookieValue,
  type Locale,
} from "@/lib/i18n/locales";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { t } from "@/lib/i18n/translate";
import "./globals.css";

async function readUiLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  return localeFromCookieValue(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = await readUiLocale();
  return {
    title: t(locale, "meta.title"),
    description: t(locale, "meta.description"),
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await readUiLocale();
  return (
    <html lang={locale} className="dark">
      <body className="antialiased">
        <LocaleProvider value={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
