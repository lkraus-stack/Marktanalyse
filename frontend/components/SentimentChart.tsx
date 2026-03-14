"use client";

import { format, parseISO } from "date-fns";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Skeleton } from "@/components/ui/skeleton";
import type { SentimentHistoryResponse } from "@/lib/types";

interface SentimentChartProps {
  data: SentimentHistoryResponse[] | undefined;
  isLoading: boolean;
}

interface SentimentChartDatum {
  label: string;
  scorePositive: number;
  scoreNegative: number;
  mentions: number;
}

export function SentimentChart({ data, isLoading }: SentimentChartProps) {
  if (isLoading) {
    return <Skeleton className="h-56 w-full rounded-lg" />;
  }

  if (!data || data.length === 0) {
    return (
      <div className="flex h-56 items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
        Keine historischen Sentiment-Daten verfuegbar.
      </div>
    );
  }

  const chartData: SentimentChartDatum[] = [...data]
    .sort((a, b) => new Date(a.period_start).getTime() - new Date(b.period_start).getTime())
    .map((item) => ({
      label: format(parseISO(item.period_start), "dd.MM HH:mm"),
      scorePositive: item.score > 0 ? item.score : 0,
      scoreNegative: item.score < 0 ? item.score : 0,
      mentions: item.total_mentions,
    }));

  return (
    <div className="h-56 w-full rounded-lg bg-card p-2">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData}>
          <defs>
            <linearGradient id="positiveFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.7} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0.05} />
            </linearGradient>
            <linearGradient id="negativeFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity={0.05} />
              <stop offset="100%" stopColor="#ef4444" stopOpacity={0.7} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#33415544" strokeDasharray="4 4" />
          <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 11 }} minTickGap={24} />
          <YAxis yAxisId="score" domain={[-1, 1]} tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <YAxis yAxisId="mentions" orientation="right" tick={{ fill: "#94a3b8", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#161b31", border: "1px solid #334155", borderRadius: "8px" }}
            labelStyle={{ color: "#e2e8f0" }}
          />
          <ReferenceLine yAxisId="score" y={0} stroke="#64748b" strokeDasharray="3 3" />
          <Bar yAxisId="mentions" dataKey="mentions" fill="#3b82f680" radius={[4, 4, 0, 0]} barSize={10} />
          <Area
            yAxisId="score"
            type="monotone"
            dataKey="scorePositive"
            stroke="#22c55e"
            fill="url(#positiveFill)"
            strokeWidth={2}
            dot={false}
          />
          <Area
            yAxisId="score"
            type="monotone"
            dataKey="scoreNegative"
            stroke="#ef4444"
            fill="url(#negativeFill)"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
