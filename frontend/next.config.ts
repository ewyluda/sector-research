import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow loading the dev server via 127.0.0.1 (matches the API host pinned in
  // .env.local); otherwise Next 16 blocks its dev resources cross-origin.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
