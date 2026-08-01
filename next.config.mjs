/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // research/experiments.md is read at runtime by /api/experiments (and at
  // build time by /research), but it is data rather than an import, so Next's
  // file tracing has no way to discover it. Without this the ledger — the
  // centrepiece of the public page — 404s on Vercel while working perfectly
  // in local dev.
  outputFileTracingIncludes: {
    "/api/experiments": ["./research/experiments.md"],
    "/research": ["./research/experiments.md"],
  },
};

export default nextConfig;
