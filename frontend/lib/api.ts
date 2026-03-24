export async function fetchJson<T>(url: string): Promise<T> {
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
  });

  if (!response.ok) {
    throw new Error(`API request failed (${response.status}): ${url}`);
  }

  return (await response.json()) as T;
}

export function apiHeaders(includeJsonContentType: boolean = false): HeadersInit {
  const headers: Record<string, string> = {};
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  return headers;
}

export function resolveWebSocketUrl(explicitUrl?: string): string | null {
  const trimmedUrl = explicitUrl?.trim();
  if (trimmedUrl) {
    return trimmedUrl;
  }
  if (typeof window === "undefined") {
    return "ws://localhost:8000/ws/prices";
  }
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return `ws://${window.location.hostname}:8000/ws/prices`;
  }
  return null;
}

export function parseNumeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

export function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("de-DE", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatCurrency(value: number | null): string {
  if (value === null) {
    return "--";
  }
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 1000 ? 0 : 2,
  }).format(value);
}

export function formatPercent(value: number | null): string {
  if (value === null) {
    return "--";
  }
  return `${value.toFixed(2)}%`;
}
