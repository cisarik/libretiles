import { networkInterfaces } from "node:os";
import type { NextConfig } from "next";

function getAllowedDevOrigins(): string[] {
  const origins = new Set<string>();

  for (const addresses of Object.values(networkInterfaces())) {
    for (const address of addresses ?? []) {
      if (address.family !== "IPv4" || address.internal) {
        continue;
      }
      origins.add(address.address);
    }
  }

  for (const origin of (process.env.NEXT_DEV_ALLOWED_ORIGINS || "").split(",")) {
    const trimmedOrigin = origin.trim();
    if (trimmedOrigin) {
      origins.add(trimmedOrigin);
    }
  }

  return [...origins];
}

const nextConfig: NextConfig = {
  allowedDevOrigins: getAllowedDevOrigins(),
};

export default nextConfig;
