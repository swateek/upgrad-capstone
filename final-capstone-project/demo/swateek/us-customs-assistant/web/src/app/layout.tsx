import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// Open fonts, downloaded at build time and served by the app itself (no runtime font CDN).
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "US Customs Assistant",
  description:
    "Alcohol and tobacco allowances for returning US travellers: what you can bring, what you owe, and the rule behind each point.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable}`}>
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
