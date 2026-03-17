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
import { cn } from "@/lib/utils";

interface PriceChartProps {
  data: PricePointResponse[] | undefined;
  isLoading: boolean;
  heightClassName?: string;
  className?: string;
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

export function PriceChart({ data, isLoading, heightClassName, className }: PriceChartProps) {
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

    const initialWidth = containerRef.current.clientWidth || 800;
    const initialHeight = containerRef.current.clientHeight || 420;

    const chart = createChart(containerRef.current, {
      width: initialWidth,
      height: initialHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#0a0a14" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e1e3a88" },
        horzLines: { color: "#1e1e3a88" },
      },
      rightPriceScale: {
        borderColor: "#1e1e3a",
      },
      timeScale: {
        borderColor: "#1e1e3a",
        timeVisible: true,
      },
      crosshair: {
        vertLine: { color: "#64748b88" },
        horzLine: { color: "#64748b88" },
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
    return <ChartSkeleton className={cn("h-[420px]", heightClassName, className)} />;
  }

  if (!data || data.length === 0) {
    return (
      <div
        className={cn(
          "flex h-[420px] items-center justify-center rounded-xl border border-border/70 bg-[#0a0a14] text-sm text-muted-foreground",
          heightClassName,
          className
        )}
      >
        Keine Kursdaten verfuegbar.
      </div>
    );
  }

  return <div ref={containerRef} className={cn("h-[420px] w-full rounded-xl", heightClassName, className)} />;
}

function ChartSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative w-full overflow-hidden rounded-xl border border-border/70 bg-[#0a0a14]", className)}>
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(30,30,58,0.2)_1px,transparent_1px),linear-gradient(180deg,rgba(30,30,58,0.2)_1px,transparent_1px)] bg-[size:28px_28px]" />
      <div className="absolute inset-x-0 bottom-0 h-[22%] bg-gradient-to-t from-blue-500/10 to-transparent" />
      <div className="absolute left-0 right-0 top-[42%] h-px border-t border-dashed border-slate-600/50" />
      <div className="absolute inset-0 px-6 py-8">
        <Skeleton className="h-full w-full rounded-[10px] bg-transparent" />
        <svg viewBox="0 0 100 30" className="absolute inset-x-6 top-1/2 h-24 -translate-y-1/2 text-slate-500/70">
          <path
            d="M0 23 L10 16 L18 18 L28 10 L35 14 L45 8 L57 12 L67 7 L76 11 L86 6 L100 9"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
}
