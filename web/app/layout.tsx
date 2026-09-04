import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Internship Radar",
  description: "A self-hosted internship tracker for CS/SWE roles, Seattle-first.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          rel="preconnect"
          href="https://fonts.googleapis.com"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
