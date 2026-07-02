/** @type {import('next').NextConfig} */
const internalApiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";

module.exports = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
    ];
  },
  // Allow images from MinIO / dev hosts
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "minio" },
    ],
  },
};
