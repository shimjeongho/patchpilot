/** @type {import('next').NextConfig} */
const nextConfig = {
  // 정적 HTML 로만 내보낸다. 런타임 서버도 API 라우트도 두지 않는다.
  output: 'export',
  // 중첩 경로를 파일 서버에서 그대로 열 수 있게 디렉터리 형태로 내보낸다.
  trailingSlash: true,
  images: { unoptimized: true },
}

export default nextConfig
