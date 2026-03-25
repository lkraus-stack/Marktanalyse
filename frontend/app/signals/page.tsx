"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Filter, History, Inbox, ShieldCheck, SignalHigh, SlidersHorizontal, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, formatCurrency, parseNumeric } from "@/lib/api";
import type {
  AssetResponse,
  SignalJournalRowResponse,
  SignalResponse,
  SignalScorecardResponse,
  SignalStrategyResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { signalToneClasses } from "@/src/components/ui/theme";

type SortMode = "strength" | "newest" | "assetType";
type AssetFilter = "all" | "stock" | "crypto";
type Horizon = "24h" | "72h" | "7d";

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

function formatDateTime(value: string | null): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("de-DE");
}

function formatSignedPercent(value: number | null): string {
  if (value === null) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function formatSignedScore(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

export default function SignalsPage() {
  const router = useRouter();
  const [sortMode, setSortMode] = useState<SortMode>("strength");
  const [assetFilter, setAssetFilter] = useState<AssetFilter>("all");
  const [scoreThreshold, setScoreThreshold] = useState(40);
  const [evaluationHorizon, setEvaluationHorizon] = useState<Horizon>("72h");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, {
    refreshInterval: 120000,
    revalidateOnFocus: true,
  });
  const { data: signals, isLoading: isSignalsLoading } = useSWR<SignalResponse[]>("/api/signals?limit=200", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: scorecard, isLoading: isScorecardLoading } = useSWR<SignalScorecardResponse>(
    `/api/signals/scorecard?horizon=${evaluationHorizon}&asset_type=${assetFilter}&limit=300`,
    fetchJson,
    {
      refreshInterval: 60000,
      revalidateOnFocus: true,
    }
  );
  const { data: journal, isLoading: isJournalLoading } = useSWR<SignalJournalRowResponse[]>(
    `/api/signals/journal?horizon=${evaluationHorizon}&asset_type=${assetFilter}&limit=40`,
    fetchJson,
    {
      refreshInterval: 60000,
      revalidateOnFocus: true,
    }
  );
  const { data: strategies, isLoading: isStrategiesLoading } = useSWR<SignalStrategyResponse[]>(
    "/api/signals/strategies",
    fetchJson,
    {
      refreshInterval: 300000,
      revalidateOnFocus: false,
    }
  );

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

  const activeSignals = useMemo(() => {
    return enrichedSignals.filter((signal) => (assetFilter === "all" ? true : signal.assetType === assetFilter));
  }, [assetFilter, enrichedSignals]);

  const actionableSignals = useMemo(() => {
    const filtered = activeSignals.filter((signal) => {
      if (signal.signal_type === "hold") {
        return false;
      }
      return signal.strength >= scoreThreshold;
    });
    return [...filtered].sort((left, right) => {
      if (sortMode === "newest") {
        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      }
      if (sortMode === "assetType") {
        return left.assetType.localeCompare(right.assetType) || right.strength - left.strength;
      }
      return right.strength - left.strength;
    });
  }, [activeSignals, scoreThreshold, sortMode]);

  const buySignals = actionableSignals.filter((signal) => signal.signal_type === "buy");
  const sellSignals = actionableSignals.filter((signal) => signal.signal_type === "sell");
  const holdSignalsCount = activeSignals.filter((signal) => signal.signal_type === "hold").length;
  const paperJournalRows = useMemo(
    () => (journal ?? []).filter((row) => row.linked_trade !== null),
    [journal]
  );
  const activePresetCount = (strategies ?? []).filter((item) => item.status === "active").length;

  return (
    <section className="space-y-6">
      <header className="trading-surface p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <SignalHigh className="h-5 w-5 text-blue-300" />
              <h1 className="text-2xl font-semibold text-slate-100">Signale</h1>
            </div>
            <p className="max-w-3xl text-sm text-slate-400">
              Diese Seite trennt bewusst zwischen aktuellen Live-Signalen, historischer Bewertung, Signal-zu-Paper-Trade
              und der Strategie-Bibliothek. Discovery bleibt ein separates Analyse-Tool.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className="border-0 bg-blue-500/15 text-blue-200">Live-Signale</Badge>
            <Badge className="border-0 bg-emerald-500/15 text-emerald-200">Bewertungshorizont {evaluationHorizon}</Badge>
            <Badge className="border-0 bg-violet-500/15 text-violet-200">{activePresetCount} aktive Strategie</Badge>
          </div>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <InfoCard
          title="Live-Signal"
          description="Die aktuelle Richtung jetzt. Sichtbar sind nur aktive Buy-, Sell- und Hold-Signale aus der Engine."
        />
        <InfoCard
          title="Signalstaerke vs. Score"
          description="Signalstaerke ist der Betrag des Scores. Der Composite-Score selbst enthaelt die Richtung und kann positiv oder negativ sein."
        />
        <InfoCard
          title="Bewertungshorizont"
          description="24h, 72h oder 7d wirken nur auf die Rueckschau und Scorecard. Das veraendert nicht das aktuelle Live-Signal."
        />
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="Aktive Signale" value={String(activeSignals.length)} subtitle="inklusive Hold" />
        <MetricCard title="Buy jetzt" value={String(buySignals.length)} subtitle={`Filter ab Staerke ${scoreThreshold}`} tone="emerald" />
        <MetricCard title="Sell jetzt" value={String(sellSignals.length)} subtitle={`Filter ab Staerke ${scoreThreshold}`} tone="red" />
        <MetricCard title="Hold jetzt" value={String(holdSignalsCount)} subtitle="sichtbar in der Uebersicht, nicht als Aktion" tone="blue" />
      </section>

      <section className="trading-surface border p-4">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Aktuelle Signale</h2>
            <p className="text-sm text-slate-400">
              Fokus auf aktuelle Buy- und Sell-Signale. Der Staerke-Filter ist nur ein Anzeige-Filter und keine eigene Strategie.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAdvancedFilters((current) => !current)}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-border/70 bg-[#12121e] px-3 text-sm text-slate-200 transition hover:bg-[#191a2e]"
          >
            <SlidersHorizontal className="h-4 w-4" />
            {showAdvancedFilters ? "Weniger Filter" : "Mehr Filter"}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Sortierung</span>
            <select
              value={sortMode}
              onChange={(event) => setSortMode(event.target.value as SortMode)}
              className="h-9 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="strength">Signalstaerke</option>
              <option value="newest">Neueste Signale</option>
              <option value="assetType">Asset-Typ</option>
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Asset-Typ</span>
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
            <span className="text-slate-500">Aktive Strategie</span>
            <div className="flex h-9 items-center rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100">
              Composite 1H
            </div>
          </label>
        </div>

        {showAdvancedFilters && (
          <div className="mt-4 rounded-xl border border-border/60 bg-slate-900/20 p-4">
            <label className="space-y-1 text-xs">
              <span className="flex items-center justify-between text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <Filter className="h-3.5 w-3.5" />
                  Signalfilter ab Staerke
                </span>
                <span className="font-mono text-slate-300">{scoreThreshold}</span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={scoreThreshold}
                onChange={(event) => setScoreThreshold(Number(event.target.value))}
                className="h-9 w-full accent-blue-500"
              />
            </label>
            <p className="mt-2 text-xs text-slate-500">
              Dieser Filter blendet nur schwache Signale aus. Er aendert nicht, wie das Backend Signale berechnet.
            </p>
          </div>
        )}

        {isSignalsLoading ? (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Skeleton className="h-[460px] rounded-2xl" />
            <Skeleton className="h-[460px] rounded-2xl" />
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <SignalColumn title="Buy Signale" tone="buy" rows={buySignals} onCardClick={(symbol) => router.push(`/asset/${symbol}`)} />
            <SignalColumn title="Sell Signale" tone="sell" rows={sellSignals} onCardClick={(symbol) => router.push(`/asset/${symbol}`)} />
          </div>
        )}
      </section>

      <section className="trading-surface border p-4">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-100">
              <History className="h-4 w-4 text-emerald-300" />
              Historie & Bewertung
            </h2>
            <p className="text-sm text-slate-400">
              Rueckschau auf vergangene Signale. Der Bewertungshorizont steuert nur, wann ein Signal im Nachhinein gemessen wird.
            </p>
          </div>
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Bewertungshorizont</span>
            <select
              value={evaluationHorizon}
              onChange={(event) => setEvaluationHorizon(event.target.value as Horizon)}
              className="h-9 min-w-[160px] rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="24h">24h</option>
              <option value="72h">72h</option>
              <option value="7d">7d</option>
            </select>
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
          {isScorecardLoading ? (
            <>
              <Skeleton className="h-28 rounded-2xl" />
              <Skeleton className="h-28 rounded-2xl" />
              <Skeleton className="h-28 rounded-2xl" />
              <Skeleton className="h-28 rounded-2xl" />
            </>
          ) : (
            <>
              <MetricCard
                title="Trefferquote"
                value={`${scorecard?.hit_rate_pct.toFixed(1) ?? "0.0"}%`}
                subtitle={`${scorecard?.evaluated_signals ?? 0} bewertete Signale`}
                tone="emerald"
              />
              <MetricCard
                title="Durchschnittlicher Ertrag"
                value={`${scorecard?.avg_strategy_return_pct.toFixed(2) ?? "0.00"}%`}
                subtitle={`Rueckschau ${evaluationHorizon}`}
                tone="blue"
              />
              <MetricCard
                title="Positiver Anteil"
                value={`${scorecard?.positive_return_share_pct.toFixed(1) ?? "0.0"}%`}
                subtitle="Strategie-Return > 0"
                tone="amber"
              />
              <MetricCard
                title="Top Symbol"
                value={scorecard?.top_symbols[0]?.symbol ?? "--"}
                subtitle={scorecard?.top_symbols[0] ? `${scorecard.top_symbols[0].avg_strategy_return_pct.toFixed(2)}% im Schnitt` : "Noch keine Historie"}
                tone="violet"
              />
            </>
          )}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,1fr)]">
          <section className="rounded-2xl border border-border/60 bg-slate-900/20 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-100">Signal-Journal</h3>
              <Badge className="border-0 bg-slate-700/30 text-slate-200">{evaluationHorizon}</Badge>
            </div>
            {isJournalLoading ? (
              <Skeleton className="h-72 rounded-2xl" />
            ) : journal && journal.length > 0 ? (
              <div className="space-y-3">
                {journal.slice(0, 8).map((row) => (
                  <button
                    key={row.signal_id}
                    type="button"
                    onClick={() => router.push(`/asset/${row.symbol}`)}
                    className="w-full rounded-xl border border-border/60 bg-slate-950/20 p-3 text-left transition hover:bg-slate-900/40"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-slate-100">{row.symbol}</span>
                          <Badge className={cn("border-0 uppercase", signalToneClasses(row.signal_type))}>{row.signal_type}</Badge>
                          <Badge className="border-0 bg-slate-700/30 text-slate-200">{row.strategy_label}</Badge>
                        </div>
                        <p className="text-xs text-slate-500">
                          Score {formatSignedScore(row.composite_score)} | Signalstaerke {row.strength.toFixed(1)} |{" "}
                          {formatDateTime(row.created_at)}
                        </p>
                        <p className="line-clamp-2 text-sm text-slate-300">{row.reasoning}</p>
                      </div>
                      <div className="grid min-w-[220px] grid-cols-2 gap-2 text-xs text-slate-400">
                        <MiniMetric label="Einstieg" value={formatCurrency(row.price_at_signal)} />
                        <MiniMetric
                          label="Bewertet"
                          value={row.evaluation_price === null ? "--" : formatCurrency(row.evaluation_price)}
                        />
                        <MiniMetric label="Roh-Return" value={formatSignedPercent(row.raw_return_pct)} />
                        <MiniMetric label="Strategie-Return" value={formatSignedPercent(row.strategy_return_pct)} />
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState message="Noch keine Signal-Historie verfuegbar." />
            )}
          </section>

          <section className="rounded-2xl border border-border/60 bg-slate-900/20 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-100">Scorecard</h3>
              <Badge className="border-0 bg-slate-700/30 text-slate-200">{evaluationHorizon}</Badge>
            </div>
            {isScorecardLoading ? (
              <Skeleton className="h-72 rounded-2xl" />
            ) : scorecard ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <MiniMetric label="Buy Signale" value={String(scorecard.buy_signals)} />
                  <MiniMetric label="Sell Signale" value={String(scorecard.sell_signals)} />
                  <MiniMetric
                    label="Buy Return"
                    value={scorecard.avg_buy_return_pct === null ? "--" : `${scorecard.avg_buy_return_pct.toFixed(2)}%`}
                  />
                  <MiniMetric
                    label="Sell Return"
                    value={scorecard.avg_sell_return_pct === null ? "--" : `${scorecard.avg_sell_return_pct.toFixed(2)}%`}
                  />
                </div>
                <div className="grid grid-cols-1 gap-3">
                  <SymbolStatsList title="Bisher stark" rows={scorecard.top_symbols} tone="good" />
                  <SymbolStatsList title="Schwaecher" rows={scorecard.weak_symbols} tone="weak" />
                </div>
              </div>
            ) : (
              <EmptyState message="Noch keine bewerteten Signale verfuegbar." />
            )}
          </section>
        </div>
      </section>

      <section className="trading-surface border p-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-100">
              <ShieldCheck className="h-4 w-4 text-emerald-300" />
              Signal-zu-Paper-Trade
            </h2>
            <p className="text-sm text-slate-400">
              Hier siehst du, welche Signale bereits in einen Paper-Trade oder eine Pending-Order ueberfuehrt wurden.
            </p>
          </div>
          <Badge className="border-0 bg-slate-700/30 text-slate-200">{paperJournalRows.length} verknuepft</Badge>
        </div>

        {isJournalLoading ? (
          <Skeleton className="h-48 rounded-2xl" />
        ) : paperJournalRows.length > 0 ? (
          <div className="space-y-3">
            {paperJournalRows.slice(0, 6).map((row) => (
              <div key={`trade-${row.signal_id}`} className="rounded-xl border border-border/60 bg-slate-900/20 p-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-100">{row.symbol}</span>
                      <Badge className={cn("border-0 uppercase", signalToneClasses(row.signal_type))}>{row.signal_type}</Badge>
                      <Badge className="border-0 bg-slate-700/30 text-slate-200">{row.strategy_label}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">Signal vom {formatDateTime(row.created_at)}</p>
                    <p className="mt-2 text-sm text-slate-300">
                      Trade #{row.linked_trade?.trade_id} | {row.linked_trade?.status} | {row.linked_trade?.is_paper ? "paper" : "live"}
                    </p>
                    {row.linked_trade?.notes && <p className="mt-1 text-xs text-slate-500">{row.linked_trade.notes}</p>}
                  </div>
                  <div className="grid min-w-[220px] grid-cols-2 gap-2 text-xs text-slate-400">
                    <MiniMetric label="Trade-Wert" value={formatCurrency(row.linked_trade?.total_value ?? null)} />
                    <MiniMetric label="Menge" value={row.linked_trade ? row.linked_trade.quantity.toFixed(4) : "--"} />
                    <MiniMetric label="Trade erstellt" value={formatDateTime(row.linked_trade?.created_at ?? null)} />
                    <MiniMetric label="Gefuellt" value={formatDateTime(row.linked_trade?.filled_at ?? null)} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState message="Noch keine Signal-zu-Trade-Verknuepfung vorhanden." />
        )}
      </section>

      <section className="trading-surface border p-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-100">
              <Workflow className="h-4 w-4 text-violet-300" />
              Strategien
            </h2>
            <p className="text-sm text-slate-400">
              Die bestehende Composite-Engine ist das erste aktive Preset. Weitere Presets und spaeter eigene Strategien koennen hier andocken.
            </p>
          </div>
        </div>
        {isStrategiesLoading ? (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
            <Skeleton className="h-40 rounded-2xl" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {(strategies ?? []).map((strategy) => (
              <StrategyCard key={strategy.strategy_id} strategy={strategy} />
            ))}
          </div>
        )}
      </section>

      <section className="trading-surface border p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-100">Discovery bleibt separat</h2>
            <p className="text-sm text-slate-400">
              Discovery nutzt Signale, Scorecard und Markt-Kontext als Input, ist aber bewusst nicht Teil der Signal-Seite.
            </p>
          </div>
          <Link
            href="/discovery"
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-border/70 bg-[#12121e] px-4 text-sm text-slate-100 transition hover:bg-[#191a2e]"
          >
            Zum Discovery Lab
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </section>
  );
}

function InfoCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-slate-900/20 p-4">
      <p className="text-sm font-semibold text-slate-100">{title}</p>
      <p className="mt-2 text-sm text-slate-400">{description}</p>
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  tone = "slate",
}: {
  title: string;
  value: string;
  subtitle: string;
  tone?: "slate" | "emerald" | "red" | "blue" | "amber" | "violet";
}) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : tone === "red"
        ? "border-red-500/30 bg-red-500/5"
        : tone === "blue"
          ? "border-blue-500/30 bg-blue-500/5"
          : tone === "amber"
            ? "border-amber-500/30 bg-amber-500/5"
            : tone === "violet"
              ? "border-violet-500/30 bg-violet-500/5"
              : "border-border/60 bg-slate-900/20";
  return (
    <div className={cn("rounded-2xl border p-4", toneClass)}>
      <p className="text-xs uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-100">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
    </div>
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
        <h3 className={cn("text-base font-semibold", headerClass)}>{title}</h3>
        <span className="font-mono text-sm text-slate-200">{rows.length}</span>
      </div>

      <div className="trading-scrollbar max-h-[560px] space-y-2 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <EmptyState message="Keine aktuellen Signale fuer diesen Filter." />
        ) : (
          rows.map((signal) => (
            <button
              key={`${signal.symbol}-${signal.created_at}`}
              type="button"
              onClick={() => onCardClick(signal.symbol)}
              className="trading-hover-glow w-full rounded-xl border border-border/50 bg-slate-900/25 p-3 text-left"
            >
              <div className="mb-2 flex items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-slate-100">{signal.symbol}</p>
                    <Badge className={cn("border-0 uppercase", signalToneClasses(signal.signal_type))}>{signal.signal_type}</Badge>
                    <Badge className="border-0 bg-slate-700/30 text-slate-200">{signal.strategy_label}</Badge>
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

              <div className="mb-2 grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                <MiniMetric label="Score" value={formatSignedScore(signal.composite_score)} />
                <MiniMetric label="Signalstaerke" value={signal.strength.toFixed(1)} />
              </div>

              <p className="line-clamp-3 text-sm text-slate-300">{signal.reasoning}</p>

              <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                <span className="font-mono">{formatCurrency(parseNumeric(signal.price_at_signal))}</span>
                <span>{formatDateTime(signal.created_at)}</span>
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

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/60 bg-slate-900/20 p-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-slate-200">{value}</p>
    </div>
  );
}

function SymbolStatsList({
  title,
  rows,
  tone,
}: {
  title: string;
  rows: SignalScorecardResponse["top_symbols"];
  tone: "good" | "weak";
}) {
  return (
    <div className="rounded-xl border border-border/60 bg-slate-900/20 p-3">
      <p className="mb-2 text-sm font-medium text-slate-200">{title}</p>
      <div className="space-y-2">
        {rows.length === 0 ? (
          <p className="text-xs text-slate-500">Noch keine Daten.</p>
        ) : (
          rows.map((row) => (
            <div key={row.symbol} className="flex items-center justify-between text-xs">
              <div>
                <p className="font-medium text-slate-100">{row.symbol}</p>
                <p className="text-slate-500">{row.evaluated_signals} Signale</p>
              </div>
              <div className="text-right">
                <p className={cn("font-mono", tone === "good" ? "text-emerald-300" : "text-red-300")}>
                  {row.avg_strategy_return_pct.toFixed(2)}%
                </p>
                <p className="text-slate-500">{row.hit_rate_pct.toFixed(1)}% Treffer</p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function StrategyCard({ strategy }: { strategy: SignalStrategyResponse }) {
  const toneClass =
    strategy.status === "active"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : "border-slate-600/50 bg-slate-900/20";
  return (
    <div className={cn("rounded-2xl border p-4", toneClass)}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-base font-semibold text-slate-100">{strategy.label}</p>
          <p className="mt-1 text-xs text-slate-500">
            {strategy.kind === "custom" ? "Custom" : "Preset"} {strategy.timeframe ? `| ${strategy.timeframe}` : ""}
          </p>
        </div>
        <Badge className={cn("border-0", strategy.status === "active" ? "bg-emerald-500/15 text-emerald-200" : "bg-slate-500/15 text-slate-200")}>
          {strategy.status === "active" ? "aktiv" : "geplant"}
        </Badge>
      </div>
      <p className="mt-3 text-sm text-slate-400">{strategy.description}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <Badge className="border-0 bg-slate-700/30 text-slate-200">{strategy.supports_paper_trade ? "Paper-Trade faehig" : "Nur Signal"}</Badge>
        <Badge className="border-0 bg-slate-700/30 text-slate-200">{strategy.is_editable ? "spaeter editierbar" : "festes Preset"}</Badge>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl bg-slate-800/30 p-4 text-sm text-slate-400">
      <Inbox className="h-5 w-5 text-slate-500" />
      {message}
    </div>
  );
}
