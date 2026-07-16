import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { SutraProvider } from "@/components/SutraProvider";
import { Nav } from "@/components/Nav";
import { DemoDock } from "@/components/DemoDock";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  fallback: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  title: "SUTRA — Security Unified Telemetry & Risk Analytics",
  description:
    "Bank SOC console: fused security + core-banking telemetry, explainable ML-DSA-65-signed alerts.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-night font-sans text-body antialiased">
        <SutraProvider>
          <Nav />
          <main className="mx-auto w-full max-w-[1700px] px-5 pb-40 pt-5">
            {children}
          </main>
          <DemoDock />
        </SutraProvider>
      </body>
    </html>
  );
}
