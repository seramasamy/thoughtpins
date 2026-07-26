import { api, configureApiSession, type ApiSession } from "../api";
import type { ClientConfigResponse } from "../types";
import { buildWebDeviceRegistration } from "./installation";
import { createSessionController } from "./session";
import type { KeyValueStorage } from "./storage";
import { evaluateClientVersion, type ClientPlatform, type VersionDecision } from "./versionPolicy";

export type AppRuntime = {
  config: ClientConfigResponse;
  session: ApiSession | null;
  version: VersionDecision;
};

export type BootstrapOptions = {
  storage: KeyValueStorage;
  platform?: ClientPlatform;
  appVersion?: string;
  registerDevice?: boolean;
};

export async function bootstrapAppRuntime(options: BootstrapOptions): Promise<AppRuntime> {
  const sessionController = createSessionController(options.storage);
  configureApiSession(sessionController);

  const config = await api.clientConfig();
  const platform = options.platform || "web";
  const appVersion = options.appVersion || config.recommended_clients[platform] || config.api_version;
  const session = sessionController.get();

  if (options.registerDevice !== false && (session || config.auth_required === false)) {
    await api.registerDevice(session?.accessToken || "", buildWebDeviceRegistration(options.storage, appVersion));
  }

  return {
    config,
    session,
    version: evaluateClientVersion(config, platform, appVersion),
  };
}
