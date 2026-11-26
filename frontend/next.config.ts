import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Protected routes gate children behind client-only sessionStorage AuthGate (ADR-006),
  // which intentionally omits children during SSR prerender; opt into instant validation per-segment instead.
  experimental: {
    instantInsights: {
      validationLevel: "manual-warning",
    },
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
