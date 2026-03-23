"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BellRing,
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  Settings2,
  Signal,
  SmilePlus,
  TrendingUp,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface NavigationItem {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  aliases?: string[];
}

const NAVIGATION_ITEMS: NavigationItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/signals", label: "Signale", icon: Signal, aliases: ["/signale"] },
  { href: "/sentiment", label: "Discovery", icon: SmilePlus },
  { href: "/alerts", label: "Alerts", icon: BellRing },
  { href: "/trading", label: "Trading", icon: TrendingUp },
  { href: "/einstellungen", label: "Einstellungen", icon: Settings2 },
];

interface AppSidebarProps {
  isExpanded: boolean;
  isMobile: boolean;
  isMobileOpen: boolean;
  onCloseMobile: () => void;
  onToggleExpanded: () => void;
}

function isPathActive(pathname: string, item: NavigationItem): boolean {
  if (pathname === item.href) {
    return true;
  }
  if (item.aliases?.some((alias) => pathname.startsWith(alias))) {
    return true;
  }
  return pathname.startsWith(item.href);
}

export function AppSidebar({ isExpanded, isMobile, isMobileOpen, onCloseMobile, onToggleExpanded }: AppSidebarProps) {
  const pathname = usePathname();
  const widthClass = isExpanded ? "w-[240px]" : "w-16";

  return (
    <>
      {isMobile && isMobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[1px] md:hidden"
          aria-label="Sidebar schliessen"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={cn(
          "fixed top-14 bottom-0 left-0 z-40 border-r border-border/70 bg-[#0d0e1b]/95 backdrop-blur-md transition-all duration-200",
          isMobile ? "w-[240px]" : widthClass,
          isMobile && (isMobileOpen ? "translate-x-0" : "-translate-x-full")
        )}
      >
        <div className="flex h-full flex-col p-2.5">
          <div className={cn("px-2 pb-3", !isExpanded && !isMobile && "px-0 text-center")}>
            <p className={cn("text-[11px] uppercase tracking-[0.2em] text-slate-500", !isExpanded && !isMobile && "hidden")}>
              Navigation
            </p>
          </div>

          <nav className="flex-1 space-y-1.5">
            {NAVIGATION_ITEMS.map((item) => {
              const active = isPathActive(pathname, item);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => {
                    if (isMobile) {
                      onCloseMobile();
                    }
                  }}
                  title={!isExpanded && !isMobile ? item.label : undefined}
                  className={cn(
                    "group relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-slate-300 transition-all duration-200 hover:bg-[#1a1a2e] hover:text-slate-100",
                    !isExpanded && !isMobile && "justify-center px-0",
                    active && "bg-[#18243f] text-blue-200 shadow-[0_0_0_1px_rgba(59,130,246,0.35)]"
                  )}
                >
                  <span
                    className={cn(
                      "absolute left-0 h-6 w-1 rounded-r-full bg-transparent transition-all",
                      active && "bg-blue-400 shadow-[0_0_10px_rgba(59,130,246,0.8)]"
                    )}
                  />
                  <Icon className={cn("h-[18px] w-[18px] shrink-0", active && "text-blue-300")} />
                  {(isExpanded || isMobile) && <span className="truncate">{item.label}</span>}
                </Link>
              );
            })}
          </nav>

          {!isMobile && (
            <button
              type="button"
              className={cn(
                "mt-2 flex h-10 items-center rounded-lg border border-border/70 bg-[#12121e] px-3 text-sm text-slate-300 transition-all hover:bg-[#191a2e] hover:text-slate-100",
                isExpanded ? "justify-between" : "justify-center px-0"
              )}
              onClick={onToggleExpanded}
              aria-label={isExpanded ? "Sidebar einklappen" : "Sidebar ausklappen"}
            >
              {isExpanded ? (
                <>
                  <span>Einklappen</span>
                  <ChevronLeft className="h-4 w-4" />
                </>
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
