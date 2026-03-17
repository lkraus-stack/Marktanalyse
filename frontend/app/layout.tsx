import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import { ThemeStyles } from "@/src/components/ui/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "Markt-Intelligence Plattform",
  description: "Markt-Intelligence und Auto-Trading Plattform",
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="de" className="dark">
      <body className="bg-background text-foreground antialiased">
        <ThemeStyles />
        <AppShell>{children}</AppShell>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
