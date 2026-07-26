import type { ClientConfigResponse } from "../types";

export type ClientPlatform = "ios" | "android" | "web";

export type VersionDecision = {
  status: "supported" | "update_recommended" | "blocked";
  minimum: string;
  recommended: string;
  storeUrl: string | null;
};

export function evaluateClientVersion(
  config: ClientConfigResponse,
  platform: ClientPlatform,
  currentVersion: string,
): VersionDecision {
  const minimum = config.minimum_supported_clients[platform] || "0.0.0";
  const recommended = config.recommended_clients[platform] || minimum;
  const storeUrl = config.store_urls[platform] || null;

  if (compareVersions(currentVersion, minimum) < 0) {
    return { status: "blocked", minimum, recommended, storeUrl };
  }
  if (compareVersions(currentVersion, recommended) < 0) {
    return { status: "update_recommended", minimum, recommended, storeUrl };
  }
  return { status: "supported", minimum, recommended, storeUrl };
}

export function compareVersions(left: string, right: string): number {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const diff = (a[index] || 0) - (b[index] || 0);
    if (diff !== 0) {
      return diff > 0 ? 1 : -1;
    }
  }
  return 0;
}

function parseVersion(value: string): number[] {
  return value
    .split(/[.+-]/)
    .map((part) => Number.parseInt(part.replace(/\D/g, ""), 10))
    .filter((part) => Number.isFinite(part));
}
