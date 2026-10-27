import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:5000/api/:path*",
      },
      {
        source: "/violations/:path*",
        destination: "http://localhost:5000/violations/:path*",
      },
    ];
  },
};

export default nextConfig;
