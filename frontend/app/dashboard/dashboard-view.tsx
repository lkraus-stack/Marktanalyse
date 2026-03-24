"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import useSWR, { mutate } from "swr";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CircleAlert,
  LineChart,
  Radar,
  Sparkles,
} from "lucide-react";

import { AssetTable } from "@/components/AssetTable";
import { PriceChart } from "@/components/PriceChart";
import { SentimentGauge } from "@/components/SentimentGauge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MiniSparkline } from "@/components/ui/mini-sparkline";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { apiHeaders, fetchJson, formatCurrency, formatPercent, parseNumeric } from "@/lib/api";
import type {
  AlertHistoryResponse,
  AlertResponse,
  AssetResponse,
  AssetTableRow,
  PortfolioSnapshotResponse,
  PricePointResponse,
  SentimentHistoryResponse,
  SentimentOverviewResponse,
  SignalPipelineStatusResponse,
  SignalResponse,
  TradingAccountResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { sentimentToneClasses, signalToneClasses } from "@/src/components/ui/theme";

type ChartRange = "1H" | "4H" | "1D" | "1W";

interface RangeConfig {
  timeframe: "1m" | "5m" | "1h" | "1d";
  limit: number;
}

interface SentimentShiftRow {
  symbol: string;
  score: number;
  shift: number;
}

const RANGE_CONFIG: Record<ChartRange, RangeConfig> = {
  "1H": { timeframe: "1m", limit: 120 },
  "4H": { timeframe: "1m", limit: 480 },
  "1D": { timeframe: "1m", limit: 1000 },
  "1W": { timeframe: "5m", limit: 1000 },
};

function safeScore(value: number | null | undefined): number {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(-1, Math.min(1, value));
}

async function fetchAssetChanges24h(assets: AssetResponse[]): Promise<Record<string, number>> {
  const changes = await Promise.all(
    assets.map(async (asset) => {
      try {
        const rows = await fetchJson<PricePointResponse[]>(
          `/api/prices/${asset.symbol}/history?timeframe=1d&limit=2`
        );
        if (rows.length < 2) {
          return [asset.symbol, 0] as const;
        }
        const first = parseNumeric(rows[0]?.close);
        const last = parseNumeric(rows[rows.length - 1]?.close);
        if (first === null || last === null || first === 0) {
          return [asset.symbol, 0] as const;
        }
        return [asset.symbol, ((last - first) / first) * 100] as const;
      } catch {
        return [asset.symbol, 0] as const;
      }
    })
  );
  return Object.fromEntries(changes);
}

async function fetchMiniSparklineMap(symbols: string[]): Promise<Record<string, number[]>> {
  const rows = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const points = await fetchJson<PricePointResponse[]>(
          `/api/prices/${symbol}/history?timeframe=1h&limit=24`
        );
        const values = points
          .map((point) => parseNumeric(point.close))
          .filter((value): value is number => value !== null);
        return [symbol, values] as const;
      } catch {
        return [symbol, []] as const;
      }
    })
  );
  return Object.fromEntries(rows);
}

async function fetchSentimentShifts(symbols: string[]): Promise<SentimentShiftRow[]> {
  const rows = await Promise.all(
    symbols.map(async (symbol) => {
      try {
        const history = await fetchJson<SentimentHistoryResponse[]>(
          `/api/sentiment/${symbol}/history?timeframe=1h&limit=5`
        );
        if (history.length < 2) {
          return { symbol, score: 0, shift: 0 };
        }
        const first = history[0]?.score ?? 0;
        const last = history[history.length - 1]?.score ?? 0;
        return { symbol, score: last, shift: last - first };
      } catch {
        return { symbol, score: 0, shift: 0 };
      }
    })
  );

  return rows.sort((left, right) => Math.abs(right.shift) - Math.abs(left.shift));
}

function useValueFlash(value: number | null | undefined): string {
  const previousRef = useRef<number | null>(null);
  const [flashClass, setFlashClass] = useState("");

  useEffect(() => {
    if (value === null || value === undefined) {
      return;
    }
    const previous = previousRef.current;
    if (previous !== null && previous !== value) {
      setFlashClass(value > previous ? "flash-up" : "flash-down");
      const timeout = window.setTimeout(() => setFlashClass(""), 500);
      previousRef.current = value;
      return () => window.clearTimeout(timeout);
    }
    previousRef.current = value;
  }, [value]);

  return flashClass;
}

function DashboardSkeletonRow() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 4 }).map((_, index) => (
        <Skeleton key={index} className="h-[120px] w-full rounded-2xl" />
      ))}
    </div>
  );
}

export default function DashboardView() {
  const router = useRouter();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [range, setRange] = useState<ChartRange>("1D");
  const [isBootstrapping, setIsBootstrapping] = useState(false);

  const { data: assets, error: assetsError, isLoading: isAssetsLoading } = useSWR<AssetResponse[]>(
    "/api/assets",
    fetchJson,
    { refreshInterval: 60000, revalidateOnFocus: true }
  );
  const { data: sentimentOverview, error: sentimentError, isLoading: isSentimentOverviewLoading } = useSWR<
    SentimentOverviewResponse[]
  >("/api/sentiment/overview", fetchJson, {
    refreshInterval: 60000,
    revalidateOnFocus: true,
  });
  const { data: pipelineStatus, error: pipelineError } = useSWR<SignalPipelineStatusResponse>(
    "/api/signals/pipeline-status",
    fetchJson,
    { refreshInterval: 45000, revalidateOnFocus: true }
  );
  const { data: signals, error: signalsError } = useSWR<SignalResponse[]>("/api/signals?limit=40", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: alerts } = useSWR<AlertResponse[]>("/api/alerts", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: alertHistory } = useSWR<AlertHistoryResponse[]>("/api/alerts/history?limit=20", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: account } = useSWR<TradingAccountResponse>("/api/trading/account", fetchJson, {
    refreshInterval: 45000,
    revalidateOnFocus: true,
  });
  const { data: snapshots } = useSWR<PortfolioSnapshotResponse[]>("/api/trading/portfolio/history?limit=12", fetchJson, {
    refreshInterval: 60000,
    revalidateOnFocus: true,
  });

  useEffect(() => {
    if (!selectedSymbol && assets && assets.length > 0) {
      setSelectedSymbol(assets[0].symbol);
    }
  }, [assets, selectedSymbol]);

  const symbolList = useMemo(() => assets?.map((asset) => asset.symbol) ?? [], [assets]);
  const assetSymbolsKey = useMemo(() => symbolList.join(","), [symbolList]);

  const { data: change24hBySymbol } = useSWR<Record<string, number>>(
    assetSymbolsKey ? `/api/dashboard/changes?symbols=${assetSymbolsKey}` : null,
    () => fetchAssetChanges24h(assets ?? []),
    { refreshInterval: 120000, revalidateOnFocus: false }
  );

  const { data: miniSparklineBySymbol } = useSWR<Record<string, number[]>>(
    assetSymbolsKey ? `/api/dashboard/sparklines?symbols=${assetSymbolsKey}` : null,
    () => fetchMiniSparklineMap(symbolList),
    { refreshInterval: 180000, revalidateOnFocus: false }
  );

  const selectedRange = RANGE_CONFIG[range];
  const historyUrl = selectedSymbol
    ? `/api/prices/${selectedSymbol}/history?timeframe=${selectedRange.timeframe}&limit=${selectedRange.limit}`
    : null;
  const { data: priceHistory, error: priceError, isLoading: isPriceLoading } = useSWR<PricePointResponse[]>(
    historyUrl,
    fetchJson,
    { refreshInterval: 60000, revalidateOnFocus: true }
  );

  const sentimentBySymbol = useMemo(() => {
    const map = new Map<string, SentimentOverviewResponse>();
    (sentimentOverview ?? []).forEach((item) => {
      map.set(item.symbol, item);
    });
    return map;
  }, [sentimentOverview]);

  const marketSentimentScore = useMemo(() => {
    const values = (sentimentOverview ?? [])
      .map((item) => item.score)
      .filter((score): score is number => score !== null && score !== undefined);
    if (values.length === 0) {
      return 0;
    }
    return values.reduce((sum, value) => sum + value, 0) / values.length;
  }, [sentimentOverview]);

  const strongestSignal = signals?.[0] ?? null;
  const topSignals = (signals ?? []).slice(0, 5);
  const activeSignals = pipelineStatus?.active_signals ?? signals?.length ?? 0;
  const openAlerts = alerts?.filter((item) => item.is_enabled).length ?? 0;
  const lastAlertMessage = alertHistory?.[0]?.message ?? "Noch keine Alerts - Daten werden gesammelt";
  const trackedAssetsCount = pipelineStatus?.assets_total ?? assets?.length ?? 0;
  const pricePoints1m = pipelineStatus?.price_points_1m ?? 0;
  const aggregatedSentiment1h = pipelineStatus?.aggregated_1h ?? 0;
  const onboardingState = useMemo(() => {
    if (isAssetsLoading) {
      return null;
    }
    if (trackedAssetsCount === 0) {
      return {
        title: "Noch keine Assets importiert.",
        description:
          "Importiere zuerst Standard-Assets. Danach kann die Pipeline Preise, Sentiment und Signale aufbauen.",
        showBootstrap: false,
      };
    }
    if (pricePoints1m === 0) {
      return {
        title: "Assets vorhanden, aber noch keine Preisdaten.",
        description:
          "Starte den Pipeline-Bootstrap oder aktiviere den Scheduler, damit aktuelle Kursdaten fuer die Webapp gesammelt werden.",
        showBootstrap: true,
      };
    }
    if (aggregatedSentiment1h === 0) {
      return {
        title: "Preisdaten vorhanden, aber Sentiment und Signale fehlen noch.",
        description:
          "Die App hat Assets, aber noch keine verwerteten Sentiment-Aggregationen. Ein Bootstrap-Lauf vervollstaendigt die Datenbasis.",
        showBootstrap: true,
      };
    }
    if (activeSignals === 0) {
      return {
        title: "Datenbasis steht, aber es gibt noch keine aktiven Signale.",
        description:
          "Die Signal-Pipeline ist fast bereit. Nach weiteren Datenpunkten oder einem erneuten Lauf erscheinen Empfehlungen automatisch.",
        showBootstrap: true,
      };
    }
    return null;
  }, [activeSignals, aggregatedSentiment1h, isAssetsLoading, pricePoints1m, trackedAssetsCount]);

  const portfolioSeries = useMemo(() => {
    return (snapshots ?? []).map((item) => item.total_value);
  }, [snapshots]);
  const portfolioValue = useMemo(() => {
    const fallback = snapshots?.[snapshots.length - 1]?.total_value ?? null;
    return account?.equity ?? fallback;
  }, [account?.equity, snapshots]);
  const portfolioChangePct = useMemo(() => {
    if (portfolioSeries.length < 2) {
      return null;
    }
    const first = portfolioSeries[0];
    const last = portfolioSeries[portfolioSeries.length - 1];
    if (!first || first === 0 || !last) {
      return null;
    }
    return ((last - first) / first) * 100;
  }, [portfolioSeries]);

  const sentimentShiftSymbols = useMemo(
    () => (sentimentOverview ?? []).slice(0, 12).map((item) => item.symbol),
    [sentimentOverview]
  );
  const { data: sentimentShifts } = useSWR<SentimentShiftRow[]>(
    sentimentShiftSymbols.length > 0 ? `/api/dashboard/sentiment-shift?symbols=${sentimentShiftSymbols.join(",")}` : null,
    () => fetchSentimentShifts(sentimentShiftSymbols),
    { refreshInterval: 180000, revalidateOnFocus: false }
  );
  const topSentimentShifts = useMemo(() => (sentimentShifts ?? []).slice(0, 5), [sentimentShifts]);

  const strongestSignalAsset = useMemo(() => {
    if (!strongestSignal || !assets) {
      return null;
    }
    return assets.find((item) => item.symbol === strongestSignal.symbol) ?? null;
  }, [assets, strongestSignal]);

  const topMover = useMemo(() => {
    if (!change24hBySymbol) {
      return null;
    }
    return Object.entries(change24hBySymbol).reduce<{ symbol: string; change: number } | null>(
      (current, [symbol, change]) => {
        if (!current || Math.abs(change) > Math.abs(current.change)) {
          return { symbol, change };
        }
        return current;
      },
      null
    );
  }, [change24hBySymbol]);

  const tableRows = useMemo<AssetTableRow[] | undefined>(() => {
    if (!assets) {
      return undefined;
    }
    return assets.map((asset) => {
      const sentiment = sentimentBySymbol.get(asset.symbol);
      const sentimentScore = safeScore(sentiment?.score);
      const signal: AssetTableRow["signal"] =
        sentimentScore > 0.25 ? "buy" : sentimentScore < -0.25 ? "sell" : "hold";

      return {
        symbol: asset.symbol,
        name: asset.name,
        assetType: asset.asset_type,
        exchange: asset.exchange,
        watchStatus: asset.watch_status,
        isToolSuggested: asset.is_tool_suggested,
        price: parseNumeric(asset.latest_close),
        change24h: change24hBySymbol?.[asset.symbol] ?? null,
        sentimentScore,
        mentions: sentiment?.mentions_1h ?? 0,
        signal,
      };
    });
  }, [assets, change24hBySymbol, sentimentBySymbol]);

  const portfolioFlashClass = useValueFlash(portfolioValue);
  const sentimentFlashClass = useValueFlash(marketSentimentScore);
  const activeSignalFlashClass = useValueFlash(activeSignals);

  const bootstrapPipeline = async () => {
    setIsBootstrapping(true);
    try {
      const response = await fetch("/api/signals/bootstrap", { method: "POST", headers: apiHeaders() });
      if (!response.ok) {
        throw new Error("bootstrap failed");
      }
      toast.success("Signal-Pipeline gestartet.");
      await Promise.all([
        mutate("/api/signals/pipeline-status"),
        mutate("/api/signals?limit=40"),
        mutate("/api/assets"),
        mutate("/api/sentiment/overview"),
      ]);
    } catch {
      toast.error("Bootstrap fehlgeschlagen. API-Keys und Logs pruefen.");
    } finally {
      setIsBootstrapping(false);
    }
  };

  return (
    <section className="space-y-5">
      <header className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-100">Trading Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            P&L, Signalstaerke und Marktstimmung in einer Live-Uebersicht.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          <Badge className="border-blue-500/40 bg-blue-500/15 text-blue-200">Range {range}</Badge>
          <Badge className="border-slate-600/60 bg-slate-700/30 text-slate-200">
            {selectedSymbol ? `Chart: ${selectedSymbol}` : "Kein Asset gewaehlt"}
          </Badge>
          {topMover && (
            <Badge className="border-emerald-500/40 bg-emerald-500/15 text-emerald-200">
              Top Mover {topMover.symbol} {formatPercent(topMover.change)}
            </Badge>
          )}
        </div>
      </header>

      {(assetsError || sentimentError || priceError || signalsError) && (
        <div className="trading-surface flex items-start gap-3 border-red-500/35 bg-red-500/10 p-4 text-sm text-red-200">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          Mindestens ein Datenfeed konnte nicht geladen werden. Bitte Backend/API-Status pruefen.
        </div>
      )}
      {pipelineError && (
        <div className="trading-surface flex items-start gap-3 border-red-500/35 bg-red-500/10 p-4 text-sm text-red-200">
          <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" />
          Signal-Pipeline Daten konnten nicht geladen werden.
        </div>
      )}
      {onboardingState && (
        <div className="trading-surface flex flex-col gap-4 border-amber-500/35 bg-amber-500/10 p-4 text-sm text-amber-100 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-3">
            <div>
              <p className="font-semibold text-amber-100">{onboardingState.title}</p>
              <p className="mt-1 max-w-3xl text-amber-100/85">{onboardingState.description}</p>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge className="border-amber-400/35 bg-amber-500/10 text-amber-100">Assets {trackedAssetsCount}</Badge>
              <Badge className="border-amber-400/35 bg-amber-500/10 text-amber-100">1m Preise {pricePoints1m}</Badge>
              <Badge className="border-amber-400/35 bg-amber-500/10 text-amber-100">
                1h Sentiment {aggregatedSentiment1h}
              </Badge>
              <Badge className="border-amber-400/35 bg-amber-500/10 text-amber-100">Signale {activeSignals}</Badge>
            </div>
            {pipelineStatus && pipelineStatus.blockers.length > 0 && (
              <p className="rounded-lg border border-amber-400/20 bg-black/10 p-3 text-xs text-amber-100/90">
                Blocker: {pipelineStatus.blockers.join(" | ")}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => router.push("/einstellungen")}>
              Onboarding oeffnen
            </Button>
            {onboardingState.showBootstrap && (
              <Button
                onClick={bootstrapPipeline}
                disabled={isBootstrapping}
                className="border-amber-400/35 bg-amber-500/20 text-amber-100 hover:bg-amber-500/30"
              >
                {isBootstrapping ? "Starte..." : "Pipeline Bootstrap"}
              </Button>
            )}
          </div>
        </div>
      )}

      {(isAssetsLoading || isSentimentOverviewLoading) && <DashboardSkeletonRow />}

      {!isAssetsLoading && !isSentimentOverviewLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <motion.article
            layout
            className="trading-surface trading-hover-glow relative h-[120px] overflow-hidden p-4"
            transition={{ duration: 0.2 }}
          >
            <div className="pointer-events-none absolute inset-x-2 bottom-2 opacity-55">
              <MiniSparkline
                values={portfolioSeries}
                className="h-12 w-full"
                strokeClassName={
                  portfolioChangePct !== null && portfolioChangePct >= 0
                    ? "text-emerald-400/70"
                    : "text-red-400/70"
                }
                showArea
              />
            </div>
            <div className="relative z-10 space-y-1">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Portfolio-Wert</p>
              <p className={cn("font-mono text-3xl font-bold text-slate-100 md:text-4xl", portfolioFlashClass)}>
                {formatCurrency(portfolioValue)}
              </p>
              <div className="flex items-center gap-1 text-xs">
                {portfolioChangePct !== null && portfolioChangePct >= 0 ? (
                  <ArrowUpRight className="h-3.5 w-3.5 text-emerald-300" />
                ) : (
                  <ArrowDownRight className="h-3.5 w-3.5 text-red-300" />
                )}
                <span
                  className={
                    portfolioChangePct !== null && portfolioChangePct >= 0
                      ? "text-emerald-300"
                      : "text-red-300"
                  }
                >
                  {formatPercent(portfolioChangePct)}
                </span>
                <span className="text-slate-500">letzte 12 Snapshots</span>
              </div>
            </div>
          </motion.article>

          <motion.article layout className="trading-surface trading-hover-glow h-[120px] p-4">
            <div className="mb-2 flex items-start justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Staerkstes Signal</p>
                <p className="mt-1 text-xl font-semibold text-slate-100">
                  {strongestSignal?.symbol ?? "--"}
                  <span className="ml-2 text-sm font-normal text-slate-400">{strongestSignalAsset?.name ?? ""}</span>
                </p>
                <Badge
                  className={cn(
                    "mt-1 border-0 px-2 py-0.5 text-[11px] font-semibold uppercase",
                    strongestSignal ? signalToneClasses(strongestSignal.signal_type) : "bg-slate-700/30 text-slate-300"
                  )}
                >
                  {strongestSignal ? strongestSignal.signal_type : "hold"}
                </Badge>
              </div>
              <ProgressRing
                value={strongestSignal?.strength ?? 0}
                size={56}
                strokeWidth={6}
                progressClassName={
                  strongestSignal?.signal_type === "buy"
                    ? "text-emerald-400"
                    : strongestSignal?.signal_type === "sell"
                      ? "text-red-400"
                      : "text-blue-400"
                }
              />
            </div>
            <p className="line-clamp-1 text-xs text-slate-500">
              {strongestSignal?.reasoning ?? "Noch kein aktives Signal verfuegbar."}
            </p>
          </motion.article>

          <motion.article layout className="trading-surface trading-hover-glow h-[120px] p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Markt-Sentiment</p>
              <Radar className="h-4 w-4 text-blue-300" />
            </div>
            <div className={cn("rounded-lg", sentimentFlashClass)}>
              <SentimentGauge score={marketSentimentScore} className="-mt-2 h-[86px]" />
            </div>
            <p className={cn("mt-1 text-right text-xs", sentimentToneClasses(marketSentimentScore))}>
              {marketSentimentScore.toFixed(2)}
            </p>
          </motion.article>

          <motion.article layout className="trading-surface trading-hover-glow h-[120px] p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Aktivitaet</p>
              <Activity className="h-4 w-4 text-blue-300" />
            </div>
            <div className={cn("flex items-end gap-4", activeSignalFlashClass)}>
              <div>
                <p className="font-mono text-2xl font-bold text-slate-100">{activeSignals}</p>
                <p className="text-[11px] text-slate-500">Aktive Signale</p>
              </div>
              <div>
                <p className="font-mono text-2xl font-bold text-slate-100">{openAlerts}</p>
                <p className="text-[11px] text-slate-500">Offene Alerts</p>
              </div>
            </div>
            <p className="mt-2 line-clamp-1 text-xs text-slate-500">{lastAlertMessage}</p>
          </motion.article>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,1fr)]">
        <section className="relative min-h-[440px] overflow-hidden rounded-2xl bg-[#0a0a14] ring-1 ring-[#1e1e3a]">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.14),transparent_40%)]" />

          <div className="absolute top-3 left-3 z-20">
            <div className="flex items-center gap-2 rounded-xl border border-border/70 bg-[#12121e]/80 p-1.5 backdrop-blur">
              <select
                value={selectedSymbol ?? ""}
                onChange={(event) => setSelectedSymbol(event.target.value)}
                className="h-8 min-w-[118px] rounded-md border border-border/60 bg-[#0d0f1e] px-2 text-xs text-slate-100 outline-none"
              >
                {(assets ?? []).map((asset) => (
                  <option key={asset.symbol} value={asset.symbol}>
                    {asset.symbol}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="absolute top-3 right-3 z-20">
            <div className="flex gap-1 rounded-xl border border-border/70 bg-[#12121e]/80 p-1.5 backdrop-blur">
              {(["1H", "4H", "1D", "1W"] as ChartRange[]).map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => setRange(candidate)}
                  className={cn(
                    "h-8 rounded-md px-2.5 text-xs transition-colors",
                    candidate === range ? "bg-blue-500/25 text-blue-200" : "text-slate-400 hover:bg-slate-700/30"
                  )}
                >
                  {candidate}
                </button>
              ))}
            </div>
          </div>

          <PriceChart data={priceHistory} isLoading={isPriceLoading} className="h-[440px] rounded-none" />
        </section>

        <aside className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-1">
          <section className="trading-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-100">Top Signale</h3>
              <Sparkles className="h-4 w-4 text-blue-300" />
            </div>
            <div className="space-y-2">
              {topSignals.length === 0 ? (
                <p className="rounded-lg bg-slate-800/30 p-3 text-sm text-slate-400">
                  Noch keine Signale - Daten werden gesammelt.
                </p>
              ) : (
                topSignals.map((signal) => (
                  <button
                    key={`${signal.symbol}-${signal.created_at}`}
                    type="button"
                    onClick={() => setSelectedSymbol(signal.symbol)}
                    className="trading-hover-glow flex w-full items-center justify-between rounded-xl px-2 py-2 text-left"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-100">{signal.symbol}</p>
                      <Badge className={cn("mt-1 border-0 text-[10px] uppercase", signalToneClasses(signal.signal_type))}>
                        {signal.signal_type}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-200">{signal.strength.toFixed(1)}</span>
                      <MiniSparkline
                        values={miniSparklineBySymbol?.[signal.symbol]}
                        className="h-5 w-11"
                        strokeClassName={signal.signal_type === "buy" ? "text-emerald-400" : "text-red-400"}
                      />
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="trading-surface p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-100">Sentiment-Radar</h3>
              <LineChart className="h-4 w-4 text-blue-300" />
            </div>
            <div className="space-y-2.5">
              {topSentimentShifts.length === 0 ? (
                <p className="rounded-lg bg-slate-800/30 p-3 text-sm text-slate-400">
                  Noch keine Sentiment-Shifts verfuegbar.
                </p>
              ) : (
                topSentimentShifts.map((item) => {
                  const marker = ((safeScore(item.score) + 1) / 2) * 100;
                  return (
                    <button
                      key={item.symbol}
                      type="button"
                      onClick={() => router.push(`/asset/${item.symbol}`)}
                      className="trading-hover-glow w-full rounded-xl px-2 py-2 text-left"
                    >
                      <div className="mb-1 flex items-center justify-between text-sm">
                        <span className="font-semibold text-slate-100">{item.symbol}</span>
                        <span className={cn("text-xs", item.shift >= 0 ? "text-emerald-300" : "text-red-300")}>
                          {item.shift >= 0 ? "↑" : "↓"}
                          {item.shift >= 0 ? "+" : ""}
                          {item.shift.toFixed(2)}
                        </span>
                      </div>
                      <div className="relative h-2 overflow-hidden rounded-full bg-slate-800">
                        <div className="absolute inset-y-0 left-0 right-0 bg-gradient-to-r from-red-500 via-amber-400 to-emerald-500" />
                        <span
                          className="absolute top-1/2 block h-3 w-1 -translate-y-1/2 rounded bg-white"
                          style={{ left: `calc(${marker}% - 2px)` }}
                        />
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </section>
        </aside>
      </div>

      <section className="trading-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-100">Asset Uebersicht</h3>
          <span className="text-xs text-slate-500">Sticky Header, Live Trends, Sentiment-Balken</span>
        </div>
        <AssetTable
          rows={tableRows}
          isLoading={isAssetsLoading || isSentimentOverviewLoading}
          sparklineBySymbol={miniSparklineBySymbol}
        />
      </section>
    </section>
  );
}
