import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,

  // SPA-style client routing: all nav pages serve the root page component.
  // The useNavPage hook reads the pathname to determine the active page.
  async rewrites() {
    return [
      { source: "/chat", destination: "/" },
      { source: "/explore", destination: "/" },
      { source: "/schema-pipeline", destination: "/" },
      { source: "/graph-explorer", destination: "/" },
    ];
  },
};

export default nextConfig;
