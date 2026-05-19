/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  // Allow images from MinIO / dev hosts
  images: {
    remotePatterns: [
      { protocol: "http", hostname: "localhost" },
      { protocol: "http", hostname: "minio" },
    ],
  },
};
