/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
