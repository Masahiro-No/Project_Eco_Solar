import type { Metadata } from "next";
import localFont from "next/font/local";
import { Noto_Sans_Thai } from "next/font/google";
import { cookies } from "next/headers";
import "./globals.css";
import { AppLayout } from "@/components/layout/AppLayout";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});
// Geist has no Thai glyphs; Noto Sans Thai covers Thai + Latin
const notoThai = Noto_Sans_Thai({
  subsets: ["thai", "latin"],
  variable: "--font-noto-thai",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SolarDSS - Solar Power Forecasting & Decision Support",
  description: "Solar Power Forecasting and Decision Support System",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const saved = (await cookies()).get("solar_locale")?.value;
  const locale = saved === "en" ? "en" : "th";

  return (
    <html lang={locale}>
      <body
        className={`${notoThai.variable} ${geistSans.variable} ${geistMono.variable} font-sans antialiased`}
        suppressHydrationWarning
      >
        <AppLayout initialLocale={locale}>{children}</AppLayout>
      </body>
    </html>
  );
}
