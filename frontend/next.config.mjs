/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No rewrites/proxying: the browser calls the FastAPI backend
  // directly via NEXT_PUBLIC_API_URL (see src/lib/api.ts). The backend
  // allows this origin via CORS (see backend/app/core/config.py's
  // cors_allow_origins and app/main.py's CORSMiddleware).
};

export default nextConfig;
