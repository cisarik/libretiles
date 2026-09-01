import type { Metadata } from "next";
import { cookies } from "next/headers";
import {
  LOCALE_COOKIE_NAME,
  localeFromCookieValue,
  type Locale,
} from "@/lib/i18n/locales";
import { enText } from "@/lib/i18n/messages.en";
import { skText } from "@/lib/i18n/messages.sk";
import "./globals.css";

async function readUiLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  return localeFromCookieValue(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}

function textFor(locale: Locale) {
  return locale === "sk" ? skText : enText;
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = await readUiLocale();
  const text = textFor(locale);
  return {
    title: text["meta.title"],
    description: text["meta.description"],
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
        {children}
      </body>
    </html>
  );
}
