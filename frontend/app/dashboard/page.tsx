"use client";

import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import useSWR, { mutate } from "swr";
import { Activity, Flame, Radar, TrendingUp } from "lucide-react";

import { AssetTable } from "@/components/AssetTable";
import { PriceChart } from "@/components/PriceChart";
import { SentimentChart } from "@/components/SentimentChart";
import { SentimentGauge } from "@/components/SentimentGauge";
import { SentimentPanel } from "@/components/SentimentPanel";
import { toast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWebSocket } from "@/hooks/useWebSocket";
import { apiHeaders, fetchJson, formatCompactNumber, formatCurrency, formatPercent, parseNumeric } from "@/lib/api";
import type {
  AssetResponse,
  AssetTableRow,
  PricePointResponse,
  SignalPipelineStatusResponse,
  SignalRecommendationResponse,
  SentimentHistoryResponse,
  SentimentOverviewResponse,
  SocialStatsResponse,
  WebSocketStatus,
} from "@/lib/types";

type ChartRange = "1H" | "4H" | "1D" | "1W";

interface RangeConfig {
  timeframe: "1m" | "5m" | "1h" | "1d";
  limit: number;
}

const RANGE_CONFIG: Record<ChartRange, RangeConfig> = {
  "1H": { timeframe: "1m", limit: 120 },
  "4H": { timeframe: "1m", limit: 480 },
  "1D": { timeframe: "1m", limit: 1000 },
  "1W": { timeframe: "5m", limit: 1000 },
};

const STATUS_STYLES: Record<WebSocketStatus, { label: string; className: string }> = {
  connecting: { label: "Verbinde...", className: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" },
  connected: { label: "Live", className: "bg-green-500/20 text-green-300 border-green-500/40" },
  disconnected: { label: "Getrennt", className: "bg-orange-500/20 text-orange-300 border-orange-500/40" },
  error: { label: "Fehler", className: "bg-red-500/20 text-red-300 border-red-500/40" },
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

function KPISkeleton() {
  return <Skeleton className="h-[160px] w-full rounded-xl" />;
}

function ConnectionBadge({ status }: { status: WebSocketStatus }) {
  const style = STATUS_STYLES[status];
  return <Badge className={style.className}>{style.label}</Badge>;
}

interface KpiCardProps {
  title: string;
  value: string;
  subtitle: string;
  icon: ComponentType<{ className?: string }>;
}

function KpiCard({ title, value, subtitle, icon: Icon }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-sm font-medium text-muted-foreground">
          {title}
          <Icon className="h-4 w-4 text-primary" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold text-foreground">{value}</div>
        <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [range, setRange] = useState<ChartRange>("1D");
  const [isBootstrapping, setIsBootstrapping] = useState(false);
  const lastStatusRef = useRef<WebSocketStatus>("connecting");

  const websocketUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/prices";
  const { status: websocketStatus } = useWebSocket(websocketUrl);

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
  const { data: recommendations, error: recommendationsError } = useSWR<SignalRecommendationResponse[]>(
    "/api/signals/recommendations?direction=all&include_hold=true&min_strength=0&limit=8",
    fetchJson,
    { refreshInterval: 45000, revalidateOnFocus: true }
  );

  useEffect(() => {
    if (!selectedSymbol && assets && assets.length > 0) {
      setSelectedSymbol(assets[0].symbol);
    }
  }, [assets, selectedSymbol]);

  const assetSymbolsKey = useMemo(() => (assets ? assets.map((asset) => asset.symbol).join(",") : ""), [assets]);

  const { data: change24hBySymbol } = useSWR<Record<string, number>>(
    assetSymbolsKey ? `/api/dashboard/changes?symbols=${assetSymbolsKey}` : null,
    () => fetchAssetChanges24h(assets ?? []),
    { refreshInterval: 120000, revalidateOnFocus: false }
  );

  const selectedRange = RANGE_CONFIG[range];
  const historyUrl = selectedSymbol
    ? `/api/prices/${selectedSymbol}/history?timeframe=${selectedRange.timeframe}&limit=${selectedRange.limit}`
    : null;
  const sentimentHistoryUrl = selectedSymbol ? `/api/sentiment/${selectedSymbol}/history?timeframe=1h&limit=72` : null;
  const socialStatsUrl = selectedSymbol ? `/api/social/${selectedSymbol}/stats` : null;

  const { data: priceHistory, error: priceError, isLoading: isPriceLoading } = useSWR<PricePointResponse[]>(
    historyUrl,
    fetchJson,
    { refreshInterval: 60000, revalidateOnFocus: true }
  );
  const { data: sentimentHistory, error: sentimentHistoryError, isLoading: isSentimentHistoryLoading } = useSWR<
    SentimentHistoryResponse[]
  >(sentimentHistoryUrl, fetchJson, {
    refreshInterval: 60000,
    revalidateOnFocus: true,
  });
  const { data: socialStats } = useSWR<SocialStatsResponse>(socialStatsUrl, fetchJson, {
    refreshInterval: 60000,
    revalidateOnFocus: true,
  });

  useEffect(() => {
    const previous = lastStatusRef.current;
    if (previous !== websocketStatus) {
      if (websocketStatus === "connected") {
        toast.success("Live-Preisstream verbunden");
      } else if (websocketStatus === "disconnected") {
        toast.warning("WebSocket getrennt - Reconnect laeuft");
      } else if (websocketStatus === "error") {
        toast.error("WebSocket-Fehler aufgetreten");
      }
      lastStatusRef.current = websocketStatus;
    }
  }, [websocketStatus]);

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

  const activeSignals = pipelineStatus?.active_signals ?? 0;

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

  const trendingAsset = useMemo(() => {
    return (sentimentOverview ?? []).reduce<SentimentOverviewResponse | null>((current, item) => {
      if (!current || item.mentions_1h > current.mentions_1h) {
        return item;
      }
      return current;
    }, null);
  }, [sentimentOverview]);

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

  const selectedAsset = useMemo(
    () => (selectedSymbol ? assets?.find((item) => item.symbol === selectedSymbol) : undefined),
    [assets, selectedSymbol]
  );

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
        mutate("/api/signals/recommendations?direction=all&include_hold=true&min_strength=0&limit=8"),
        mutate("/api/signals?limit=100"),
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
    <section className="space-y-6">
      <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Trading Dashboard</h2>
          <p className="text-sm text-muted-foreground">
            Live-Uebersicht fuer Sentiment, Signale und Preisbewegungen.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted-foreground">Stream</span>
          <ConnectionBadge status={websocketStatus} />
        </div>
      </header>

      {(assetsError || sentimentError || priceError || sentimentHistoryError) && (
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-sm text-red-300">
            Mindestens ein Datenfeed konnte nicht geladen werden. Bitte Backend/API-Status pruefen.
          </CardContent>
        </Card>
      )}
      {(pipelineError || recommendationsError) && (
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-sm text-red-300">
            Signal-Pipeline Daten konnten nicht geladen werden.
          </CardContent>
        </Card>
      )}
      {pipelineStatus && pipelineStatus.blockers.length > 0 && (
        <Card className="border-yellow-500/40">
          <CardContent className="space-y-3 pt-6">
            <p className="text-sm text-yellow-200">
              Signal-Pipeline blockiert: {pipelineStatus.blockers.join(" | ")}
            </p>
            <Button onClick={bootstrapPipeline} disabled={isBootstrapping}>
              {isBootstrapping ? "Starte..." : "Pipeline Bootstrap starten"}
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {isAssetsLoading || isSentimentOverviewLoading ? (
          <>
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
            <KPISkeleton />
          </>
        ) : (
          <>
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="flex items-center justify-between text-sm font-medium text-muted-foreground">
                  Markt-Sentiment
                  <Radar className="h-4 w-4 text-primary" />
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SentimentGauge score={marketSentimentScore} />
              </CardContent>
            </Card>
            <KpiCard
              title="Aktive Signale"
              value={`${activeSignals}`}
              subtitle="Assets mit starkem Sentimentimpuls"
              icon={Activity}
            />
            <KpiCard
              title="Top Mover"
              value={topMover ? `${topMover.symbol} ${formatPercent(topMover.change)}` : "--"}
              subtitle="Groesste 24h-Preisbewegung"
              icon={TrendingUp}
            />
            <KpiCard
              title="Trending Asset"
              value={trendingAsset ? trendingAsset.symbol : "--"}
              subtitle={
                trendingAsset ? `${formatCompactNumber(trendingAsset.mentions_1h)} Erwaehnungen / 1h` : "Keine Daten"
              }
              icon={Flame}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader className="space-y-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <CardTitle className="text-base">Candlestick Chart</CardTitle>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Select
                  value={selectedSymbol ?? ""}
                  onValueChange={(symbol) => {
                    setSelectedSymbol(symbol);
                  }}
                >
                  <SelectTrigger className="w-full sm:w-44">
                    <SelectValue placeholder="Asset waehlen" />
                  </SelectTrigger>
                  <SelectContent>
                    {(assets ?? []).map((asset) => (
                      <SelectItem key={asset.symbol} value={asset.symbol}>
                        {asset.symbol}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="flex flex-wrap gap-1.5">
                  {(["1H", "4H", "1D", "1W"] as ChartRange[]).map((candidate) => (
                    <Button
                      key={candidate}
                      variant={candidate === range ? "default" : "outline"}
                      size="sm"
                      onClick={() => setRange(candidate)}
                    >
                      {candidate}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
            <Separator />
          </CardHeader>
          <CardContent>
            <PriceChart data={priceHistory} isLoading={isPriceLoading} />
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Sentiment Uebersicht</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="overview">Assets</TabsTrigger>
                <TabsTrigger value="history">Verlauf</TabsTrigger>
              </TabsList>
              <TabsContent value="overview" className="mt-3">
                <SentimentPanel selectedSymbol={selectedSymbol} onSelectSymbol={setSelectedSymbol} />
              </TabsContent>
              <TabsContent value="history" className="mt-3">
                <SentimentChart data={sentimentHistory} isLoading={isSentimentHistoryLoading} />
              </TabsContent>
            </Tabs>

            <Separator />

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-md bg-muted/50 p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Aktuell</p>
                <p className="mt-1 text-base font-medium text-foreground">{selectedSymbol ?? "--"}</p>
              </div>
              <div className="rounded-md bg-muted/50 p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Preis</p>
                <p className="mt-1 text-base font-medium text-foreground">
                  {formatCurrency(parseNumeric(selectedAsset?.latest_close ?? null))}
                </p>
              </div>
              <div className="rounded-md bg-muted/50 p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Sentiment-Score</p>
                <p className="mt-1 text-base font-medium text-foreground">
                  {safeScore(sentimentBySymbol.get(selectedSymbol ?? "")?.score).toFixed(2)}
                </p>
              </div>
              <div className="rounded-md bg-muted/50 p-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Erwaehnungen</p>
                <p className="mt-1 text-base font-medium text-foreground">
                  {socialStats ? formatCompactNumber(socialStats.total_mentions) : "--"}
                </p>
              </div>
            </div>
            <Separator />
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Tool Vorschlaege</p>
              {(recommendations ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">Noch keine Buy-Empfehlungen.</p>
              ) : (
                <div className="space-y-1">
                  {(recommendations ?? []).slice(0, 5).map((item) => (
                    <button
                      key={`${item.symbol}-${item.created_at}`}
                      type="button"
                      className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left hover:bg-muted/40"
                      onClick={() => setSelectedSymbol(item.symbol)}
                    >
                      <span className="text-sm font-medium">{item.symbol}</span>
                      <span
                        className={`text-xs ${
                          item.signal_type === "buy"
                            ? "text-green-300"
                            : item.signal_type === "sell"
                              ? "text-red-300"
                              : "text-yellow-300"
                        }`}
                      >
                        {item.signal_type.toUpperCase()} {item.strength.toFixed(1)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Asset Uebersicht</CardTitle>
        </CardHeader>
        <CardContent>
          <AssetTable rows={tableRows} isLoading={isAssetsLoading || isSentimentOverviewLoading} />
        </CardContent>
      </Card>
    </section>
  );
}
