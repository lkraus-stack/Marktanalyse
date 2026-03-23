"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { BrainCircuit, Loader2, Radar, Search, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { apiHeaders, fetchJson, formatCurrency, formatPercent } from "@/lib/api";
import type {
  DiscoveryCandidateResponse,
  DiscoverySearchResponse,
  MarketSummaryResponse,
  SignalScorecardResponse,
} from "@/lib/types";

type RiskProfile = "low" | "balanced" | "high";
type Direction = "all" | "buy" | "sell";
type AssetType = "all" | "stock" | "crypto";
type Horizon = "24h" | "72h" | "7d";

async function fetchOptionalJson<T>(url: string): Promise<T | null> {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...apiHeaders(),
    },
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`API request failed (${response.status}): ${url}`);
  }
  return (await response.json()) as T;
}

function riskLabel(value: RiskProfile): string {
  if (value === "low") {
    return "Defensiv";
  }
  if (value === "high") {
    return "Chancenreich";
  }
  return "Ausgewogen";
}

function directionLabel(value: Direction): string {
  if (value === "buy") {
    return "Kauf-Ideen";
  }
  if (value === "sell") {
    return "Verkaufs-/Absicherungs-Ideen";
  }
  return "Alle Signale";
}

function riskBucketBadge(bucket: DiscoveryCandidateResponse["risk_bucket"]) {
  if (bucket === "low") {
    return <Badge className="border-0 bg-emerald-500/15 text-emerald-200">niedriges Risiko</Badge>;
  }
  if (bucket === "high") {
    return <Badge className="border-0 bg-red-500/15 text-red-200">hohes Risiko</Badge>;
  }
  return <Badge className="border-0 bg-amber-500/15 text-amber-200">mittleres Risiko</Badge>;
}

function signalBadge(signalType: DiscoveryCandidateResponse["signal_type"]) {
  if (signalType === "buy") {
    return <Badge className="border-0 bg-emerald-500/15 text-emerald-200">buy</Badge>;
  }
  if (signalType === "sell") {
    return <Badge className="border-0 bg-red-500/15 text-red-200">sell</Badge>;
  }
  return <Badge className="border-0 bg-slate-500/15 text-slate-200">hold</Badge>;
}

export default function SentimentPage() {
  const [riskProfile, setRiskProfile] = useState<RiskProfile>("balanced");
  const [direction, setDirection] = useState<Direction>("buy");
  const [assetType, setAssetType] = useState<AssetType>("all");
  const [horizon, setHorizon] = useState<Horizon>("72h");
  const [limit, setLimit] = useState(10);
  const [query, setQuery] = useState(
    "Finde mir 10 Chancen mit News-Momentum, nachvollziehbarem Signal und passendem Risiko fuer mein Profil."
  );
  const [isSearching, setIsSearching] = useState(false);
  const [searchResult, setSearchResult] = useState<DiscoverySearchResponse | null>(null);

  const discoveryUrl = useMemo(
    () =>
      `/api/discovery/candidates?risk_profile=${riskProfile}&direction=${direction}&asset_type=${assetType}&horizon=${horizon}&limit=${limit}`,
    [assetType, direction, horizon, limit, riskProfile]
  );
  const scorecardUrl = useMemo(
    () => `/api/signals/scorecard?horizon=${horizon}&asset_type=${assetType}&limit=300`,
    [assetType, horizon]
  );

  const { data: marketSummary, isLoading: isSummaryLoading } = useSWR<MarketSummaryResponse | null>(
    "/api/market-summary",
    fetchOptionalJson,
    { refreshInterval: 60000 }
  );
  const { data: localCandidates, isLoading: isCandidatesLoading } = useSWR<DiscoveryCandidateResponse[]>(
    discoveryUrl,
    fetchJson,
    { refreshInterval: 45000 }
  );
  const { data: scorecard, isLoading: isScorecardLoading } = useSWR<SignalScorecardResponse>(
    scorecardUrl,
    fetchJson,
    { refreshInterval: 60000 }
  );

  const topCandidate = localCandidates?.[0] ?? null;

  const runDiscoverySearch = async () => {
    if (!query.trim()) {
      toast.error("Bitte gib eine Discovery-Frage ein.");
      return;
    }
    setIsSearching(true);
    try {
      const response = await fetch("/api/discovery/search", {
        method: "POST",
        headers: {
          ...apiHeaders(true),
        },
        body: JSON.stringify({
          query,
          risk_profile: riskProfile,
          direction,
          asset_type: assetType,
          horizon,
          limit,
        }),
      });
      const payload = (await response.json().catch(() => null)) as DiscoverySearchResponse | { detail?: string } | null;
      if (!response.ok) {
        throw new Error(payload && "detail" in payload && typeof payload.detail === "string" ? payload.detail : "Discovery fehlgeschlagen.");
      }
      const result = payload as DiscoverySearchResponse;
      setSearchResult(result);
      if (result.status === "success") {
        toast.success("Sonar-Discovery erfolgreich aktualisiert.");
      } else if (result.status === "partial") {
        toast.error("Discovery lieferte Text, aber nicht alle Kandidaten konnten strukturiert gelesen werden.");
      } else {
        const firstError = result.errors[0];
        toast.error(firstError?.status_code ? `Discovery-Fehler HTTP ${firstError.status_code}` : "Discovery-Fehler.");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Discovery konnte nicht gestartet werden.");
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <section className="space-y-6">
      <header className="rounded-2xl border border-border/70 bg-[#0d0f1c] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <BrainCircuit className="h-5 w-5 text-blue-300" />
              <h1 className="text-2xl font-semibold text-slate-100">Sentiment & Discovery Lab</h1>
            </div>
            <p className="max-w-3xl text-sm text-slate-400">
              Sonar sucht nach Discovery-Ideen, lokale Signale werden gegen die Vergangenheit geprueft und das Risiko
              wird nach Volatilitaet eingeordnet. So siehst du schneller, welche Setups informativ sind und ob sie in
              der Praxis ueberhaupt etwas gebracht haetten.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge className="border-0 bg-blue-500/15 text-blue-200">Discovery: Sonar</Badge>
            <Badge className="border-0 bg-violet-500/15 text-violet-200">Validierung/Fallback: GPT OSS</Badge>
            <Badge className="border-0 bg-slate-500/15 text-slate-200">Profil: {riskLabel(riskProfile)}</Badge>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-300" />
              Markt-Kontext
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isSummaryLoading ? (
              <Skeleton className="h-28 w-full" />
            ) : marketSummary ? (
              <div className="rounded-lg border border-border bg-background/50 p-4">
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">{marketSummary.text_snippet}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {marketSummary.author ? `Modell: ${marketSummary.author} | ` : ""}
                  Aktualisiert: {new Date(marketSummary.created_at).toLocaleString("de-DE")}
                </p>
              </div>
            ) : (
              <p className="rounded-lg border border-border bg-background/50 p-4 text-sm text-muted-foreground">
                Noch keine globale Market Summary vorhanden. Du kannst trotzdem mit lokalen Signalen und Discovery
                arbeiten.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-300" />
              Testbot
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {isScorecardLoading ? (
              <Skeleton className="h-28 w-full" />
            ) : scorecard ? (
              <>
                <div className="flex items-center justify-between">
                  <span>Trefferquote</span>
                  <Badge variant="secondary">{formatPercent(scorecard.hit_rate_pct)}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span>Durchschnittlicher Signal-Ertrag</span>
                  <Badge variant="secondary">{formatPercent(scorecard.avg_strategy_return_pct)}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span>Bewertete Signale</span>
                  <Badge variant="secondary">{scorecard.evaluated_signals}</Badge>
                </div>
                {scorecard.top_symbols[0] && (
                  <p className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs text-emerald-100">
                    Bisher stark: {scorecard.top_symbols[0].symbol} mit {formatPercent(scorecard.top_symbols[0].hit_rate_pct)} Trefferquote
                    und {formatPercent(scorecard.top_symbols[0].avg_strategy_return_pct)} durchschnittlichem Signal-Ertrag.
                  </p>
                )}
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-4 w-4 text-blue-300" />
            Sonar Discovery
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
            <label className="space-y-1 text-xs">
              <span className="text-slate-500">Risikoprofil</span>
              <select
                value={riskProfile}
                onChange={(event) => setRiskProfile(event.target.value as RiskProfile)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="low">Defensiv</option>
                <option value="balanced">Ausgewogen</option>
                <option value="high">Chancenreich</option>
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-slate-500">Signalrichtung</span>
              <select
                value={direction}
                onChange={(event) => setDirection(event.target.value as Direction)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="buy">Kauf-Ideen</option>
                <option value="sell">Verkaufs-/Absicherungsideen</option>
                <option value="all">Alle Signale</option>
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-slate-500">Asset-Typ</span>
              <select
                value={assetType}
                onChange={(event) => setAssetType(event.target.value as AssetType)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="all">Alle</option>
                <option value="stock">Aktien</option>
                <option value="crypto">Krypto</option>
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-slate-500">Testbot-Horizont</span>
              <select
                value={horizon}
                onChange={(event) => setHorizon(event.target.value as Horizon)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="24h">24 Stunden</option>
                <option value="72h">72 Stunden</option>
                <option value="7d">7 Tage</option>
              </select>
            </label>
            <label className="space-y-1 text-xs">
              <span className="text-slate-500">Anzahl Ideen</span>
              <input
                type="number"
                min={3}
                max={20}
                value={limit}
                onChange={(event) => setLimit(Math.max(3, Math.min(20, Number(event.target.value) || 10)))}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              />
            </label>
          </div>
          <label className="space-y-2 text-xs">
            <span className="text-slate-500">Discovery-Frage</span>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              rows={4}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="Zum Beispiel: Finde mir 10 Aktien mit positivem News-Flow, aber noch nicht ueberhitztem Risiko."
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button onClick={runDiscoverySearch} disabled={isSearching}>
              {isSearching && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Discovery starten
            </Button>
            <Badge className="border-0 bg-slate-500/15 text-slate-200">{directionLabel(direction)}</Badge>
            <Badge className="border-0 bg-slate-500/15 text-slate-200">Risiko: {riskLabel(riskProfile)}</Badge>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Radar className="h-4 w-4 text-violet-300" />
              Lokale Kandidaten
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {isCandidatesLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, index) => (
                  <Skeleton key={index} className="h-28 w-full" />
                ))}
              </div>
            ) : localCandidates && localCandidates.length > 0 ? (
              <>
                {topCandidate && (
                  <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-4 text-sm">
                    <p className="font-semibold text-slate-100">Schnellster Fit im aktuellen Profil: {topCandidate.symbol}</p>
                    <p className="mt-1 text-slate-300">
                      {topCandidate.name} | Discovery-Score {topCandidate.discovery_score.toFixed(1)} | Risiko{" "}
                      {topCandidate.risk_bucket}
                    </p>
                  </div>
                )}
                <div className="space-y-3">
                  {localCandidates.map((candidate) => (
                    <div key={`${candidate.symbol}-${candidate.created_at}`} className="rounded-lg border border-border bg-background/40 p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <Link href={`/asset/${candidate.symbol}`} className="text-base font-semibold text-slate-100 hover:text-blue-300">
                              {candidate.symbol}
                            </Link>
                            {signalBadge(candidate.signal_type)}
                            {riskBucketBadge(candidate.risk_bucket)}
                          </div>
                          <p className="text-sm text-slate-300">{candidate.name}</p>
                          <p className="text-xs text-slate-400">{candidate.reasoning}</p>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-slate-400 lg:min-w-[280px]">
                          <MetricChip label="Preis" value={formatCurrency(candidate.latest_price)} />
                          <MetricChip label="Signal-Staerke" value={candidate.strength.toFixed(1)} />
                          <MetricChip label="Discovery-Score" value={candidate.discovery_score.toFixed(1)} />
                          <MetricChip label="Volatilitaet" value={formatPercent(candidate.volatility_pct)} />
                          <MetricChip label="Trefferquote" value={formatPercent(candidate.historical_hit_rate_pct)} />
                          <MetricChip label="Signal-Ertrag" value={formatPercent(candidate.historical_avg_return_pct)} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="rounded-lg border border-border bg-background/40 p-4 text-sm text-muted-foreground">
                Noch keine lokalen Kandidaten. Pruefe Pipeline und Signale.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-300" />
              AI Discovery Ergebnis
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {!searchResult ? (
              <p className="rounded-lg border border-border bg-background/40 p-4 text-muted-foreground">
                Starte eine Discovery-Suche, damit Sonar die lokalen Signale, die Scorecard und aktuelle News in eine
                lesbare Kandidatenliste uebersetzt.
              </p>
            ) : (
              <>
                <div className="rounded-lg border border-border bg-background/40 p-4">
                  <p className="font-medium text-slate-100">
                    Lauf: {searchResult.status} | Provider: {searchResult.provider} | Modell:{" "}
                    {searchResult.used_model ?? searchResult.primary_model}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Primär: {searchResult.primary_model}
                    {searchResult.validation_model ? ` | Validierung/Fallback: ${searchResult.validation_model}` : ""}
                  </p>
                  {searchResult.ai_summary && (
                    <p className="mt-3 whitespace-pre-wrap text-slate-200">{searchResult.ai_summary}</p>
                  )}
                </div>
                {searchResult.errors.length > 0 && (
                  <div className="space-y-2">
                    {searchResult.errors.slice(0, 3).map((error, index) => (
                      <div key={`${error.model}-${index}`} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                        <p className="font-medium text-red-200">
                          {error.model ?? "KI-Modell"}{error.status_code ? ` | HTTP ${error.status_code}` : ""}
                        </p>
                        <p className="mt-1 text-red-100/90">{error.message}</p>
                        {error.response_excerpt && <p className="mt-1 text-xs text-red-100/70">{error.response_excerpt}</p>}
                      </div>
                    ))}
                  </div>
                )}
                {searchResult.candidates.length > 0 ? (
                  <div className="space-y-3">
                    {searchResult.candidates.map((candidate, index) => (
                      <div key={`${candidate.symbol}-${index}`} className="rounded-lg border border-border bg-background/40 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-100">{candidate.symbol}</p>
                            <p className="text-xs uppercase tracking-wide text-slate-500">{candidate.action}</p>
                          </div>
                          {candidate.confidence !== null && (
                            <Badge className="border-0 bg-blue-500/15 text-blue-200">
                              Confidence {(candidate.confidence * 100).toFixed(0)}%
                            </Badge>
                          )}
                        </div>
                        <p className="mt-2 text-slate-200">{candidate.thesis}</p>
                        <p className="mt-2 text-xs text-slate-400">Risiko: {candidate.risk_note}</p>
                      </div>
                    ))}
                  </div>
                ) : searchResult.raw_response ? (
                  <div className="rounded-lg border border-border bg-background/40 p-4">
                    <p className="text-xs text-muted-foreground">
                      Die Antwort war nicht komplett als JSON lesbar. Rohtext:
                    </p>
                    <p className="mt-2 whitespace-pre-wrap text-slate-200">{searchResult.raw_response}</p>
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function MetricChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/60 bg-background/60 p-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-slate-200">{value}</p>
    </div>
  );
}
