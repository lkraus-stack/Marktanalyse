"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type HealthResponse = {
  status: string;
  version: string;
};

type ConnectionState = "loading" | "connected" | "error";

export function HealthStatus() {
  const [connectionState, setConnectionState] = useState<ConnectionState>("loading");
  const [version, setVersion] = useState<string>("-");
  const [errorMessage, setErrorMessage] = useState<string>("");

  const fetchHealth = useCallback(async () => {
    setConnectionState("loading");
    setErrorMessage("");

    try {
      const response = await fetch("/api/health", {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Health-Check fehlgeschlagen mit HTTP ${response.status}.`);
      }

      const payload = (await response.json()) as HealthResponse;
      if (payload.status !== "ok") {
        throw new Error("Backend meldet keinen OK-Status.");
      }

      setVersion(payload.version);
      setConnectionState("connected");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unbekannter Fehler.";
      setErrorMessage(message);
      setConnectionState("error");
    }
  }, []);

  useEffect(() => {
    void fetchHealth();
  }, [fetchHealth]);

  const indicatorClass =
    connectionState === "connected"
      ? "bg-emerald-500"
      : connectionState === "error"
        ? "bg-red-500"
        : "bg-amber-400";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Backend-Verbindung</CardTitle>
        <CardDescription>Prueft den FastAPI Health-Endpoint unter `/api/health`.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <span className={`inline-block h-3 w-3 rounded-full ${indicatorClass}`} />
          <p className="text-sm font-medium text-slate-700">
            {connectionState === "connected" && "Verbunden"}
            {connectionState === "error" && "Fehler"}
            {connectionState === "loading" && "Wird geprueft"}
          </p>
        </div>

        <div className="space-y-1 text-sm text-slate-600">
          <p>
            <span className="font-medium text-slate-800">Backend-Version:</span> {version}
          </p>
          {errorMessage ? (
            <p>
              <span className="font-medium text-slate-800">Fehlermeldung:</span> {errorMessage}
            </p>
          ) : null}
        </div>

        <Button variant="outline" size="sm" onClick={() => void fetchHealth()}>
          Erneut pruefen
        </Button>
      </CardContent>
    </Card>
  );
}
