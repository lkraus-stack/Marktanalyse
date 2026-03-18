import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const rawBackendUrl = process.env.BACKEND_URL?.trim();
    const fallbackUrl = "http://localhost:8000";

    let backendUrl = rawBackendUrl || fallbackUrl;
    try {
      const parsed = new URL(backendUrl);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        throw new Error(`Unsupported protocol: ${parsed.protocol}`);
      }
      parsed.pathname = "";
      parsed.search = "";
      parsed.hash = "";
      backendUrl = parsed.toString().replace(/\/$/, "");
    } catch {
      console.warn(
        `[next.config] Ignoring invalid BACKEND_URL "${rawBackendUrl}". No /api rewrite will be configured.`
      );
      return [];
    }

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
