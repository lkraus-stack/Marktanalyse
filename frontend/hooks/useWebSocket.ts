"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { mutate } from "swr";

import type {
  AlertTriggeredMessage,
  AssetResponse,
  PricePointResponse,
  PriceUpdateMessage,
  WebSocketStatus,
} from "@/lib/types";

const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000, 16000, 30000];

function isPriceUpdateMessage(payload: unknown): payload is PriceUpdateMessage {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return (
    candidate.type === "price_update" &&
    typeof candidate.symbol === "string" &&
    typeof candidate.timestamp === "string" &&
    typeof candidate.close === "number"
  );
}

function isAlertTriggeredMessage(payload: unknown): payload is AlertTriggeredMessage {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Record<string, unknown>;
  return candidate.type === "alert_triggered" && candidate.channel === "alerts" && typeof candidate.message === "string";
}

interface UseWebSocketOptions {
  onAlert?: (alert: AlertTriggeredMessage) => void;
}

export function useWebSocket(
  url: string = "ws://localhost:8000/ws/prices",
  options?: UseWebSocketOptions
): { status: WebSocketStatus } {
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectStepRef = useRef(0);
  const shouldReconnectRef = useRef(true);
  const onAlertRef = useRef<UseWebSocketOptions["onAlert"]>(options?.onAlert);

  const [status, setStatus] = useState<WebSocketStatus>("connecting");

  useEffect(() => {
    onAlertRef.current = options?.onAlert;
  }, [options?.onAlert]);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const updateCaches = useCallback((message: PriceUpdateMessage) => {
    void mutate(
      "/api/assets",
      (current: AssetResponse[] | undefined) => {
        if (!current) {
          return current;
        }
        return current.map((asset) =>
          asset.symbol === message.symbol
            ? {
                ...asset,
                latest_close: message.close,
                latest_timestamp: message.timestamp,
                latest_source: message.source,
              }
            : asset
        );
      },
      { revalidate: false }
    );

    void mutate(
      `/api/prices/${message.symbol}`,
      (current: PricePointResponse | undefined) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          symbol: message.symbol,
          source: message.source,
          timeframe: message.timeframe,
          timestamp: message.timestamp,
          open: message.open,
          high: message.high,
          low: message.low,
          close: message.close,
          volume: message.volume,
        };
      },
      { revalidate: false }
    );

    void mutate(
      (key: unknown) => typeof key === "string" && key.startsWith(`/api/prices/${message.symbol}/history`),
      (current: PricePointResponse[] | undefined) => {
        if (!current || current.length === 0) {
          return current;
        }
        const point: PricePointResponse = {
          symbol: message.symbol,
          source: message.source,
          timeframe: message.timeframe,
          timestamp: message.timestamp,
          open: message.open,
          high: message.high,
          low: message.low,
          close: message.close,
          volume: message.volume,
        };
        const last = current[current.length - 1];
        if (last && last.timestamp === message.timestamp) {
          return [...current.slice(0, -1), point];
        }
        return [...current, point].slice(-1000);
      },
      { revalidate: false }
    );
  }, []);

  const connect = useCallback(() => {
    if (!shouldReconnectRef.current) {
      return;
    }

    clearReconnectTimer();
    setStatus("connecting");

    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => {
      reconnectStepRef.current = 0;
      setStatus("connected");
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const parsed: unknown = JSON.parse(event.data);
        if (isPriceUpdateMessage(parsed)) {
          updateCaches(parsed);
          return;
        }
        if (isAlertTriggeredMessage(parsed)) {
          onAlertRef.current?.(parsed);
        }
      } catch {
        setStatus("error");
      }
    };

    socket.onerror = () => {
      setStatus("error");
    };

    socket.onclose = () => {
      if (!shouldReconnectRef.current) {
        return;
      }
      setStatus("disconnected");
      const step = Math.min(reconnectStepRef.current, BACKOFF_STEPS_MS.length - 1);
      const delay = BACKOFF_STEPS_MS[step];
      reconnectStepRef.current = Math.min(step + 1, BACKOFF_STEPS_MS.length - 1);

      reconnectTimerRef.current = window.setTimeout(() => {
        connect();
      }, delay);
    };
  }, [clearReconnectTimer, updateCaches, url]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [clearReconnectTimer, connect]);

  return { status };
}
