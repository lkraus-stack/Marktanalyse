"use client";

import { useMemo, useState } from "react";
import { Filter, Inbox, Radar, ShieldCheck, SignalHigh } from "lucide-react";
import { useRouter } from "next/navigation";
import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson, formatCurrency, parseNumeric } from "@/lib/api";
import type {
  AssetResponse,
  DiscoveryCandidateResponse,
  SignalResponse,
  SignalScorecardResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { signalToneClasses } from "@/src/components/ui/theme";

type SortMode = "strength" | "newest" | "assetType";
type AssetFilter = "all" | "stock" | "crypto";
type RiskProfile = "low" | "balanced" | "high";
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

export default function SignalsPage() {
  const router = useRouter();
  const [sortMode, setSortMode] = useState<SortMode>("strength");
  const [assetFilter, setAssetFilter] = useState<AssetFilter>("all");
  const [minStrength, setMinStrength] = useState(40);
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [horizon, setHorizon] = useState<Horizon>("72h");

  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, {
    refreshInterval: 120000,
    revalidateOnFocus: true,
  });
  const { data: signals, isLoading } = useSWR<SignalResponse[]>("/api/signals?limit=200", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: scorecard, isLoading: isScorecardLoading } = useSWR<SignalScorecardResponse>(
    `/api/signals/scorecard?horizon=${horizon}&asset_type=${assetFilter}&limit=300`,
    fetchJson,
    {
      refreshInterval: 60000,
      revalidateOnFocus: true,
    }
  );
  const { data: riskCandidates, isLoading: isCandidatesLoading } = useSWR<DiscoveryCandidateResponse[]>(
    `/api/discovery/candidates?risk_profile=${riskProfile}&direction=all&asset_type=${assetFilter}&horizon=${horizon}&limit=10`,
    fetchJson,
    {
      refreshInterval: 45000,
      revalidateOnFocus: true,
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
            <p className="text-sm text-slate-400">
              Buy/Sell Signale mit Score-Aufschluesselung, Testbot-Rueckblick und risikoorientierten Kandidatenlisten.
            </p>
          </div>
          <SignalHigh className="h-5 w-5 text-blue-300" />
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
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
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Testbot-Horizont</span>
            <select
              value={horizon}
              onChange={(event) => setHorizon(event.target.value as Horizon)}
              className="h-9 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="24h">24h</option>
              <option value="72h">72h</option>
              <option value="7d">7d</option>
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span className="text-slate-500">Risikoprofil</span>
            <select
              value={riskProfile}
              onChange={(event) => setRiskProfile(event.target.value as RiskProfile)}
              className="h-9 w-full rounded-lg border border-border/70 bg-[#0d0f1c] px-3 text-sm text-slate-100 outline-none"
            >
              <option value="low">Defensiv</option>
              <option value="balanced">Ausgewogen</option>
              <option value="high">Chancenreich</option>
            </select>
          </label>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-4">
        {isScorecardLoading ? (
          <>
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
            <Skeleton className="h-28 rounded-2xl" />
          </>
        ) : (
          <>
            <ScoreMetricCard
              title="Trefferquote"
              value={`${scorecard?.hit_rate_pct.toFixed(1) ?? "0.0"}%`}
              subtitle={`${scorecard?.evaluated_signals ?? 0} bewertete Signale`}
              tone="emerald"
            />
            <ScoreMetricCard
              title="Durchschnitt Ertrag"
              value={`${scorecard?.avg_strategy_return_pct.toFixed(2) ?? "0.00"}%`}
              subtitle={`Horizont ${horizon}`}
              tone="blue"
            />
            <ScoreMetricCard
              title="Positiver Anteil"
              value={`${scorecard?.positive_return_share_pct.toFixed(1) ?? "0.0"}%`}
              subtitle="Strategie-Return > 0"
              tone="amber"
            />
            <ScoreMetricCard
              title="Top Symbol"
              value={scorecard?.top_symbols[0]?.symbol ?? "--"}
              subtitle={
                scorecard?.top_symbols[0]
                  ? `${scorecard.top_symbols[0].avg_strategy_return_pct.toFixed(2)}% durchschnittlich`
                  : "Noch keine Historie"
              }
              tone="violet"
            />
          </>
        )}
      </section>

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

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="trading-surface border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-100">
              <ShieldCheck className="h-4 w-4 text-emerald-300" />
              Testbot-Scorecard
            </h2>
            <Badge className="border-0 bg-slate-700/30 text-slate-200">{horizon}</Badge>
          </div>
          {isScorecardLoading ? (
            <Skeleton className="h-60 rounded-2xl" />
          ) : scorecard ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                <ScoreSmallMetric label="Buy Signale" value={String(scorecard.buy_signals)} />
                <ScoreSmallMetric label="Sell Signale" value={String(scorecard.sell_signals)} />
                <ScoreSmallMetric
                  label="Buy Return"
                  value={scorecard.avg_buy_return_pct === null ? "--" : `${scorecard.avg_buy_return_pct.toFixed(2)}%`}
                />
                <ScoreSmallMetric
                  label="Sell Return"
                  value={scorecard.avg_sell_return_pct === null ? "--" : `${scorecard.avg_sell_return_pct.toFixed(2)}%`}
                />
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <SymbolStatsList title="Bisher stark" rows={scorecard.top_symbols} tone="good" />
                <SymbolStatsList title="Schwaecher" rows={scorecard.weak_symbols} tone="weak" />
              </div>
              <div>
                <p className="mb-2 text-sm font-medium text-slate-200">Letzte bewertete Signale</p>
                <div className="space-y-2">
                  {scorecard.recent.slice(0, 5).map((row) => (
                    <button
                      key={row.signal_id}
                      type="button"
                      onClick={() => router.push(`/asset/${row.symbol}`)}
                      className="w-full rounded-xl border border-border/60 bg-slate-900/25 p-3 text-left transition hover:bg-slate-900/40"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-100">{row.symbol}</p>
                          <p className="text-xs text-slate-500">{new Date(row.created_at).toLocaleString("de-DE")}</p>
                        </div>
                        <div className="text-right">
                          <p className={cn("font-mono text-sm", row.strategy_return_pct >= 0 ? "text-emerald-300" : "text-red-300")}>
                            {row.strategy_return_pct.toFixed(2)}%
                          </p>
                          <p className="text-xs text-slate-500">{row.signal_type}</p>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : null}
        </section>

        <section className="trading-surface border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-base font-semibold text-slate-100">
              <Radar className="h-4 w-4 text-blue-300" />
              Risiko-Fokus
            </h2>
            <Badge className="border-0 bg-slate-700/30 text-slate-200">{riskProfile}</Badge>
          </div>
          {isCandidatesLoading ? (
            <Skeleton className="h-60 rounded-2xl" />
          ) : riskCandidates && riskCandidates.length > 0 ? (
            <div className="space-y-2">
              {riskCandidates.map((candidate) => (
                <button
                  key={`${candidate.symbol}-${candidate.created_at}`}
                  type="button"
                  onClick={() => router.push(`/asset/${candidate.symbol}`)}
                  className="w-full rounded-xl border border-border/60 bg-slate-900/25 p-3 text-left transition hover:bg-slate-900/40"
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-slate-100">{candidate.symbol}</p>
                        <Badge className={cn("border-0 uppercase", signalToneClasses(candidate.signal_type))}>
                          {candidate.signal_type}
                        </Badge>
                        <RiskBucketBadge bucket={candidate.risk_bucket} />
                      </div>
                      <p className="text-xs text-slate-500">{candidate.name}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm text-slate-100">{candidate.discovery_score.toFixed(1)}</p>
                      <p className="text-[11px] text-slate-500">Discovery</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                    <ScoreSmallMetric label="Staerke" value={candidate.strength.toFixed(1)} compact />
                    <ScoreSmallMetric
                      label="Trefferquote"
                      value={candidate.historical_hit_rate_pct === null ? "--" : `${candidate.historical_hit_rate_pct.toFixed(1)}%`}
                      compact
                    />
                    <ScoreSmallMetric
                      label="Signal-Ertrag"
                      value={
                        candidate.historical_avg_return_pct === null ? "--" : `${candidate.historical_avg_return_pct.toFixed(2)}%`
                      }
                      compact
                    />
                    <ScoreSmallMetric
                      label="Volatilitaet"
                      value={candidate.volatility_pct === null ? "--" : `${candidate.volatility_pct.toFixed(2)}%`}
                      compact
                    />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 rounded-xl bg-slate-800/30 p-4 text-sm text-slate-400">
              <Inbox className="h-5 w-5 text-slate-500" />
              Noch keine risikoorientierten Kandidaten verfuegbar.
            </div>
          )}
        </section>
      </div>
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

function ScoreMetricCard({
  title,
  value,
  subtitle,
  tone,
}: {
  title: string;
  value: string;
  subtitle: string;
  tone: "emerald" | "blue" | "amber" | "violet";
}) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/5"
      : tone === "blue"
        ? "border-blue-500/30 bg-blue-500/5"
        : tone === "amber"
          ? "border-amber-500/30 bg-amber-500/5"
          : "border-violet-500/30 bg-violet-500/5";

  return (
    <div className={cn("rounded-2xl border p-4", toneClass)}>
      <p className="text-xs uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-100">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{subtitle}</p>
    </div>
  );
}

function ScoreSmallMetric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("rounded-xl border border-border/60 bg-slate-900/20 p-2", compact && "py-1.5")}>
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

function RiskBucketBadge({ bucket }: { bucket: DiscoveryCandidateResponse["risk_bucket"] }) {
  if (bucket === "low") {
    return <Badge className="border-0 bg-emerald-500/15 text-emerald-200">low risk</Badge>;
  }
  if (bucket === "high") {
    return <Badge className="border-0 bg-red-500/15 text-red-200">high risk</Badge>;
  }
  return <Badge className="border-0 bg-amber-500/15 text-amber-200">mid risk</Badge>;
}
