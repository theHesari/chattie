import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev server only serves its JS to `localhost` by default; without this, opening
  // the app at http://127.0.0.1:3001 renders HTML that never hydrates (dead buttons).
  allowedDevOrigins: ["127.0.0.1"],
  cacheComponents: true,
  partialPrefetching: true,
  reactCompiler: true,
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
