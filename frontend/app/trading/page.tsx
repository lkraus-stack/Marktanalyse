"use client";

import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { AlertTriangle, Loader2, Play, ShieldCheck, Wallet } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import { apiHeaders, fetchJson, formatCurrency, formatPercent, parseNumeric } from "@/lib/api";
import type {
  AssetResponse,
  PortfolioSnapshotResponse,
  TradeSide,
  TradingAccountResponse,
  TradingOrderResponse,
  TradingPerformanceResponse,
  TradingPositionResponse,
  TradingSettingsResponse,
  TradingStatusResponse,
} from "@/lib/types";

function formatDateTime(value: string | null): string {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("de-DE");
}

function orderStatusBadge(status: TradingOrderResponse["status"]): "default" | "secondary" | "destructive" {
  if (status === "filled" || status === "submitted") {
    return "default";
  }
  if (status === "pending_confirmation") {
    return "secondary";
  }
  return "destructive";
}

export default function TradingPage() {
  const [symbol, setSymbol] = useState<string>("");
  const [qty, setQty] = useState<string>("1");
  const [side, setSide] = useState<TradeSide>("buy");
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isTriggeringCycle, setIsTriggeringCycle] = useState(false);

  const { data: assets } = useSWR<AssetResponse[]>("/api/assets", fetchJson, { refreshInterval: 120000 });
  const { data: account, error: accountError, isLoading: isAccountLoading } = useSWR<TradingAccountResponse>(
    "/api/trading/account",
    fetchJson,
    { refreshInterval: 30000 }
  );
  const { data: positions, isLoading: isPositionsLoading } = useSWR<TradingPositionResponse[]>(
    "/api/trading/positions",
    fetchJson,
    { refreshInterval: 30000 }
  );
  const { data: orders, isLoading: isOrdersLoading } = useSWR<TradingOrderResponse[]>(
    "/api/trading/orders?limit=100",
    fetchJson,
    { refreshInterval: 30000 }
  );
  const { data: snapshots, isLoading: isSnapshotsLoading } = useSWR<PortfolioSnapshotResponse[]>(
    "/api/trading/portfolio/history?limit=168",
    fetchJson,
    { refreshInterval: 60000 }
  );
  const { data: performance } = useSWR<TradingPerformanceResponse>("/api/trading/performance", fetchJson, {
    refreshInterval: 60000,
  });
  const { data: settings, isLoading: isSettingsLoading } = useSWR<TradingSettingsResponse>(
    "/api/trading/settings",
    fetchJson,
    { refreshInterval: 120000 }
  );
  const { data: tradingStatus } = useSWR<TradingStatusResponse>("/api/trading/status", fetchJson, {
    refreshInterval: 15000,
  });

  const [settingsDraft, setSettingsDraft] = useState<TradingSettingsResponse | null>(null);
  const effectiveSettings = settingsDraft ?? settings ?? null;
  const isLive = Boolean(effectiveSettings?.is_live ?? tradingStatus?.is_live ?? account?.is_live);
  const bannerClass = isLive ? "border-red-500/60 bg-red-500/10" : "border-green-500/60 bg-green-500/10";
  const bannerIconClass = isLive ? "text-red-400" : "text-green-400";
  const bannerTitleClass = isLive ? "text-red-300" : "text-green-300";
  const bannerSubtitleClass = isLive ? "text-red-200/90" : "text-green-200/90";

  const chartData = useMemo(() => {
    return (snapshots ?? []).map((item) => ({
      time: new Date(item.snapshot_at).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" }),
      total: item.total_value,
      cash: item.cash,
      positions: item.positions_value,
    }));
  }, [snapshots]);

  const selectedSymbol = symbol || assets?.[0]?.symbol || "";

  const refreshTradingData = async () => {
    await Promise.all([
      mutate("/api/trading/account"),
      mutate("/api/trading/positions"),
      mutate("/api/trading/orders?limit=100"),
      mutate("/api/trading/portfolio/history?limit=168"),
      mutate("/api/trading/performance"),
    ]);
  };

  const submitQuickOrder = async () => {
    if (!selectedSymbol) {
      toast.error("Bitte zuerst ein Asset waehlen.");
      return;
    }
    const parsedQty = Number.parseFloat(qty);
    if (!Number.isFinite(parsedQty) || parsedQty <= 0) {
      toast.error("Menge muss groesser als 0 sein.");
      return;
    }
    setIsSubmittingOrder(true);
    try {
      const response = await fetch("/api/trading/orders", {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({
          symbol: selectedSymbol,
          qty: parsedQty,
          side,
          order_type: "market",
          time_in_force: "day",
          notes: "quick_trade_ui",
        }),
      });
      if (!response.ok) {
        throw new Error("create order failed");
      }
      toast.success("Paper-Order eingereicht.");
      await refreshTradingData();
    } catch {
      toast.error("Order konnte nicht eingereicht werden.");
    } finally {
      setIsSubmittingOrder(false);
    }
  };

  const confirmOrder = async (orderId: number) => {
    try {
      const response = await fetch(`/api/trading/orders/${orderId}/confirm`, {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        throw new Error("confirm failed");
      }
      toast.success("Order bestaetigt.");
      await refreshTradingData();
    } catch {
      toast.error("Order-Bestaetigung fehlgeschlagen.");
    }
  };

  const cancelOrder = async (orderId: number) => {
    try {
      const response = await fetch(`/api/trading/orders/${orderId}`, { method: "DELETE" });
      if (!response.ok) {
        throw new Error("cancel failed");
      }
      toast.success("Order storniert.");
      await refreshTradingData();
    } catch {
      toast.error("Order konnte nicht storniert werden.");
    }
  };

  const saveSettings = async () => {
    if (!effectiveSettings) {
      return;
    }
    setIsSavingSettings(true);
    try {
      const response = await fetch("/api/trading/settings", {
        method: "PATCH",
        headers: apiHeaders(true),
        body: JSON.stringify(effectiveSettings),
      });
      if (!response.ok) {
        throw new Error("settings failed");
      }
      toast.success("AutoTrader-Settings gespeichert.");
      setSettingsDraft(null);
      await mutate("/api/trading/settings");
    } catch {
      toast.error("Settings konnten nicht gespeichert werden.");
    } finally {
      setIsSavingSettings(false);
    }
  };

  const runCycle = async (type: "evaluate" | "exits" | "snapshot") => {
    setIsTriggeringCycle(true);
    try {
      const response = await fetch(`/api/trading/run/${type}`, { method: "POST" });
      if (!response.ok) {
        throw new Error("cycle failed");
      }
      toast.success("Trading-Zyklus gestartet.");
      await refreshTradingData();
    } catch {
      toast.error("Trading-Zyklus fehlgeschlagen.");
    } finally {
      setIsTriggeringCycle(false);
    }
  };

  return (
    <section className="space-y-6">
      <Card className={bannerClass}>
        <CardContent className="flex items-center gap-3 py-4">
          <AlertTriangle className={`h-5 w-5 ${bannerIconClass}`} />
          <div>
            <p className={`text-lg font-semibold ${bannerTitleClass}`}>{isLive ? "LIVE TRADING" : "PAPER TRADING"}</p>
            <p className={`text-sm ${bannerSubtitleClass}`}>
              {isLive
                ? "Echtgeld-Modus aktiv - pruefe Risiko- und Sicherheitsregeln vor jedem Trade."
                : "Simulation only - kein echtes Geld wird eingesetzt."}
            </p>
          </div>
        </CardContent>
      </Card>

      {accountError && (
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-sm text-red-300">
            Trading-Account konnte nicht geladen werden (Alpaca Credentials pruefen).
          </CardContent>
        </Card>
      )}
      {tradingStatus?.live_stop_reason && (
        <Card className="border-red-500/40">
          <CardContent className="pt-6 text-sm text-red-300">
            Live-Trading gestoppt: {tradingStatus.live_stop_reason}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {isAccountLoading ? (
          <>
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </>
        ) : (
          <>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Equity</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{formatCurrency(account?.equity ?? 0)}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Cash</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{formatCurrency(account?.cash ?? 0)}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Buying Power</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">
                {formatCurrency(account?.buying_power ?? 0)}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Tages-PnL</CardTitle>
              </CardHeader>
              <CardContent
                className={`text-2xl font-semibold ${(performance?.daily_pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"}`}
              >
                {formatCurrency(performance?.daily_pnl ?? 0)}
              </CardContent>
            </Card>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Eigenkapital-Kurve</CardTitle>
          </CardHeader>
          <CardContent>
            {isSnapshotsLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid stroke="#33415544" strokeDasharray="4 4" />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="total" name="Total" stroke="#3b82f6" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="cash" name="Cash" stroke="#22c55e" strokeWidth={2} dot={false} />
                    <Line
                      type="monotone"
                      dataKey="positions"
                      name="Positionen"
                      stroke="#a855f7"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wallet className="h-4 w-4 text-primary" />
              Schnellhandel
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Asset</label>
              <Select value={selectedSymbol} onValueChange={setSymbol}>
                <SelectTrigger>
                  <SelectValue placeholder="Asset waehlen" />
                </SelectTrigger>
                <SelectContent>
                  {(assets ?? []).map((item) => (
                    <SelectItem key={item.symbol} value={item.symbol}>
                      {item.symbol}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Side</label>
              <Select value={side} onValueChange={(value) => setSide(value as TradeSide)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="buy">BUY</SelectItem>
                  <SelectItem value="sell">SELL</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Menge</label>
              <input
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={qty}
                onChange={(event) => setQty(event.target.value)}
              />
            </div>
            <Button className="w-full" onClick={submitQuickOrder} disabled={isSubmittingOrder}>
              {isSubmittingOrder && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isLive ? "Live-Order senden" : "Paper-Order senden"}
            </Button>
            <div className="grid grid-cols-3 gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void runCycle("evaluate")}
                disabled={isTriggeringCycle}
              >
                <Play className="mr-1 h-3.5 w-3.5" />
                Buy
              </Button>
              <Button variant="outline" size="sm" onClick={() => void runCycle("exits")} disabled={isTriggeringCycle}>
                Exits
              </Button>
              <Button variant="outline" size="sm" onClick={() => void runCycle("snapshot")} disabled={isTriggeringCycle}>
                Snapshot
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            AutoTrader Settings
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isSettingsLoading || !effectiveSettings ? (
            <Skeleton className="h-36 w-full" />
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Modus</label>
                <Select
                  value={effectiveSettings.mode}
                  onValueChange={(value) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      mode: value as TradingSettingsResponse["mode"],
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">manual</SelectItem>
                    <SelectItem value="semi_auto">semi_auto</SelectItem>
                    <SelectItem value="auto">auto</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Execution</label>
                <div className="h-10 rounded-md border border-input bg-background px-3 text-sm leading-10">
                  {effectiveSettings.is_live ? "live" : "paper"}
                </div>
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Position ($)</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.max_position_size_usd}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      max_position_size_usd: Number.parseFloat(event.target.value) || 0,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Positionen</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.max_positions}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      max_positions: Number.parseInt(event.target.value, 10) || 1,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Min Signal-Staerke</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.min_signal_strength}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      min_signal_strength: Number.parseFloat(event.target.value) || 0,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Stop Loss %</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.stop_loss_pct}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      stop_loss_pct: Number.parseFloat(event.target.value) || 0.1,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Take Profit %</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.take_profit_pct}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      take_profit_pct: Number.parseFloat(event.target.value) || 0.1,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Double Confirm ab EUR</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.double_confirm_threshold_eur}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      double_confirm_threshold_eur: Number.parseFloat(event.target.value) || 1,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Daily Loss Limit EUR</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.daily_loss_limit_eur}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      daily_loss_limit_eur: Number.parseFloat(event.target.value) || 1,
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-muted-foreground">Max Trades/Tag</label>
                <input
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={effectiveSettings.max_trades_per_day}
                  onChange={(event) =>
                    setSettingsDraft({
                      ...effectiveSettings,
                      max_trades_per_day: Number.parseInt(event.target.value, 10) || 1,
                    })
                  }
                />
              </div>
              <div className="md:col-span-3">
                <Button onClick={saveSettings} disabled={isSavingSettings}>
                  {isSavingSettings && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Settings speichern
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Positionen</CardTitle>
        </CardHeader>
        <CardContent>
          {isPositionsLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Qty</TableHead>
                  <TableHead>Entry</TableHead>
                  <TableHead>Aktuell</TableHead>
                  <TableHead>Market Value</TableHead>
                  <TableHead>Unrealized</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(positions ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      Keine offenen Positionen.
                    </TableCell>
                  </TableRow>
                ) : (
                  (positions ?? []).map((row) => (
                    <TableRow key={row.symbol}>
                      <TableCell>{row.symbol}</TableCell>
                      <TableCell>{row.qty.toFixed(4)}</TableCell>
                      <TableCell>{formatCurrency(row.avg_entry_price)}</TableCell>
                      <TableCell>{formatCurrency(row.current_price)}</TableCell>
                      <TableCell>{formatCurrency(row.market_value)}</TableCell>
                      <TableCell className={row.unrealized_pl >= 0 ? "text-green-400" : "text-red-400"}>
                        {formatCurrency(row.unrealized_pl)} ({formatPercent(row.unrealized_plpc * 100)})
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
          <CardTitle>Orders</CardTitle>
        </CardHeader>
        <CardContent>
          {isOrdersLoading ? (
            <Skeleton className="h-28 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Menge</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Wert</TableHead>
                  <TableHead>Zeit</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(orders ?? []).length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center text-muted-foreground">
                      Keine Orders vorhanden.
                    </TableCell>
                  </TableRow>
                ) : (
                  (orders ?? []).map((order) => (
                    <TableRow key={order.id}>
                      <TableCell>{order.id}</TableCell>
                      <TableCell>{order.symbol ?? `asset:${order.asset_id ?? "--"}`}</TableCell>
                      <TableCell>{order.side.toUpperCase()}</TableCell>
                      <TableCell>{(parseNumeric(order.quantity) ?? 0).toFixed(4)}</TableCell>
                      <TableCell>
                        <Badge variant={orderStatusBadge(order.status)}>{order.status}</Badge>
                      </TableCell>
                      <TableCell>{formatCurrency(parseNumeric(order.total_value) ?? 0)}</TableCell>
                      <TableCell>{formatDateTime(order.created_at)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          {order.status === "pending_confirmation" && (
                            <Button size="sm" variant="outline" onClick={() => void confirmOrder(order.id)}>
                              Confirm
                            </Button>
                          )}
                          {(order.status === "submitted" || order.status === "pending_confirmation") && (
                            <Button size="sm" variant="ghost" onClick={() => void cancelOrder(order.id)}>
                              Cancel
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
