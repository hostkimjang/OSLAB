/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const api = process.env.OSLAB_API_PROXY ?? "http://127.0.0.1:3001";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};

export default nextConfig;
