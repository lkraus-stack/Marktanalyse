"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";

const NAVIGATION_ITEMS: Array<{ href: string; label: string }> = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/signale", label: "Signale" },
  { href: "/sentiment", label: "Sentiment" },
  { href: "/alerts", label: "Alerts" },
  { href: "/trading", label: "Trading" },
  { href: "/einstellungen", label: "Einstellungen" },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <aside className="w-full border-b border-border bg-card p-4 lg:min-h-screen lg:w-64 lg:border-b-0 lg:border-r">
      <div className="mb-4 flex items-center justify-between lg:mb-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Markt-Intelligence</p>
          <h1 className="text-lg font-semibold text-foreground">Control Center</h1>
        </div>
        <button
          type="button"
          className="rounded-md border border-border p-2 text-muted-foreground lg:hidden"
          onClick={() => setIsOpen((prev) => !prev)}
          aria-label="Navigation umschalten"
        >
          {isOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        </button>
      </div>

      <nav className={cn("grid gap-2", !isOpen && "hidden", "lg:grid")}>
        {NAVIGATION_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setIsOpen(false)}
            className={cn(
              "rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              pathname === item.href && "bg-muted text-foreground"
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
