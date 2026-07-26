import type { DeviceRegistrationRequest } from "../types";
import type { KeyValueStorage } from "./storage";

const INSTALLATION_KEY = "thoughtpins.installationId.v1";

export function getOrCreateInstallationId(storage: KeyValueStorage, key = INSTALLATION_KEY): string {
  const existing = storage.getItem(key);
  if (existing) {
    return existing;
  }
  const next = crypto.randomUUID();
  storage.setItem(key, next);
  return next;
}

export function buildWebDeviceRegistration(
  storage: KeyValueStorage,
  appVersion: string,
  pushToken?: string | null,
): DeviceRegistrationRequest {
  const nav = typeof navigator !== "undefined" ? navigator : null;
  const language = nav?.language || null;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  return {
    installation_id: getOrCreateInstallationId(storage),
    platform: "web",
    device_name: nav?.platform || "web",
    app_version: appVersion,
    build_number: appVersion,
    os_version: nav?.userAgent ? trim(nav.userAgent, 64) : null,
    locale: language,
    timezone,
    push_provider: pushToken ? "webpush" : null,
    push_token: pushToken || null,
    notifications_enabled: Boolean(pushToken),
    metadata: {
      userAgentFamily: "user-agent",
    },
  };
}

function trim(value: string, max: number): string {
  return value.length <= max ? value : value.slice(0, max);
}
