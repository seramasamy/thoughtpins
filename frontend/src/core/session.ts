import type { ApiSession } from "../api";
import type { ClientConfigResponse } from "../types";
import type { KeyValueStorage } from "./storage";

export type SessionController = {
  get: () => ApiSession | null;
  set: (session: ApiSession | null) => void;
};

export function createSessionController(storage: KeyValueStorage, key = "thoughtpins.session.v1"): SessionController {
  return {
    get() {
      try {
        const raw = storage.getItem(key);
        return raw ? (JSON.parse(raw) as ApiSession) : null;
      } catch {
        return null;
      }
    },
    set(session) {
      if (!session) {
        storage.removeItem(key);
        return;
      }
      storage.setItem(key, JSON.stringify(session));
    },
  };
}

export function canUseLocalMode(config: ClientConfigResponse | null, session: ApiSession | null): boolean {
  return Boolean(session || config?.auth_required === false);
}

export function requiresAuthenticatedAccount(config: ClientConfigResponse | null): boolean {
  return config?.auth_required !== false;
}
