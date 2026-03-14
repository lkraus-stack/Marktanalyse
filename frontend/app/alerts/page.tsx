"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { Bell, Loader2, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { useWebSocket } from "@/hooks/useWebSocket";
import { fetchJson } from "@/lib/api";
import type {
  AlertHistoryResponse,
  AlertResponse,
  AlertTriggeredMessage,
  AlertType,
  AssetResponse,
  DeliveryMethod,
} from "@/lib/types";

type ThresholdDirection = "above" | "below";
type SentimentDirection = "abs" | "up" | "down";

const ALERT_TYPE_OPTIONS: Array<{ value: AlertType; label: string }> = [
  { value: "signal_threshold", label: "Signal Threshold" },
  { value: "price_target", label: "Price Target" },
  { value: "sentiment_shift", label: "Sentiment Shift" },
  { value: "custom", label: "Custom" },
];

const DELIVERY_OPTIONS: Array<{ value: DeliveryMethod; label: string }> = [
  { value: "websocket", label: "WebSocket" },
  { value: "email", label: "E-Mail" },
  { value: "telegram", label: "Telegram" },
];

function formatDate(value: string | null): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("de-DE");
}

function buildConditionSummary(alert: AlertResponse): string {
  const json = alert.condition_json;
  if (alert.alert_type === "signal_threshold") {
    const threshold = json.threshold ?? "--";
    const direction = json.direction ?? "above";
    return `Staerke ${direction} ${threshold}`;
  }
  if (alert.alert_type === "price_target") {
    const target = json.target_price ?? "--";
    const direction = json.direction ?? "above";
    return `Preis ${direction} ${target}`;
  }
  if (alert.alert_type === "sentiment_shift") {
    const shift = json.shift ?? "--";
    const hours = json.hours ?? "--";
    const direction = json.direction ?? "abs";
    return `Shift ${direction} ${shift} in ${hours}h`;
  }
  return "Custom Expression";
}

function mapWsStatus(status: ReturnType<typeof useWebSocket>["status"]): { text: string; className: string } {
  if (status === "connected") {
    return { text: "Live", className: "bg-green-500/20 text-green-300 border-green-500/40" };
  }
  if (status === "connecting") {
    return { text: "Verbinde...", className: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" };
  }
  if (status === "disconnected") {
    return { text: "Getrennt", className: "bg-orange-500/20 text-orange-300 border-orange-500/40" };
  }
  return { text: "Fehler", className: "bg-red-500/20 text-red-300 border-red-500/40" };
}

export default function AlertsPage() {
  const [assetId, setAssetId] = useState<string>("all");
  const [alertType, setAlertType] = useState<AlertType>("signal_threshold");
  const [deliveryMethod, setDeliveryMethod] = useState<DeliveryMethod>("websocket");
  const [thresholdDirection, setThresholdDirection] = useState<ThresholdDirection>("above");
  const [sentimentDirection, setSentimentDirection] = useState<SentimentDirection>("abs");
  const [threshold, setThreshold] = useState("70");
  const [targetPrice, setTargetPrice] = useState("");
  const [shift, setShift] = useState("0.2");
  const [shiftHours, setShiftHours] = useState("4");
  const [emailTo, setEmailTo] = useState("");
  const [telegramChat, setTelegramChat] = useState("");
  const [customExpression, setCustomExpression] = useState(
    JSON.stringify(
      {
        op: "and",
        conditions: [
          { field: "signal_strength", operator: ">=", value: 75 },
          { field: "signal_type", operator: "==", value: "buy" },
        ],
      },
      null,
      2
    )
  );
  const [isCreating, setIsCreating] = useState(false);

  const { data: assets, isLoading: isAssetsLoading } = useSWR<AssetResponse[]>("/api/assets", fetchJson, {
    refreshInterval: 120000,
  });
  const {
    data: alerts,
    error: alertsError,
    isLoading: isAlertsLoading,
  } = useSWR<AlertResponse[]>("/api/alerts", fetchJson, {
    refreshInterval: 60000,
  });
  const {
    data: history,
    error: historyError,
    isLoading: isHistoryLoading,
  } = useSWR<AlertHistoryResponse[]>("/api/alerts/history?limit=100", fetchJson, {
    refreshInterval: 60000,
  });

  const onAlert = useCallback((event: AlertTriggeredMessage) => {
    const heading = event.symbol ? `Alert ${event.symbol}` : "Alert";
    toast.warning(`${heading}: ${event.message}`);
    void mutate("/api/alerts");
    void mutate("/api/alerts/history?limit=100");
  }, []);

  const websocketUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/prices";
  const { status } = useWebSocket(websocketUrl, { onAlert });
  const statusBadge = mapWsStatus(status);

  const assetOptions = useMemo(() => assets ?? [], [assets]);

  const createAlert = async () => {
    try {
      setIsCreating(true);
      if (assetId === "all" && alertType !== "custom") {
        toast.error("Dieser Alert-Typ benoetigt ein Asset.");
        return;
      }
      const condition: Record<string, unknown> = {};
      if (alertType === "signal_threshold") {
        condition.threshold = Number.parseFloat(threshold);
        condition.direction = thresholdDirection;
      } else if (alertType === "price_target") {
        condition.target_price = Number.parseFloat(targetPrice);
        condition.direction = thresholdDirection;
      } else if (alertType === "sentiment_shift") {
        condition.shift = Number.parseFloat(shift);
        condition.hours = Number.parseInt(shiftHours, 10);
        condition.direction = sentimentDirection;
      } else {
        condition.expression = JSON.parse(customExpression);
      }

      if (deliveryMethod === "email" && emailTo.trim()) {
        condition.email_to = emailTo.trim();
      }
      if (deliveryMethod === "telegram" && telegramChat.trim()) {
        condition.telegram_chat_id = telegramChat.trim();
      }

      const payload = {
        asset_id: assetId === "all" ? null : Number.parseInt(assetId, 10),
        alert_type: alertType,
        condition_json: condition,
        delivery_method: deliveryMethod,
        is_enabled: true,
      };

      const response = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error(`API ${response.status}`);
      }
      toast.success("Alert erstellt.");
      await mutate("/api/alerts");
    } catch {
      toast.error("Alert konnte nicht erstellt werden. JSON/Parameter pruefen.");
    } finally {
      setIsCreating(false);
    }
  };

  const toggleAlert = async (alert: AlertResponse) => {
    const response = await fetch(`/api/alerts/${alert.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_enabled: !alert.is_enabled }),
    });
    if (!response.ok) {
      toast.error("Alert konnte nicht aktualisiert werden.");
      return;
    }
    toast.success(`Alert ${!alert.is_enabled ? "aktiviert" : "deaktiviert"}.`);
    await mutate("/api/alerts");
  };

  const deleteAlert = async (alertId: number) => {
    const response = await fetch(`/api/alerts/${alertId}`, { method: "DELETE" });
    if (!response.ok) {
      toast.error("Alert konnte nicht geloescht werden.");
      return;
    }
    toast.success("Alert geloescht.");
    await mutate("/api/alerts");
    await mutate("/api/alerts/history?limit=100");
  };

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Alerts</h2>
          <p className="text-sm text-muted-foreground">Signal-, Preis- und Sentiment-basierte Benachrichtigungen.</p>
        </div>
        <Badge className={statusBadge.className}>{statusBadge.text}</Badge>
      </header>

      {(alertsError || historyError) && (
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-sm text-red-300">
            Alert-Daten konnten nicht vollstaendig geladen werden.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Alert erstellen</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Asset</label>
            <Select value={assetId} onValueChange={setAssetId}>
              <SelectTrigger>
                <SelectValue placeholder="Asset auswaehlen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Global (kein Asset)</SelectItem>
                {assetOptions.map((asset) => (
                  <SelectItem key={asset.id} value={String(asset.id)}>
                    {asset.symbol}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Alert-Typ</label>
            <Select value={alertType} onValueChange={(value) => setAlertType(value as AlertType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ALERT_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-muted-foreground">Delivery</label>
            <Select value={deliveryMethod} onValueChange={(value) => setDeliveryMethod(value as DeliveryMethod)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DELIVERY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {(alertType === "signal_threshold" || alertType === "price_target") && (
            <>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">
                  {alertType === "signal_threshold" ? "Threshold" : "Target Price"}
                </label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={alertType === "signal_threshold" ? threshold : targetPrice}
                  onChange={(event) =>
                    alertType === "signal_threshold"
                      ? setThreshold(event.target.value)
                      : setTargetPrice(event.target.value)
                  }
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">Richtung</label>
                <Select value={thresholdDirection} onValueChange={(value) => setThresholdDirection(value as ThresholdDirection)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="above">Above</SelectItem>
                    <SelectItem value="below">Below</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {alertType === "sentiment_shift" && (
            <>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">Shift</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={shift}
                  onChange={(event) => setShift(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">Stunden</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={shiftHours}
                  onChange={(event) => setShiftHours(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs text-muted-foreground">Modus</label>
                <Select value={sentimentDirection} onValueChange={(value) => setSentimentDirection(value as SentimentDirection)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="abs">Absolute</SelectItem>
                    <SelectItem value="up">Up</SelectItem>
                    <SelectItem value="down">Down</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {alertType === "custom" && (
            <div className="col-span-1 space-y-2 lg:col-span-3">
              <label className="text-xs text-muted-foreground">Custom Expression (JSON)</label>
              <textarea
                className="min-h-36 w-full rounded-md border border-input bg-background p-3 font-mono text-xs"
                value={customExpression}
                onChange={(event) => setCustomExpression(event.target.value)}
              />
            </div>
          )}

          {deliveryMethod === "email" && (
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">Empfaenger E-Mail (optional)</label>
              <input
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={emailTo}
                onChange={(event) => setEmailTo(event.target.value)}
                placeholder="optional@domain.tld"
              />
            </div>
          )}

          {deliveryMethod === "telegram" && (
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">Telegram Chat-ID (optional)</label>
              <input
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={telegramChat}
                onChange={(event) => setTelegramChat(event.target.value)}
                placeholder="123456789"
              />
            </div>
          )}

          <div className="col-span-1 lg:col-span-3">
            <Button onClick={createAlert} disabled={isCreating || isAssetsLoading}>
              {isCreating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Alert erstellen
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Aktive Alert-Regeln</CardTitle>
        </CardHeader>
        <CardContent>
          {isAlertsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Asset</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Bedingung</TableHead>
                  <TableHead>Delivery</TableHead>
                  <TableHead>Aktiv</TableHead>
                  <TableHead>Last Trigger</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(alerts ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground">
                      Keine Alerts vorhanden.
                    </TableCell>
                  </TableRow>
                ) : (
                  (alerts ?? []).map((alert) => (
                    <TableRow key={alert.id}>
                      <TableCell>{alert.asset_symbol ?? "GLOBAL"}</TableCell>
                      <TableCell>{alert.alert_type}</TableCell>
                      <TableCell>{buildConditionSummary(alert)}</TableCell>
                      <TableCell>{alert.delivery_method}</TableCell>
                      <TableCell>
                        <input
                          type="checkbox"
                          checked={alert.is_enabled}
                          onChange={() => void toggleAlert(alert)}
                        />
                      </TableCell>
                      <TableCell>{formatDate(alert.last_triggered)}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => void deleteAlert(alert.id)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>History Feed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isHistoryLoading ? (
            Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-12 w-full" />)
          ) : (
            (history ?? []).slice(0, 20).map((item) => (
              <div key={item.id} className="rounded-md border border-border bg-muted/20 p-3">
                <div className="mb-1 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Bell className="h-4 w-4 text-primary" />
                    <span className="text-sm font-medium">{item.asset_symbol ?? "GLOBAL"}</span>
                    {item.alert_type && <Badge variant="secondary">{item.alert_type}</Badge>}
                    <Badge variant={item.delivered ? "default" : "destructive"}>
                      {item.delivered ? "zugestellt" : "nicht zugestellt"}
                    </Badge>
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDate(item.created_at)}</span>
                </div>
                <p className="text-sm text-foreground">{item.message}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}
