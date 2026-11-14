import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Audience Simulator · Campaign Lab",
  description: "Un laboratorio locale per simulare il pubblico, confrontare creatività e capire l'incertezza."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="it"><body>{children}</body></html>;
}
