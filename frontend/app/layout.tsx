import type {Metadata} from "next";
import localFont from "next/font/local";
import {AppProvider} from "@/components/app-provider";
import {AppShell} from "@/components/app-shell";
import "./globals.css";

const jost = localFont({
  src: "./fonts/Jost-latin.woff2",
  weight: "400 700",
  display: "swap",
  variable: "--font-jost",
  fallback: ["system-ui", "sans-serif"]
});

export const metadata: Metadata = {
  title: "Audience Simulator",
  description: "Confronta le tue creatività con un pubblico simulato prima di spendere il budget."
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="it" className={jost.variable}>
      <body>
        <a className="skip" href="#contenuto">Vai al contenuto</a>
        <AppProvider>
          <AppShell>{children}</AppShell>
        </AppProvider>
      </body>
    </html>
  );
}
