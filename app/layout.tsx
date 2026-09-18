import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RailPlan AI — Dual-Line Track Access Command",
  description: "A source-backed planning dashboard for the PS1 Line Alpha and Line Beta track-access challenge.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
