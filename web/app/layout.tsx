import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradeLens AI",
  description:
    "Post-trade reflection journal and analytics for SMC/ICT day traders.",
  // Auth pages must not be indexed: they are functional surfaces, not content,
  // and an indexed reset page invites traffic that should only ever arrive by
  // email link.
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
