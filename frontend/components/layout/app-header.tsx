"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Bell, Menu, Search, Settings2 } from "lucide-react";

import { fetchJson } from "@/lib/api";
import type { AlertResponse, AssetResponse, WebSocketStatus } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useWebSocket } from "@/hooks/useWebSocket";

interface AppHeaderProps {
  sidebarOffset: number;
  onOpenMobileMenu: () => void;
}

function statusColor(status: WebSocketStatus): string {
  if (status === "connected") {
    return "bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.85)]";
  }
  if (status === "connecting") {
    return "bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.85)]";
  }
  return "bg-red-400 shadow-[0_0_8px_rgba(239,68,68,0.85)]";
}

export function AppHeader({ sidebarOffset, onOpenMobileMenu }: AppHeaderProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");

  const websocketUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/prices";
  const { status } = useWebSocket(websocketUrl);
  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, { refreshInterval: 120000 });
  const { data: alerts } = useSWR<AlertResponse[]>("/api/alerts", fetchJson, { refreshInterval: 45000 });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const notificationCount = alerts?.filter((item) => item.is_enabled).length ?? 0;

  return (
    <header
      className="fixed top-0 right-0 z-50 h-14 border-b border-border/60 bg-[#0a0a14]/95 backdrop-blur-md"
      style={{ left: sidebarOffset }}
    >
      <div className="flex h-full items-center justify-between gap-3 px-4 md:px-5">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-[#12121e] text-slate-200 md:hidden"
            onClick={onOpenMobileMenu}
            aria-label="Menue oeffnen"
          >
            <Menu className="h-4 w-4" />
          </button>
          <Link href="/dashboard" className="hidden text-[15px] font-medium tracking-tight text-slate-200 sm:inline-flex">
            Kapitalmarkt Analyse
          </Link>
        </div>

        <form
          className="flex w-full max-w-xl items-center gap-2 rounded-xl border border-border/70 bg-[#12121e]/90 px-3 py-1.5"
          onSubmit={(event) => {
            event.preventDefault();
            const normalized = query.trim().toUpperCase();
            if (!normalized) {
              return;
            }
            router.push(`/asset/${normalized}`);
            setQuery("");
          }}
        >
          <Search className="h-4 w-4 text-slate-500" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            list="asset-search-list"
            placeholder="Asset suchen..."
            className="h-7 w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
          />
          <span className="hidden rounded border border-border/70 px-1.5 py-0.5 text-[10px] text-slate-400 sm:inline">
            Cmd+K
          </span>
          <datalist id="asset-search-list">
            {(assets ?? []).slice(0, 200).map((asset) => (
              <option key={asset.symbol} value={asset.symbol}>
                {asset.name}
              </option>
            ))}
          </datalist>
        </form>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-full border border-border/70 bg-[#12121e] px-2.5 py-1 sm:flex">
            <span className={cn("h-2 w-2 rounded-full", statusColor(status))} />
            <span className="text-xs text-slate-300">{status === "connected" ? "Live" : status}</span>
          </div>

          <Link
            href="/alerts"
            className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-[#12121e] text-slate-300 transition-colors hover:text-slate-100"
            aria-label="Benachrichtigungen"
          >
            <Bell className="h-4 w-4" />
            {notificationCount > 0 && (
              <span className="absolute -top-1 -right-1 inline-flex min-h-4 min-w-4 items-center justify-center rounded-full bg-blue-500 px-1 text-[10px] font-semibold text-white">
                {notificationCount > 9 ? "9+" : notificationCount}
              </span>
            )}
          </Link>

          <Link
            href="/einstellungen"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border/70 bg-[#12121e] text-slate-300 transition-colors hover:text-slate-100"
            aria-label="Einstellungen"
          >
            <Settings2 className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </header>
  );
}
