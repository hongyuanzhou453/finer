import type { NextConfig } from "next";

/**
 * Standalone marketing site for Finer OS.
 *
 * Pure static export — NO backend, NO /api rewrites (unlike the dashboard).
 * Produces ./out which is deployed verbatim to Cloudflare Pages
 * (custom domain: finer.t800.click).
 */
const nextConfig: NextConfig = {
  output: "export",
  // next/image cannot use the default server loader under static export.
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
