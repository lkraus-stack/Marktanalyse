"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

interface MiniSparklineProps {
  values: number[] | undefined;
  className?: string;
  strokeClassName?: string;
  width?: number;
  height?: number;
  showArea?: boolean;
}

function toPath(values: number[], width: number, height: number): string {
  if (values.length === 1) {
    return `M 0 ${height / 2} L ${width} ${height / 2}`;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, Number.EPSILON);

  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export function MiniSparkline({
  values,
  className,
  strokeClassName,
  width = 60,
  height = 20,
  showArea = false,
}: MiniSparklineProps) {
  const gradientId = useId();
  const source = values?.filter((value) => Number.isFinite(value)) ?? [];
  const path = source.length > 0 ? toPath(source, width, height) : `M 0 ${height / 2} L ${width} ${height / 2}`;
  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn("overflow-visible", className)}
      role="img"
      aria-label="Trendverlauf"
    >
      {showArea && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity={0.35} />
            <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
          </linearGradient>
        </defs>
      )}

      {showArea && <path d={areaPath} fill={`url(#${gradientId})`} className={cn("text-blue-400/20", strokeClassName)} />}
      <path
        d={path}
        fill="none"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={cn("text-blue-400", strokeClassName)}
        stroke="currentColor"
      />
    </svg>
  );
}
