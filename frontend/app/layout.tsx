import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { Toaster } from "@/components/ui/sonner";

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
        <div className="flex min-h-screen flex-col lg:flex-row">
          <AppSidebar />
          <main className="flex-1 p-6 lg:p-10">{children}</main>
        </div>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  );
}
