import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Libre Tiles — Web Scrabble with AI and Live Multiplayer",
  description: "Open-source Scrabble with AI rivals, live human matches, chat, and polished drag-and-drop play.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
