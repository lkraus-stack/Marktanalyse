"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { PriceChart } from "@/components/PriceChart";
import { SentimentChart } from "@/components/SentimentChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchJson, formatCurrency, parseNumeric } from "@/lib/api";
import type { PricePointResponse, SentimentHistoryResponse, SentimentOverviewResponse } from "@/lib/types";

export default function AssetDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = (params?.symbol ?? "").toUpperCase();

  const { data: latestPrice } = useSWR<PricePointResponse>(
    symbol ? `/api/prices/${symbol}` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: priceHistory, isLoading: isPriceLoading } = useSWR<PricePointResponse[]>(
    symbol ? `/api/prices/${symbol}/history?timeframe=1m&limit=1000` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: sentimentHistory, isLoading: isSentimentLoading } = useSWR<SentimentHistoryResponse[]>(
    symbol ? `/api/sentiment/${symbol}/history?timeframe=1h&limit=72` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: sentimentSnapshot } = useSWR<SentimentOverviewResponse>(
    symbol ? `/api/sentiment/${symbol}` : null,
    fetchJson,
    { refreshInterval: 60000 }
  );

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">{symbol}</h2>
          <p className="text-sm text-muted-foreground">Detailansicht fuer Preis und Sentiment.</p>
        </div>
        <Button asChild variant="outline">
          <Link href="/dashboard">Zurueck zum Dashboard</Link>
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Letzter Preis</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-foreground">
            {formatCurrency(parseNumeric(latestPrice?.close ?? null))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Sentiment</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-foreground">
            {(sentimentSnapshot?.score ?? 0).toFixed(2)}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground">Erwaehnungen (1h)</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold text-foreground">
            {sentimentSnapshot?.mentions_1h ?? 0}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Kursverlauf</CardTitle>
        </CardHeader>
        <CardContent>
          <PriceChart data={priceHistory} isLoading={isPriceLoading} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sentiment-Verlauf</CardTitle>
        </CardHeader>
        <CardContent>
          <SentimentChart data={sentimentHistory} isLoading={isSentimentLoading} />
        </CardContent>
      </Card>
    </section>
  );
}
