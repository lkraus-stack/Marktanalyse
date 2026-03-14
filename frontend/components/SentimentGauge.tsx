"use client";

import { cn } from "@/lib/utils";

interface SentimentGaugeProps {
  score: number;
  className?: string;
}

function clampScore(value: number): number {
  return Math.max(-1, Math.min(1, value));
}

function getLabel(score: number): string {
  if (score > 0.3) {
    return "Bullish";
  }
  if (score < -0.3) {
    return "Bearish";
  }
  return "Neutral";
}

export function SentimentGauge({ score, className }: SentimentGaugeProps) {
  const clamped = clampScore(score);
  const normalized = (clamped + 1) / 2;
  const radius = 54;
  const circumference = Math.PI * radius;
  const dash = circumference * normalized;

  return (
    <div className={cn("relative flex h-36 w-full items-center justify-center", className)}>
      <svg viewBox="0 0 140 84" className="h-full w-full">
        <defs>
          <linearGradient id="sentimentGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#ef4444" />
            <stop offset="50%" stopColor="#facc15" />
            <stop offset="100%" stopColor="#22c55e" />
          </linearGradient>
        </defs>
        <path
          d="M 16 70 A 54 54 0 0 1 124 70"
          fill="none"
          stroke="#334155"
          strokeWidth="12"
          strokeLinecap="round"
        />
        <path
          d="M 16 70 A 54 54 0 0 1 124 70"
          fill="none"
          stroke="url(#sentimentGradient)"
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
        />
      </svg>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center pt-6">
        <span className="text-2xl font-semibold text-foreground">{clamped.toFixed(2)}</span>
        <span className="text-xs uppercase tracking-wider text-muted-foreground">{getLabel(clamped)}</span>
      </div>
    </div>
  );
}
