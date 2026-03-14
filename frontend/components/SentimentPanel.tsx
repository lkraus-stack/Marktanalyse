"use client";

import useSWR from "swr";
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchJson } from "@/lib/api";
import type { SentimentOverviewResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SentimentPanelProps {
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
}

function clampScore(score: number): number {
  return Math.max(-1, Math.min(1, score));
}

function TrendIcon({ score }: { score: number }) {
  if (score > 0.1) {
    return <ArrowUpRight className="h-4 w-4 text-green-400" />;
  }
  if (score < -0.1) {
    return <ArrowDownRight className="h-4 w-4 text-red-400" />;
  }
  return <ArrowRight className="h-4 w-4 text-yellow-300" />;
}

export function SentimentPanel({ selectedSymbol, onSelectSymbol }: SentimentPanelProps) {
  const {
    data: overview,
    error,
    isLoading,
  } = useSWR<SentimentOverviewResponse[]>("/api/sentiment/overview", fetchJson, {
    refreshInterval: 60000,
    revalidateOnFocus: true,
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-red-400">Sentiment-Daten konnten nicht geladen werden.</p>;
  }

  if (!overview || overview.length === 0) {
    return <p className="text-sm text-muted-foreground">Keine Sentiment-Daten verfuegbar.</p>;
  }

  return (
    <div className="space-y-2">
      {overview.map((item) => {
        const score = clampScore(item.score ?? 0);
        const markerPosition = ((score + 1) / 2) * 100;

        return (
          <button
            key={item.symbol}
            type="button"
            onClick={() => onSelectSymbol(item.symbol)}
            className={cn(
              "w-full rounded-md border border-border bg-card p-3 text-left transition hover:border-primary/60 hover:bg-muted/50",
              selectedSymbol === item.symbol && "border-primary"
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="font-medium text-foreground">{item.symbol}</span>
              <div className="flex items-center gap-2">
                <TrendIcon score={score} />
                <Badge variant="secondary">{item.mentions_1h} Erw.</Badge>
              </div>
            </div>
            <div className="relative h-2 rounded-full bg-gradient-to-r from-red-500 via-yellow-400 to-green-500">
              <span
                className="absolute top-1/2 block h-4 w-1 -translate-y-1/2 rounded bg-white shadow"
                style={{ left: `calc(${markerPosition}% - 2px)` }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}
