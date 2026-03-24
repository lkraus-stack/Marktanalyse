import type { NextConfig } from "next";

const FALLBACK_BACKEND_URL = "http://localhost:8000";

function normalizeBackendUrl(rawValue?: string): string {
  const trimmedValue = rawValue?.trim();
  const candidate = trimmedValue || FALLBACK_BACKEND_URL;

  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      throw new Error(`Unsupported protocol: ${parsed.protocol}`);
    }
    parsed.pathname = "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    console.warn(
      `[next.config] Invalid BACKEND_URL "${trimmedValue}". Falling back to ${FALLBACK_BACKEND_URL}.`
    );
    return FALLBACK_BACKEND_URL;
  }
}

const backendUrl = normalizeBackendUrl(process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL);

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
