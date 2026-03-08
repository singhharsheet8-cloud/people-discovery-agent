import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "People Discovery Agent",
  description: "AI-powered person discovery with multi-source search and confidence scoring",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        {children}
      </body>
    </html>
  );
}
