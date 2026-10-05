import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server output => much smaller Docker image
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
