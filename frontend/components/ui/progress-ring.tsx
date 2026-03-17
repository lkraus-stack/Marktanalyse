"use client";

import { cn } from "@/lib/utils";

interface ProgressRingProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
  trackClassName?: string;
  progressClassName?: string;
  labelClassName?: string;
  suffix?: string;
}

export function ProgressRing({
  value,
  max = 100,
  size = 62,
  strokeWidth = 7,
  className,
  trackClassName,
  progressClassName,
  labelClassName,
  suffix = "",
}: ProgressRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const normalized = Math.max(0, Math.min(1, value / max));
  const offset = circumference * (1 - normalized);

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          className={cn("text-slate-800", trackClassName)}
          stroke="currentColor"
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn("text-blue-400 transition-all duration-300", progressClassName)}
          stroke="currentColor"
          fill="none"
        />
      </svg>
      <span className={cn("absolute text-xs font-semibold text-slate-100", labelClassName)}>
        {Math.round(value)}
        {suffix}
      </span>
    </div>
  );
}
