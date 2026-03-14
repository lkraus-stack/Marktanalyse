"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import { Skeleton } from "@/components/ui/skeleton";
import { parseNumeric } from "@/lib/api";
import type { PricePointResponse } from "@/lib/types";

interface PriceChartProps {
  data: PricePointResponse[] | undefined;
  isLoading: boolean;
}

interface CandlestickPoint {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface VolumePoint {
  time: UTCTimestamp;
  value: number;
  color: string;
}

function toUnixTimestamp(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

export function PriceChart({ data, isLoading }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const transformed = useMemo(() => {
    const sorted = [...(data ?? [])].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );

    const candles: CandlestickPoint[] = [];
    const volume: VolumePoint[] = [];

    sorted.forEach((point) => {
      const open = parseNumeric(point.open);
      const high = parseNumeric(point.high);
      const low = parseNumeric(point.low);
      const close = parseNumeric(point.close);
      const volumeValue = parseNumeric(point.volume);

      if (open === null || high === null || low === null || close === null || volumeValue === null) {
        return;
      }

      const time = toUnixTimestamp(point.timestamp);
      candles.push({ time, open, high, low, close });
      volume.push({
        time,
        value: volumeValue,
        color: close >= open ? "#22c55e66" : "#ef444466",
      });
    });

    return { candles, volume };
  }, [data]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#1a1a2e" },
        textColor: "#cbd5e1",
      },
      grid: {
        vertLines: { color: "#1f2a44" },
        horzLines: { color: "#1f2a44" },
      },
      rightPriceScale: {
        borderColor: "#2a385b",
      },
      timeScale: {
        borderColor: "#2a385b",
        timeVisible: true,
      },
      crosshair: {
        vertLine: { color: "#334155" },
        horzLine: { color: "#334155" },
      },
      localization: {
        locale: "de-DE",
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      priceLineVisible: true,
    });

    const volume = chart.addSeries(HistogramSeries, {
      color: "#60a5fa80",
      priceScaleId: "",
      priceFormat: {
        type: "volume",
      },
    });

    volume.priceScale().applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry || !chartRef.current) {
        return;
      }
      chartRef.current.applyOptions({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });

    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !chartRef.current) {
      return;
    }

    candleSeriesRef.current.setData(transformed.candles);
    volumeSeriesRef.current.setData(transformed.volume);
    chartRef.current.timeScale().fitContent();
  }, [transformed]);

  if (isLoading) {
    return <Skeleton className="h-[420px] w-full rounded-lg" />;
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-[420px] items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
        Keine Kursdaten verfuegbar.
      </div>
    );
  }

  return <div ref={containerRef} className="h-[420px] w-full rounded-lg" />;
}
