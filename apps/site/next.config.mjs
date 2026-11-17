// Compiled in a temporary project under apps/web to share its dependencies.
const basePath = process.env.SITE_BASE_PATH ?? "/CareerPilot";
if (basePath && (!basePath.startsWith("/") || basePath.endsWith("/") || !/^\/[A-Za-z0-9_/-]+$/.test(basePath))) {
  throw new Error("SITE_BASE_PATH must be empty or a URL path without a trailing slash");
}
const config = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  env: { NEXT_PUBLIC_SITE_BASE_PATH: basePath },
};

export default config;
