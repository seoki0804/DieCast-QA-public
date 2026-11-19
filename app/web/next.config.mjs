/** API 요청(/api/*)을 FastAPI 서버로 넘긴다. 주소는 API_URL 환경 변수로 바꿀 수 있다. */
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
