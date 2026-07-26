import type { ApiSession } from "../api";
import type { SessionController } from "./session";
import type { KeyValueStorage } from "./storage";

export function createRefreshTokenSessionController(
  storage: KeyValueStorage,
  key = "thoughtpins.refreshToken.v1",
): SessionController {
  let accessToken = "";
  return {
    get(): ApiSession | null {
      const refreshToken = storage.getItem(key);
      if (!refreshToken) {
        return null;
      }
      return { accessToken, refreshToken };
    },
    set(session: ApiSession | null): void {
      accessToken = session?.accessToken || "";
      if (session?.refreshToken) {
        storage.setItem(key, session.refreshToken);
      } else {
        storage.removeItem(key);
      }
    },
  };
}
