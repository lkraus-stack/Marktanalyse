"use client";

import { useMemo, useState } from "react";
import { ArrowUpDown, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { mutate } from "swr";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { apiHeaders, formatCurrency, formatPercent } from "@/lib/api";
import type { AssetTableRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type SortableColumn = "symbol" | "price" | "change24h" | "sentimentScore" | "mentions";
type SortDirection = "asc" | "desc";
type AssetFilter = "all" | "stock" | "crypto";
type ListFilter = "all" | "suggested" | "watchlist" | "holding";

interface AssetTableProps {
  rows: AssetTableRow[] | undefined;
  isLoading: boolean;
}

function getSignalVariant(signal: AssetTableRow["signal"]): "default" | "secondary" | "destructive" {
  if (signal === "buy") {
    return "default";
  }
  if (signal === "sell") {
    return "destructive";
  }
  return "secondary";
}

export function AssetTable({ rows, isLoading }: AssetTableProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<AssetFilter>("all");
  const [listFilter, setListFilter] = useState<ListFilter>("all");
  const [sortColumn, setSortColumn] = useState<SortableColumn>("mentions");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [updatingSymbol, setUpdatingSymbol] = useState<string | null>(null);

  const filteredRows = useMemo(() => {
    const lowerQuery = query.trim().toLowerCase();
    const source = rows ?? [];

    const byFilter = source.filter((row) => (filter === "all" ? true : row.assetType === filter));
    const byList = byFilter.filter((row) => {
      if (listFilter === "all") {
        return true;
      }
      if (listFilter === "suggested") {
        return row.isToolSuggested;
      }
      if (listFilter === "watchlist") {
        return row.watchStatus === "watchlist";
      }
      return row.watchStatus === "holding";
    });
    const byQuery = byList.filter((row) => {
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

      const safeLeft = leftValue === null ? Number.NEGATIVE_INFINITY : Number(leftValue);
      const safeRight = rightValue === null ? Number.NEGATIVE_INFINITY : Number(rightValue);
      return (safeLeft - safeRight) * direction;
    });

    return sorted;
  }, [filter, listFilter, query, rows, sortColumn, sortDirection]);

  const toggleSort = (column: SortableColumn) => {
    if (sortColumn === column) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortColumn(column);
    setSortDirection("desc");
  };

  const updateWatchStatus = async (
    symbol: string,
    watchStatus: "none" | "watchlist" | "holding"
  ) => {
    setUpdatingSymbol(symbol);
    try {
      const response = await fetch(`/api/assets/${symbol}/watch`, {
        method: "PATCH",
        headers: apiHeaders(true),
        body: JSON.stringify({ watch_status: watchStatus }),
      });
      if (!response.ok) {
        throw new Error("watch update failed");
      }
      toast.success(`Status fuer ${symbol} gespeichert.`);
      await Promise.all([
        mutate("/api/assets"),
        mutate("/api/signals/recommendations?direction=all&include_hold=true&min_strength=0&limit=8"),
      ]);
    } catch {
      toast.error(`Status fuer ${symbol} konnte nicht gespeichert werden.`);
    } finally {
      setUpdatingSymbol(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="relative w-full md:max-w-sm">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Asset suchen..."
            className="h-10 w-full rounded-md border border-input bg-background px-9 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <div className="flex w-full gap-2 md:w-auto">
          <Select value={filter} onValueChange={(value) => setFilter(value as AssetFilter)}>
            <SelectTrigger className="w-full md:w-44">
              <SelectValue placeholder="Asset-Typ" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle</SelectItem>
              <SelectItem value="stock">Aktien</SelectItem>
              <SelectItem value="crypto">Krypto</SelectItem>
            </SelectContent>
          </Select>
          <Select value={listFilter} onValueChange={(value) => setListFilter(value as ListFilter)}>
            <SelectTrigger className="w-full md:w-44">
              <SelectValue placeholder="Liste" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Listen</SelectItem>
              <SelectItem value="suggested">Tool Vorschlaege</SelectItem>
              <SelectItem value="watchlist">Watchlist</SelectItem>
              <SelectItem value="holding">Holding</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("symbol")}>
                  Asset <ArrowUpDown className="h-3.5 w-3.5" />
                </button>
              </TableHead>
              <TableHead>
                <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("price")}>
                  Preis <ArrowUpDown className="h-3.5 w-3.5" />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1"
                  onClick={() => toggleSort("change24h")}
                >
                  24h% <ArrowUpDown className="h-3.5 w-3.5" />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1"
                  onClick={() => toggleSort("sentimentScore")}
                >
                  Sentiment <ArrowUpDown className="h-3.5 w-3.5" />
                </button>
              </TableHead>
              <TableHead>
                <button
                  type="button"
                  className="inline-flex items-center gap-1"
                  onClick={() => toggleSort("mentions")}
                >
                  Erwaehnungen <ArrowUpDown className="h-3.5 w-3.5" />
                </button>
              </TableHead>
              <TableHead>Signal</TableHead>
              <TableHead className="text-right">Aktionen</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-20 text-center text-muted-foreground">
                  Keine passenden Assets gefunden.
                </TableCell>
              </TableRow>
            ) : (
              filteredRows.map((row) => (
                <TableRow
                  key={row.symbol}
                  className="cursor-pointer"
                  onClick={() => router.push(`/assets/${row.symbol}`)}
                >
                  <TableCell>
                    <div className="font-medium text-foreground">{row.symbol}</div>
                    <div className="text-xs text-muted-foreground">{row.name}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {row.isToolSuggested && (
                        <Badge variant="secondary" className="text-[10px]">
                          Vorschlag
                        </Badge>
                      )}
                      {row.watchStatus === "watchlist" && (
                        <Badge variant="outline" className="text-[10px]">
                          Watchlist
                        </Badge>
                      )}
                      {row.watchStatus === "holding" && (
                        <Badge variant="outline" className="text-[10px]">
                          Holding
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>{formatCurrency(row.price)}</TableCell>
                  <TableCell
                    className={cn(
                      row.change24h === null
                        ? "text-muted-foreground"
                        : row.change24h >= 0
                          ? "text-green-400"
                          : "text-red-400"
                    )}
                  >
                    {formatPercent(row.change24h)}
                  </TableCell>
                  <TableCell>{row.sentimentScore.toFixed(2)}</TableCell>
                  <TableCell>{row.mentions}</TableCell>
                  <TableCell>
                    <Badge variant={getSignalVariant(row.signal)}>{row.signal.toUpperCase()}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Select
                        value={row.watchStatus}
                        onValueChange={(value) =>
                          updateWatchStatus(row.symbol, value as "none" | "watchlist" | "holding")
                        }
                        disabled={updatingSymbol === row.symbol}
                      >
                        <SelectTrigger
                          className="h-8 w-[130px]"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <SelectValue placeholder="Status" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          <SelectItem value="watchlist">watchlist</SelectItem>
                          <SelectItem value="holding">holding</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(event) => {
                          event.stopPropagation();
                          router.push(`/assets/${row.symbol}`);
                        }}
                      >
                        Details
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
