/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Trim the runtime image: the Dockerfile ships only .next/standalone,
  // .next/static, and public/ instead of the full node_modules + source.
  output: "standalone",
  serverExternalPackages: ["pg"],
};

export default nextConfig;
