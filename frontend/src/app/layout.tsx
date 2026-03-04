import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Orchestrator",
  description: "Multi-agent coding orchestrator",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
