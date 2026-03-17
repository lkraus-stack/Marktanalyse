"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Inbox, Search } from "lucide-react";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { MiniSparkline } from "@/components/ui/mini-sparkline";
import { Skeleton } from "@/components/ui/skeleton";
import type { AssetTableRow } from "@/lib/types";
import { formatCurrency, formatPercent } from "@/lib/api";
import { cn } from "@/lib/utils";
import { signalToneClasses } from "@/src/components/ui/theme";

type SortableColumn = "symbol" | "price" | "change24h" | "sentimentScore" | "mentions";
type SortDirection = "asc" | "desc";
type AssetFilter = "all" | "stock" | "crypto";

interface AssetTableProps {
  rows: AssetTableRow[] | undefined;
  isLoading: boolean;
  sparklineBySymbol?: Record<string, number[]>;
}

function numericSortValue(value: string | number | null): number {
  if (value === null) {
    return Number.NEGATIVE_INFINITY;
  }
  if (typeof value === "string") {
    return Number.parseFloat(value);
  }
  return value;
}

export function AssetTable({ rows, isLoading, sparklineBySymbol }: AssetTableProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<AssetFilter>("all");
  const [sortColumn, setSortColumn] = useState<SortableColumn>("mentions");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const filteredRows = useMemo(() => {
    const source = rows ?? [];
    const lowerQuery = query.trim().toLowerCase();

    const byFilter = source.filter((row) => (filter === "all" ? true : row.assetType === filter));
    const byQuery = byFilter.filter((row) => {
      if (!lowerQuery) {
        return true;
      }
      return row.symbol.toLowerCase().includes(lowerQuery) || row.name.toLowerCase().includes(lowerQuery);
    });

    const sorted = [...byQuery].sort((left, right) => {
      const direction = sortDirection === "asc" ? 1 : -1;
      const leftValue = left[sortColumn];
      const rightValue = right[sortColumn];

      if (typeof leftValue === "string" && typeof rightValue === "string") {
        return leftValue.localeCompare(rightValue) * direction;
      }
      return (numericSortValue(leftValue) - numericSortValue(rightValue)) * direction;
    });

    return sorted;
  }, [filter, query, rows, sortColumn, sortDirection]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="relative w-full lg:max-w-sm">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-slate-500" />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Asset suchen..."
            className="h-10 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-9 text-sm text-slate-100 outline-none transition focus:border-blue-500/70 focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as AssetFilter)}
            className="h-10 rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
          >
            <option value="all">Alle</option>
            <option value="stock">Aktien</option>
            <option value="crypto">Krypto</option>
          </select>
          <select
            value={`${sortColumn}:${sortDirection}`}
            onChange={(event) => {
              const [column, direction] = event.target.value.split(":");
              setSortColumn(column as SortableColumn);
              setSortDirection(direction as SortDirection);
            }}
            className="h-10 rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
          >
            <option value="mentions:desc">Sortierung: Erwaehnungen</option>
            <option value="change24h:desc">Sortierung: 24h Gewinner</option>
            <option value="change24h:asc">Sortierung: 24h Verlierer</option>
            <option value="sentimentScore:desc">Sortierung: Sentiment hoch</option>
            <option value="price:desc">Sortierung: Preis hoch</option>
            <option value="symbol:asc">Sortierung: Symbol A-Z</option>
          </select>
        </div>
      </div>

      {filteredRows.length === 0 ? (
        <div className="trading-soft-surface flex min-h-36 flex-col items-center justify-center gap-2 rounded-xl border border-border/60 p-5 text-center">
          <Inbox className="h-5 w-5 text-slate-500" />
          <p className="text-sm text-slate-300">Noch keine Signale - Daten werden gesammelt.</p>
          <p className="text-xs text-slate-500">Passe Suchbegriff oder Filter an.</p>
        </div>
      ) : (
        <>
          <DesktopTable rows={filteredRows} onRowClick={(symbol) => router.push(`/asset/${symbol}`)} sparklineBySymbol={sparklineBySymbol} />
          <MobileCards rows={filteredRows} onRowClick={(symbol) => router.push(`/asset/${symbol}`)} sparklineBySymbol={sparklineBySymbol} />
        </>
      )}
    </div>
  );
}

interface RowsViewProps {
  rows: AssetTableRow[];
  sparklineBySymbol?: Record<string, number[]>;
  onRowClick: (symbol: string) => void;
}

function DesktopTable({ rows, sparklineBySymbol, onRowClick }: RowsViewProps) {
  return (
    <div className="hidden overflow-hidden rounded-xl border border-border/60 bg-[#0d0f1c] md:block">
      <div className="trading-scrollbar max-h-[420px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-[#131526]/95 backdrop-blur">
            <tr className="text-xs uppercase tracking-[0.12em] text-slate-500">
              <th className="px-4 py-3 text-left">Asset</th>
              <th className="px-4 py-3 text-left">Preis</th>
              <th className="px-4 py-3 text-left">24h%</th>
              <th className="px-4 py-3 text-left">Sentiment</th>
              <th className="px-4 py-3 text-left">Signal</th>
              <th className="px-4 py-3 text-right">Mentions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const changeUp = (row.change24h ?? 0) >= 0;
              const sentimentWidth = Math.max(2, ((row.sentimentScore + 1) / 2) * 100);
              return (
                <tr
                  key={row.symbol}
                  onClick={() => onRowClick(row.symbol)}
                  className="cursor-pointer border-t border-border/40 transition-all duration-200 hover:bg-[#1a1a2e]"
                >
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-100">{row.symbol}</div>
                    <div className="text-xs text-slate-500">{row.name}</div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-100">{formatCurrency(row.price)}</span>
                      <MiniSparkline
                        values={sparklineBySymbol?.[row.symbol]}
                        className="h-5 w-[60px]"
                        strokeClassName={changeUp ? "text-emerald-400" : "text-red-400"}
                      />
                    </div>
                  </td>
                  <td className={cn("px-4 py-3 font-mono", changeUp ? "text-emerald-300" : "text-red-300")}>
                    <span className="inline-flex items-center gap-1">
                      {changeUp ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                      {formatPercent(row.change24h)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className={cn("h-full rounded-full", row.sentimentScore >= 0 ? "bg-emerald-500" : "bg-red-500")}
                          style={{ width: `${sentimentWidth}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs text-slate-400">{row.sentimentScore.toFixed(2)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge className={cn("border-0 uppercase", signalToneClasses(row.signal))}>{row.signal}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300">{row.mentions}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MobileCards({ rows, sparklineBySymbol, onRowClick }: RowsViewProps) {
  return (
    <div className="space-y-2 md:hidden">
      {rows.map((row) => {
        const changeUp = (row.change24h ?? 0) >= 0;
        return (
          <button
            key={row.symbol}
            type="button"
            className="trading-hover-glow w-full rounded-xl border border-border/50 bg-[#0d0f1c] p-3 text-left"
            onClick={() => onRowClick(row.symbol)}
          >
            <div className="mb-2 flex items-center justify-between">
              <div>
                <p className="text-base font-semibold text-slate-100">{row.symbol}</p>
                <p className="text-xs text-slate-500">{row.name}</p>
              </div>
              <Badge className={cn("border-0 uppercase", signalToneClasses(row.signal))}>{row.signal}</Badge>
            </div>

            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="font-mono text-slate-100">{formatCurrency(row.price)}</span>
              <span className={changeUp ? "text-emerald-300" : "text-red-300"}>{formatPercent(row.change24h)}</span>
            </div>

            <div className="mb-2 flex items-center justify-between">
              <MiniSparkline
                values={sparklineBySymbol?.[row.symbol]}
                className="h-5 w-[70px]"
                strokeClassName={changeUp ? "text-emerald-400" : "text-red-400"}
              />
              <span className="text-xs text-slate-500">{row.mentions} Erwaehnungen</span>
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                className={cn("h-full rounded-full", row.sentimentScore >= 0 ? "bg-emerald-500" : "bg-red-500")}
                style={{ width: `${Math.max(2, ((row.sentimentScore + 1) / 2) * 100)}%` }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}
