import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Libre Tiles — Web Scrabble with AI",
  description: "Open-source Scrabble game with AI opponents, beautiful UI, and advanced drag-and-drop.",
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
