import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  // Produces .next/standalone: a self-contained server bundle with only the
  // node_modules it actually needs, so the runtime Docker stage doesn't have
  // to ship the full node_modules tree.
  output: "standalone",
};
export default nextConfig;
