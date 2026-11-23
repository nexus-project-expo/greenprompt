import type { NextConfig } from "next";

// Static export: FastAPI serves web/out, so the demo is one Python process.
const config: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  devIndicators: false,
};

export default config;
