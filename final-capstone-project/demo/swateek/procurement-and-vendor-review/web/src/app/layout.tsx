import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Procurement copilot (draft)",
  description: "Policy Q&A, vendor screening and draft bid scoring. Drafts only.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="draft-watermark min-h-screen antialiased">{children}</body>
    </html>
  );
}
