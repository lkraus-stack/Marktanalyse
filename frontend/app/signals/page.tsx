"use client";

import { useMemo, useState } from "react";
import { Filter, Inbox, SignalHigh } from "lucide-react";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, formatCurrency, parseNumeric } from "@/lib/api";
import type { AssetResponse, SignalResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import { signalToneClasses } from "@/src/components/ui/theme";

type SortMode = "strength" | "newest" | "assetType";
type AssetFilter = "all" | "stock" | "crypto";

interface EnrichedSignal extends SignalResponse {
  assetType: "stock" | "crypto";
  assetName: string;
}

function normalizeSignalComponent(value: number): number {
  if (Math.abs(value) <= 1) {
    return Math.max(0, Math.min(100, (value + 1) * 50));
  }
  return Math.max(0, Math.min(100, value));
}

export default function SignalsPage() {
  const router = useRouter();
  const [sortMode, setSortMode] = useState<SortMode>("strength");
  const [assetFilter, setAssetFilter] = useState<AssetFilter>("all");
  const [minStrength, setMinStrength] = useState(40);

  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, {
    refreshInterval: 120000,
    revalidateOnFocus: true,
  });
  const { data: signals, isLoading } = useSWR<SignalResponse[]>("/api/signals?limit=200", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });

  const enrichedSignals = useMemo<EnrichedSignal[]>(() => {
    const assetMap = new Map((assets ?? []).map((asset) => [asset.symbol, asset]));
    return (signals ?? []).map((signal) => {
      const asset = assetMap.get(signal.symbol);
      return {
        ...signal,
        assetType: asset?.asset_type ?? "stock",
        assetName: asset?.name ?? signal.symbol,
      };
    });
  }, [assets, signals]);

  const filteredAndSorted = useMemo(() => {
    const filtered = enrichedSignals.filter((signal) => {
      if (signal.signal_type === "hold") {
        return false;
      }
      if (signal.strength < minStrength) {
        return false;
      }
      if (assetFilter !== "all" && signal.assetType !== assetFilter) {
        return false;
      }
      return true;
    });

    const sorted = [...filtered].sort((left, right) => {
      if (sortMode === "newest") {
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      }
      if (sortMode === "assetType") {
        return left.assetType.localeCompare(right.assetType) || right.strength - left.strength;
      }
      return right.strength - left.strength;
    });

    return sorted;
  }, [assetFilter, enrichedSignals, minStrength, sortMode]);

  const buySignals = filteredAndSorted.filter((signal) => signal.signal_type === "buy");
  const sellSignals = filteredAndSorted.filter((signal) => signal.signal_type === "sell");

  return (
    <section className="space-y-5">
      <header className="trading-surface p-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-100">Signale</h1>
            <p className="text-sm text-slate-400">Buy/Sell Signale mit Score-Aufschluesselung und Reasoning.</p>
          </div>
          <SignalHigh className="h-5 w-5 text-blue-300" />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Sortierung</span>
            <select
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value as SortMode)}
              className="h-9 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="strength">Staerke</option>
              <option value="newest">Neueste</option>
              <option value="assetType">Asset-Typ</option>
            </select>
          </label>

          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Filter</span>
            <select
              value={assetFilter}
              onChange={(event) => setAssetFilter(event.target.value as AssetFilter)}
              className="h-9 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="all">Alle Assets</option>
              <option value="stock">Nur Aktien</option>
              <option value="crypto">Nur Krypto</option>
            </select>
          </label>

          <label className="space-y-1 text-xs">
            <span className="flex items-center justify-between text-slate-500">
              <span className="inline-flex items-center gap-1">
                <Filter className="h-3.5 w-3.5" />
                Min-Staerke
              </span>
              <span className="font-mono text-slate-300">{minStrength}</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={minStrength}
              onChange={(event) => setMinStrength(Number(event.target.value))}
              className="h-9 w-full accent-blue-500"
            />
          </label>
        </div>
      </header>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-[460px] rounded-2xl" />
          <Skeleton className="h-[460px] rounded-2xl" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SignalColumn title="Buy Signale" tone="buy" rows={buySignals} onCardClick={(symbol) => router.push(`/asset/${symbol}`)} />
          <SignalColumn title="Sell Signale" tone="sell" rows={sellSignals} onCardClick={(symbol) => router.push(`/asset/${symbol}`)} />
        </div>
      )}
    </section>
  );
}

interface SignalColumnProps {
  title: string;
  tone: "buy" | "sell";
  rows: EnrichedSignal[];
  onCardClick: (symbol: string) => void;
}

function SignalColumn({ title, tone, rows, onCardClick }: SignalColumnProps) {
  const headerClass = tone === "buy" ? "text-emerald-300" : "text-red-300";
  const headerBg = tone === "buy" ? "bg-emerald-500/12 border-emerald-500/40" : "bg-red-500/12 border-red-500/40";

  return (
    <section className={cn("trading-surface border p-4", headerBg)}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className={cn("text-base font-semibold", headerClass)}>{title}</h2>
        <span className="font-mono text-sm text-slate-200">{rows.length}</span>
      </div>

      <div className="trading-scrollbar max-h-[560px] space-y-2 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl bg-slate-800/30 p-4 text-sm text-slate-400">
            <Inbox className="h-5 w-5 text-slate-500" />
            Noch keine Signale - Daten werden gesammelt.
          </div>
        ) : (
          rows.map((signal) => (
            <button
              key={`${signal.symbol}-${signal.created_at}`}
              type="button"
              onClick={() => onCardClick(signal.symbol)}
              className="trading-hover-glow w-full rounded-xl border border-border/50 bg-slate-900/25 p-3 text-left"
            >
              <div className="mb-2 flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-base font-semibold text-slate-100">{signal.symbol}</p>
                    <Badge className={cn("border-0 uppercase", signalToneClasses(signal.signal_type))}>
                      {signal.signal_type}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-500">{signal.assetName}</p>
                </div>
                <ProgressRing
                  value={signal.strength}
                  size={56}
                  strokeWidth={6}
                  progressClassName={tone === "buy" ? "text-emerald-400" : "text-red-400"}
                />
              </div>

              <div className="mb-2 grid grid-cols-2 gap-2">
                <ComponentBar label="Sentiment" value={normalizeSignalComponent(signal.sentiment_component)} />
                <ComponentBar label="Technik" value={normalizeSignalComponent(signal.technical_component)} />
                <ComponentBar label="Volumen" value={normalizeSignalComponent(signal.volume_component)} />
                <ComponentBar label="Momentum" value={normalizeSignalComponent(signal.momentum_component)} />
              </div>

              <p className="line-clamp-3 text-sm text-slate-300">{signal.reasoning}</p>

              <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                <span className="font-mono">{formatCurrency(parseNumeric(signal.price_at_signal))}</span>
                <span>{new Date(signal.created_at).toLocaleString("de-DE")}</span>
              </div>
            </button>
          ))
        )}
      </div>
    </section>
  );
}

function ComponentBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
        <span>{label}</span>
        <span className="font-mono">{value.toFixed(0)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
        <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-300" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
