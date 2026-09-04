/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The live API (radar serve) runs on :8787. In dev we proxy /api to it so the
  // browser can use same-origin requests. In static-export mode the UI falls
  // back to /data.json (see lib/api.ts).
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8787/api/:path*" }];
  },
};
export default nextConfig;
