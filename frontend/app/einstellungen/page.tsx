"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { AlertTriangle, Loader2, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { apiHeaders, fetchJson } from "@/lib/api";
import type {
  AssetResponse,
  DefaultAssetSeedResponse,
  MarketSummaryRefreshResponse,
  MarketSummaryResponse,
  SignalPipelineStatusResponse,
  TradingSettingsResponse,
  TradingStatusResponse,
} from "@/lib/types";

interface HealthResponse {
  status: string;
  checks?: {
    api_keys?: Record<string, boolean>;
  };
}

function configuredBadge(value: boolean) {
  return value ? <Badge variant="default">konfiguriert</Badge> : <Badge variant="destructive">fehlt</Badge>;
}

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

export default function EinstellungenPage() {
  const [activationText, setActivationText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [isSeedingDefaults, setIsSeedingDefaults] = useState(false);
  const [isBootstrappingPipeline, setIsBootstrappingPipeline] = useState(false);
  const [isRefreshingSummary, setIsRefreshingSummary] = useState(false);
  const [summaryRefreshResult, setSummaryRefreshResult] = useState<MarketSummaryRefreshResponse | null>(null);
  const summaryEndpoint =
    summaryRefreshResult === null
      ? null
      : summaryRefreshResult.chat_completions_path.startsWith("http://") ||
          summaryRefreshResult.chat_completions_path.startsWith("https://")
        ? summaryRefreshResult.chat_completions_path
        : `${summaryRefreshResult.base_url}${summaryRefreshResult.chat_completions_path}`;

  const { data: tradingStatus, isLoading: isStatusLoading } = useSWR<TradingStatusResponse>(
    "/api/trading/status",
    fetchJson,
    { refreshInterval: 15000 }
  );
  const { data: tradingSettings, isLoading: isSettingsLoading } = useSWR<TradingSettingsResponse>(
    "/api/trading/settings",
    fetchJson,
    { refreshInterval: 30000 }
  );
  const { data: health } = useSWR<HealthResponse>("/api/health", fetchJson, { refreshInterval: 30000 });
  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, { refreshInterval: 60000 });
  const { data: pipelineStatus } = useSWR<SignalPipelineStatusResponse>("/api/signals/pipeline-status", fetchJson, {
    refreshInterval: 30000,
  });
  const { data: marketSummary } = useSWR<MarketSummaryResponse | null>("/api/market-summary", fetchOptionalJson, {
    refreshInterval: 60000,
  });

  const activateLiveTrading = async () => {
    if (!activationText.trim()) {
      toast.error("Bitte BESTÄTIGEN eingeben.");
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/trading/settings", {
        method: "PATCH",
        headers: apiHeaders(true),
        body: JSON.stringify({ is_live: true, activation_phrase: activationText }),
      });
      if (!response.ok) {
        throw new Error("activation failed");
      }
      toast.success("Live Trading aktiviert.");
      setActivationText("");
      await Promise.all([mutate("/api/trading/settings"), mutate("/api/trading/status")]);
    } catch {
      toast.error("Aktivierung fehlgeschlagen. Bitte BESTÄTIGEN exakt eingeben.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const deactivateLiveTrading = async () => {
    setIsSubmitting(true);
    try {
      const response = await fetch("/api/trading/settings", {
        method: "PATCH",
        headers: apiHeaders(true),
        body: JSON.stringify({ is_live: false }),
      });
      if (!response.ok) {
        throw new Error("deactivate failed");
      }
      toast.success("Live Trading deaktiviert.");
      await Promise.all([mutate("/api/trading/settings"), mutate("/api/trading/status")]);
    } catch {
      toast.error("Deaktivierung fehlgeschlagen.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const seedDefaultAssets = async () => {
    setIsSeedingDefaults(true);
    try {
      const response = await fetch("/api/assets/seed-defaults", { method: "POST", headers: apiHeaders() });
      if (!response.ok) {
        throw new Error("seed failed");
      }
      const result = (await response.json()) as DefaultAssetSeedResponse;
      if (result.seeded_count > 0) {
        toast.success(`${result.seeded_count} Standard-Assets importiert.`);
      } else {
        toast.success("Standard-Assets waren bereits vorhanden.");
      }
      await Promise.all([mutate("/api/assets"), mutate("/api/signals/pipeline-status")]);
    } catch {
      toast.error("Standard-Assets konnten nicht importiert werden.");
    } finally {
      setIsSeedingDefaults(false);
    }
  };

  const bootstrapPipeline = async () => {
    setIsBootstrappingPipeline(true);
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
      toast.error("Pipeline-Bootstrap fehlgeschlagen. Bitte Backend-Logs pruefen.");
    } finally {
      setIsBootstrappingPipeline(false);
    }
  };

  const refreshMarketSummary = async () => {
    setIsRefreshingSummary(true);
    try {
      const response = await fetch("/api/market-summary/refresh", { method: "POST", headers: apiHeaders() });
      const payload = (await response.json().catch(() => null)) as MarketSummaryRefreshResponse | { detail?: string } | null;
      if (!response.ok) {
        throw new Error(payload && "detail" in payload && typeof payload.detail === "string" ? payload.detail : "market summary refresh failed");
      }
      const result = payload as MarketSummaryRefreshResponse;
      setSummaryRefreshResult(result);
      if (result.status === "success" && result.saved_count > 0) {
        toast.success("KI-Market Summary aktualisiert.");
      } else if (result.status === "partial") {
        const firstError = result.errors[0];
        toast.error(
          firstError
            ? `Teilweise erfolgreich, aber ${firstError.model ?? "ein Modell"} lieferte einen Fehler.`
            : "Teilweise erfolgreich, aber nicht alle KI-Aufrufe waren sauber."
        );
      } else if (result.errors.length > 0) {
        const firstError = result.errors[0];
        toast.error(
          firstError.status_code
            ? `${firstError.model ?? "KI-Modell"}: HTTP ${firstError.status_code}`
            : firstError.message
        );
      } else {
        toast.success("Keine neue KI-Market Summary erzeugt.");
      }
      await Promise.all([mutate("/api/market-summary"), mutate("/api/sentiment/overview")]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "KI-Market Summary konnte nicht aktualisiert werden.");
    } finally {
      setIsRefreshingSummary(false);
    }
  };

  return (
    <section className="space-y-6">
      <Card className={(tradingSettings?.is_live ?? false) ? "border-red-500/60 bg-red-500/10" : "border-green-500/60 bg-green-500/10"}>
        <CardContent className="flex items-start gap-3 py-4">
          {(tradingSettings?.is_live ?? false) ? (
            <ShieldAlert className="mt-0.5 h-5 w-5 text-red-400" />
          ) : (
            <ShieldCheck className="mt-0.5 h-5 w-5 text-green-400" />
          )}
          <div>
            <p className="text-lg font-semibold">
              {(tradingSettings?.is_live ?? false) ? "LIVE MODUS AKTIV" : "PAPER MODUS AKTIV"}
            </p>
            <p className="text-sm text-muted-foreground">
              {(tradingSettings?.is_live ?? false)
                ? "Echtgeld-Risiko aktiv. Achte auf Verlustlimits, Double-Confirm und Tageslimits."
                : "Sicherer Simulationsmodus ohne echtes Kapital."}
            </p>
          </div>
        </CardContent>
      </Card>

      {isStatusLoading || isSettingsLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Broker-Status</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span>Alpaca</span>
                {configuredBadge(Boolean(tradingStatus?.alpaca_configured))}
              </div>
              <div className="flex items-center justify-between">
                <span>Kraken</span>
                {configuredBadge(Boolean(tradingStatus?.kraken_configured))}
              </div>
              <div className="flex items-center justify-between">
                <span>Modus</span>
                <Badge variant={(tradingStatus?.is_live ?? false) ? "destructive" : "default"}>
                  {(tradingStatus?.is_live ?? false) ? "live" : "paper"}
                </Badge>
              </div>
              {tradingStatus?.live_stop_reason && (
                <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-red-300">
                  Trading gestoppt: {tradingStatus.live_stop_reason}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>API-Key Konfiguration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span>Alpaca Keys</span>
                {configuredBadge(Boolean(health?.checks?.api_keys?.alpaca))}
              </div>
              <div className="flex items-center justify-between">
                <span>Kraken Keys</span>
                {configuredBadge(Boolean(health?.checks?.api_keys?.kraken))}
              </div>
              <div className="flex items-center justify-between">
                <span>Finnhub Key</span>
                {configuredBadge(Boolean(health?.checks?.api_keys?.finnhub))}
              </div>
              <div className="flex items-center justify-between">
                <span>KI / Sonar Key</span>
                {configuredBadge(Boolean(health?.checks?.api_keys?.ai_summary ?? health?.checks?.api_keys?.perplexity))}
              </div>
              <p className="text-xs text-muted-foreground">
                Hinweise: Keys werden nur serverseitig aus Env-Variablen gelesen und nie im Frontend gespeichert.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Onboarding & Pipeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <span>Aktive Assets</span>
              <Badge variant="secondary">{pipelineStatus?.assets_total ?? assets?.length ?? 0}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>1m Preisdaten</span>
              <Badge variant="secondary">{pipelineStatus?.price_points_1m ?? 0}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>1h Preisdaten</span>
              <Badge variant="secondary">{pipelineStatus?.price_points_h1 ?? 0}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>Aktive Signale</span>
              <Badge variant="secondary">{pipelineStatus?.active_signals ?? 0}</Badge>
            </div>
            {pipelineStatus?.blockers && pipelineStatus.blockers.length > 0 && (
              <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                {pipelineStatus.blockers.join(" | ")}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={seedDefaultAssets} disabled={isSeedingDefaults}>
                {isSeedingDefaults && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Standard-Assets importieren
              </Button>
              <Button onClick={bootstrapPipeline} disabled={isBootstrappingPipeline}>
                {isBootstrappingPipeline && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Pipeline Bootstrap
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Empfohlene Reihenfolge: zuerst Standard-Assets importieren, danach einen manuellen Pipeline-Bootstrap starten.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-300" />
              KI & Sonar Summary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <span>KI / Sonar</span>
              {configuredBadge(Boolean(health?.checks?.api_keys?.ai_summary ?? health?.checks?.api_keys?.perplexity))}
            </div>
            {marketSummary ? (
              <div className="rounded-md border border-border bg-background/60 p-3">
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">{marketSummary.text_snippet}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {marketSummary.asset_symbol ? `Asset: ${marketSummary.asset_symbol} | ` : ""}
                  {marketSummary.author ? `Modell: ${marketSummary.author} | ` : ""}
                  Aktualisiert: {new Date(marketSummary.created_at).toLocaleString("de-DE")}
                </p>
              </div>
            ) : (
              <p className="rounded-md border border-border p-3 text-xs text-muted-foreground">
                Noch keine KI-Market Summary vorhanden. Setze zuerst `AI_API_KEY` und die KI-URL im Backend und starte
                danach eine manuelle Aktualisierung oder den Scheduler.
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={refreshMarketSummary} disabled={isRefreshingSummary}>
                {isRefreshingSummary && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Market Summary aktualisieren
              </Button>
            </div>
            {summaryRefreshResult && (
              <div className="rounded-md border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                <p className="font-medium text-slate-200">
                  Letzter Lauf: {summaryRefreshResult.status} | gespeichert: {summaryRefreshResult.saved_count}
                </p>
                <p className="mt-1">
                  Provider: {summaryRefreshResult.provider} | Modell: {summaryRefreshResult.primary_model}
                  {summaryRefreshResult.validation_model ? ` | Validierung/Fallback: ${summaryRefreshResult.validation_model}` : ""}
                </p>
                <p className="mt-1">Verwendet: {summaryRefreshResult.used_models.join(", ") || "noch keines"}</p>
                <p className="mt-1 break-all">Endpoint: {summaryEndpoint}</p>
                {summaryRefreshResult.errors.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {summaryRefreshResult.errors.slice(0, 4).map((item, index) => (
                      <div key={`${item.scope}-${item.model}-${index}`} className="rounded border border-red-500/20 bg-red-500/5 p-2">
                        <p className="font-medium text-red-200">
                          {item.scope === "asset" && item.asset_symbol ? `${item.asset_symbol}: ` : ""}
                          {item.model ?? "KI-Modell"}{item.status_code ? ` | HTTP ${item.status_code}` : ""}
                        </p>
                        <p className="mt-1 text-red-100/90">{item.message}</p>
                        {item.response_excerpt && <p className="mt-1 break-words text-red-100/70">{item.response_excerpt}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Die Summary dient als KI-Layer fuer Discovery und Validierung. Das eigentliche Handels-Signal bleibt
              weiterhin quantitativ reproduzierbar.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Benachrichtigungen & Theme</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-sm font-medium">In-App Notifications</p>
              <p className="text-xs text-muted-foreground">Toast-Benachrichtigungen fuer Alerts und Trading-Events.</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => setNotificationsEnabled((prev) => !prev)}>
              {notificationsEnabled ? "An" : "Aus"}
            </Button>
          </div>
          <div className="flex items-center justify-between rounded-md border border-border p-3">
            <div>
              <p className="text-sm font-medium">Telegram Prioritaet</p>
              <p className="text-xs text-muted-foreground">Zusatzkanal fuer kritische Events im Live-Modus.</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => setTelegramEnabled((prev) => !prev)}>
              {telegramEnabled ? "An" : "Aus"}
            </Button>
          </div>
          <div className="rounded-md border border-border p-3">
            <p className="text-sm font-medium">Theme</p>
            <p className="text-xs text-muted-foreground">Dark ist fuer Trading als Produktionsstandard gesetzt.</p>
          </div>
        </CardContent>
      </Card>

      <Card className="border-red-500/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400" />
            Live Trading Schutzaktivierung
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Um Live Trading zu aktivieren, tippe exakt <span className="font-semibold text-red-300">BESTÄTIGEN</span>.
          </p>
          <input
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            placeholder="BESTÄTIGEN"
            value={activationText}
            onChange={(event) => setActivationText(event.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="destructive"
              onClick={activateLiveTrading}
              disabled={isSubmitting || (tradingSettings?.is_live ?? false)}
            >
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Live aktivieren
            </Button>
            <Button
              variant="outline"
              onClick={deactivateLiveTrading}
              disabled={isSubmitting || !(tradingSettings?.is_live ?? false)}
            >
              Auf Paper zurueck
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
