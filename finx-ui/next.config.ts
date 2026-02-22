import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  reactCompiler: true,

  // SPA-style client routing: all nav pages serve the root page component.
  // The useNavPage hook reads the pathname to determine the active page & admin tab.
  async rewrites() {
    return [
      { source: "/chat", destination: "/" },
      { source: "/explore", destination: "/" },
      { source: "/playground", destination: "/" },
      { source: "/admin", destination: "/" },
      { source: "/admin/:tab", destination: "/" },
    ];
  },
};

export default nextConfig;
