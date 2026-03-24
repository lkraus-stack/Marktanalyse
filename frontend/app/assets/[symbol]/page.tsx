"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import {
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  Cell,
} from "recharts";

import { PriceChart } from "@/components/PriceChart";
import { Badge } from "@/components/ui/badge";
import { ProgressRing } from "@/components/ui/progress-ring";
import { fetchJson, formatCurrency, formatPercent, parseNumeric } from "@/lib/api";
import type {
  AssetResponse,
  PricePointResponse,
  SentimentSnapshotResponse,
  SignalResponse,
  SocialFeedItemResponse,
  SocialStatsResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { sentimentToneClasses, signalToneClasses } from "@/src/components/ui/theme";

type FeedFilter = "all" | "reddit" | "stocktwits" | "news" | "twitter";

const DONUT_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444"];

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizeSignalComponent(value: number): number {
  if (Math.abs(value) <= 1) {
    return clamp((value + 1) * 50, 0, 100);
  }
  return clamp(value, 0, 100);
}

function signalState(
  value: number,
  thresholds: { green: number; red: number }
): { tone: "green" | "amber" | "red"; label: string } {
  if (value >= thresholds.green) {
    return { tone: "green", label: "Bullish" };
  }
  if (value <= thresholds.red) {
    return { tone: "red", label: "Bearish" };
  }
  return { tone: "amber", label: "Neutral" };
}

function toneClass(tone: "green" | "amber" | "red"): string {
  if (tone === "green") {
    return "text-emerald-300 bg-emerald-500/15";
  }
  if (tone === "red") {
    return "text-red-300 bg-red-500/15";
  }
  return "text-amber-300 bg-amber-500/15";
}

export default function AssetDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = (params?.symbol ?? "").toUpperCase();
  const [feedFilter, setFeedFilter] = useState<FeedFilter>("all");

  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, { refreshInterval: 120000 });
  const { data: latestPrice, error: latestPriceError } = useSWR<PricePointResponse>(
    symbol ? `/api/prices/${symbol}` : null,
    fetchJson,
    {
      refreshInterval: 60000,
      shouldRetryOnError: false,
    }
  );
  const { data: priceHistory, isLoading: isPriceLoading } = useSWR<PricePointResponse[]>(
    symbol ? `/api/prices/${symbol}/history?timeframe=1m&limit=1000` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: dayHistory } = useSWR<PricePointResponse[]>(
    symbol ? `/api/prices/${symbol}/history?timeframe=1d&limit=2` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: sentimentSnapshot } = useSWR<SentimentSnapshotResponse>(
    symbol ? `/api/sentiment/${symbol}` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: socialStats } = useSWR<SocialStatsResponse>(symbol ? `/api/social/${symbol}/stats` : null, fetchJson, {
    refreshInterval: 60000,
  });
  const { data: socialFeed } = useSWR<SocialFeedItemResponse[]>(
    symbol ? `/api/social/${symbol}/feed?limit=40` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: signal } = useSWR<SignalResponse>(symbol ? `/api/signals/${symbol}` : null, fetchJson, {
    refreshInterval: 45000,
    shouldRetryOnError: false,
  });

  const assetMeta = useMemo(() => assets?.find((item) => item.symbol === symbol), [assets, symbol]);
  const isUnknownAsset = Boolean(symbol) && assets !== undefined && !assetMeta;
  const hasNoPriceData = Boolean(assetMeta) && !isPriceLoading && (!priceHistory || priceHistory.length === 0);

  const price = parseNumeric(latestPrice?.close ?? null);
  const change24h = useMemo(() => {
    if (!dayHistory || dayHistory.length < 2) {
      return null;
    }
    const first = parseNumeric(dayHistory[0]?.close);
    const last = parseNumeric(dayHistory[dayHistory.length - 1]?.close);
    if (first === null || last === null || first === 0) {
      return null;
    }
    return ((last - first) / first) * 100;
  }, [dayHistory]);

  const donutData = useMemo(() => {
    if (!socialStats) {
      return [];
    }
    const sourceEntries = Object.entries(socialStats.by_source ?? {});
    const total = sourceEntries.reduce((sum, [, value]) => sum + value, 0);
    if (total <= 0) {
      return [];
    }
    return sourceEntries.map(([name, value]) => ({
      name,
      value,
      pct: (value / total) * 100,
    }));
  }, [socialStats]);

  const feedRows = useMemo(() => {
    const rows = socialFeed ?? [];
    if (feedFilter === "all") {
      return rows;
    }
    return rows.filter((item) => item.source === feedFilter);
  }, [feedFilter, socialFeed]);

  const rsi = useMemo(() => {
    const source = signal?.momentum_component ?? 0;
    return clamp(50 + source * 35, 0, 100);
  }, [signal?.momentum_component]);
  const macd = useMemo(() => {
    const source = signal?.technical_component ?? 0;
    return source * 2;
  }, [signal?.technical_component]);
  const bollinger = useMemo(() => {
    const source = signal?.volume_component ?? 0;
    return clamp(50 + source * 40, 0, 100);
  }, [signal?.volume_component]);

  const rsiState = signalState(rsi, { green: 60, red: 40 });
  const macdState = signalState(macd, { green: 0.25, red: -0.25 });
  const bollingerState = signalState(bollinger, { green: 58, red: 42 });

  const signalComponents = [
    { label: "Sentiment", value: normalizeSignalComponent(signal?.sentiment_component ?? 0) },
    { label: "Technik", value: normalizeSignalComponent(signal?.technical_component ?? 0) },
    { label: "Volumen", value: normalizeSignalComponent(signal?.volume_component ?? 0) },
    { label: "Momentum", value: normalizeSignalComponent(signal?.momentum_component ?? 0) },
  ];

  if (isUnknownAsset) {
    return (
      <section className="space-y-6">
        <div className="trading-surface space-y-4 p-6">
          <div>
            <h1 className="text-2xl font-semibold text-slate-100">{symbol} ist noch nicht im Tracking-Universum</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-400">
              Dieses Asset ist aktuell nicht in der Datenbank vorhanden. Importiere zuerst Standard-Assets oder fuege das
              Symbol ueber das Onboarding hinzu.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/einstellungen"
              className="inline-flex rounded-lg border border-border/70 bg-slate-800/35 px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-700/45"
            >
              Onboarding oeffnen
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex rounded-lg border border-border/70 bg-slate-800/20 px-3 py-2 text-sm text-slate-300 transition hover:bg-slate-700/35"
            >
              Zurueck zum Dashboard
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <header className="trading-surface p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <h1 className="text-3xl font-semibold text-slate-100 md:text-4xl">
                {assetMeta?.name ?? symbol}
              </h1>
              <Badge className="border-slate-600/60 bg-slate-700/30 text-slate-200">{symbol}</Badge>
            </div>
            <p className="text-xs text-slate-500">Live-Detailansicht fuer Preis, Signal und Social-Stimmung.</p>
          </div>

          <div className="text-left md:text-right">
            <p className="font-mono text-4xl font-bold text-slate-100 md:text-5xl">{formatCurrency(price)}</p>
            <p className={cn("mt-1 text-sm", (change24h ?? 0) >= 0 ? "text-emerald-300" : "text-red-300")}>
              24h {formatPercent(change24h)}
            </p>
          </div>
        </div>

        <div className="mt-4">
          <Link
            href="/dashboard"
            className="inline-flex rounded-lg border border-border/70 bg-slate-800/35 px-3 py-2 text-xs text-slate-300 transition hover:bg-slate-700/45"
          >
            Zurueck zum Dashboard
          </Link>
        </div>
      </header>

      {(hasNoPriceData || latestPriceError) && (
        <section className="trading-surface border-amber-500/35 bg-amber-500/10 p-4 text-sm text-amber-100">
          <p className="font-medium">Fuer {symbol} sind noch keine vollstaendigen Kursdaten vorhanden.</p>
          <p className="mt-1 text-amber-100/85">
            Starte zuerst den Pipeline-Bootstrap oder pruefe Scheduler, Marktdaten-Keys und Asset-Onboarding.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              href="/einstellungen"
              className="inline-flex rounded-lg border border-amber-400/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100 transition hover:bg-amber-500/20"
            >
              Onboarding oeffnen
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex rounded-lg border border-amber-400/20 bg-black/10 px-3 py-2 text-xs text-amber-100 transition hover:bg-black/20"
            >
              Zurueck zum Dashboard
            </Link>
          </div>
        </section>
      )}

      <section className="overflow-hidden rounded-2xl bg-[#0a0a14] ring-1 ring-[#1e1e3a]">
        <PriceChart
          data={priceHistory}
          isLoading={isPriceLoading}
          heightClassName="h-[70vh] min-h-[420px]"
          className="rounded-none"
        />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <article className="trading-surface p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-100">Technische Indikatoren</h3>
          <div className="space-y-2">
            <IndicatorCard
              label="RSI"
              value={rsi.toFixed(1)}
              subtitle={rsiState.label}
              tone={rsiState.tone}
            />
            <IndicatorCard
              label="MACD"
              value={macd.toFixed(2)}
              subtitle={macdState.label}
              tone={macdState.tone}
            />
            <IndicatorCard
              label="Bollinger"
              value={bollinger.toFixed(1)}
              subtitle={bollingerState.label}
              tone={bollingerState.tone}
            />
          </div>
        </article>

        <article className="trading-surface p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-100">Sentiment-Detail</h3>
          <p className="text-sm text-slate-400">
            Score <span className={cn("font-mono", sentimentToneClasses(sentimentSnapshot?.score ?? 0))}>{(sentimentSnapshot?.score ?? 0).toFixed(2)}</span>
          </p>
          <div className="mt-3 h-44">
            {donutData.length === 0 ? (
              <div className="flex h-full items-center justify-center rounded-xl bg-slate-800/30 text-sm text-slate-500">
                Keine Source-Daten vorhanden.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={donutData} dataKey="value" nameKey="name" innerRadius={42} outerRadius={68} paddingAngle={2}>
                    {donutData.map((entry, index) => (
                      <Cell key={entry.name} fill={DONUT_COLORS[index % DONUT_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{ background: "#12121e", border: "1px solid #1e1e3a", borderRadius: "10px" }}
                    formatter={(value) => [`${value ?? 0}`, "Erwaehnungen"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
          <div className="mt-2 space-y-1">
            {donutData.map((row, index) => (
              <div key={row.name} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2 text-slate-300">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: DONUT_COLORS[index % DONUT_COLORS.length] }} />
                  <span className="uppercase">{row.name}</span>
                </div>
                <span className="font-mono text-slate-400">{row.pct.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </article>

        <article className="trading-surface p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-100">Signal-Detail</h3>
          {!signal ? (
            <div className="flex min-h-44 items-center justify-center rounded-xl bg-slate-800/30 text-sm text-slate-400">
              Noch keine Signale - Daten werden gesammelt.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Badge className={cn("border-0 uppercase", signalToneClasses(signal.signal_type))}>
                  {signal.signal_type}
                </Badge>
                <ProgressRing
                  value={signal.composite_score}
                  size={76}
                  strokeWidth={7}
                  progressClassName={
                    signal.signal_type === "buy"
                      ? "text-emerald-400"
                      : signal.signal_type === "sell"
                        ? "text-red-400"
                        : "text-blue-400"
                  }
                />
              </div>
              <div className="space-y-2">
                {signalComponents.map((component) => (
                  <div key={component.label}>
                    <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
                      <span>{component.label}</span>
                      <span className="font-mono">{component.value.toFixed(0)}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-blue-500 to-emerald-400"
                        style={{ width: `${component.value}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </article>
      </section>

      <section className="trading-surface p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Social Feed</h3>
          <div className="flex flex-wrap gap-1">
            {(["all", "reddit", "stocktwits", "news", "twitter"] as FeedFilter[]).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setFeedFilter(filter)}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-xs uppercase transition-colors",
                  feedFilter === filter
                    ? "bg-blue-500/25 text-blue-200"
                    : "bg-slate-700/30 text-slate-400 hover:bg-slate-700/45"
                )}
              >
                {filter}
              </button>
            ))}
          </div>
        </div>

        <div className="trading-scrollbar max-h-[320px] space-y-2 overflow-y-auto pr-1">
          {feedRows.length === 0 ? (
            <div className="rounded-xl bg-slate-800/30 p-4 text-sm text-slate-400">
              Noch keine Posts fuer diesen Filter vorhanden.
            </div>
          ) : (
            feedRows.map((item) => (
              <article key={item.id} className="rounded-xl border border-border/50 bg-slate-900/25 p-3">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge className="border-slate-600/60 bg-slate-700/30 text-slate-300 uppercase">
                      {item.source}
                    </Badge>
                    {item.sentiment_score !== null && (
                      <span className={cn("text-xs font-mono", sentimentToneClasses(item.sentiment_score))}>
                        {item.sentiment_score.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {new Date(item.created_at).toLocaleString("de-DE")}
                  </span>
                </div>
                <p className="line-clamp-3 text-sm text-slate-200">{item.text_snippet}</p>
                {item.author && <p className="mt-1 text-xs text-slate-500">von {item.author}</p>}
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

interface IndicatorCardProps {
  label: string;
  value: string;
  subtitle: string;
  tone: "green" | "amber" | "red";
}

function IndicatorCard({ label, value, subtitle, tone }: IndicatorCardProps) {
  return (
    <div className="rounded-xl border border-border/50 bg-slate-900/25 p-3">
      <div className="mb-1 flex items-center justify-between">
        <p className="text-xs uppercase text-slate-500">{label}</p>
        <span className={cn("rounded-full px-2 py-0.5 text-[11px]", toneClass(tone))}>{subtitle}</span>
      </div>
      <p className="font-mono text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}
