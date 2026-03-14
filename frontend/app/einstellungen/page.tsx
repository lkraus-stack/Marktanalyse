"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { AlertTriangle, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { apiHeaders, fetchJson } from "@/lib/api";
import type { TradingSettingsResponse, TradingStatusResponse } from "@/lib/types";

interface HealthResponse {
  status: string;
  checks?: {
    api_keys?: Record<string, boolean>;
  };
}

function configuredBadge(value: boolean) {
  return value ? <Badge variant="default">konfiguriert</Badge> : <Badge variant="destructive">fehlt</Badge>;
}

export default function EinstellungenPage() {
  const [activationText, setActivationText] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [telegramEnabled, setTelegramEnabled] = useState(false);

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
                <span>Perplexity Key</span>
                {configuredBadge(Boolean(health?.checks?.api_keys?.perplexity))}
              </div>
              <p className="text-xs text-muted-foreground">
                Hinweise: Keys werden nur serverseitig aus Env-Variablen gelesen und nie im Frontend gespeichert.
              </p>
            </CardContent>
          </Card>
        </div>
      )}

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
