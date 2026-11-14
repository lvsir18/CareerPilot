import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the production Docker image small.
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Same-origin API proxy. The browser only ever talks to :3000, so opening the
  // app from a phone on the LAN works without rebuilding for a different IP and
  // without CORS. It also fixes SSE, which used a relative path and used to 404.
  async rewrites() {
    const target =
      process.env.API_INTERNAL_URL ??
      (process.env.NODE_ENV === "production" ? "http://api:8000" : "http://localhost:8000");
    return [{ source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` }];
  },
};

export default nextConfig;