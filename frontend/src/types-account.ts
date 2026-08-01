/** Who you are, how you sign in, and what is signed in.
 *
 * Split out of types.ts, which had grown past its size budget. These belong
 * together: identity, credentials, devices, sessions, and private-launch
 * admission are one surface, and none of them describe a memory.
 */

export type DeviceRegistrationRequest = {
  installation_id: string;
  platform: "ios" | "android" | "web";
  device_name?: string | null;
  app_version?: string | null;
  build_number?: string | null;
  os_version?: string | null;
  locale?: string | null;
  timezone?: string | null;
  push_provider?: "apns" | "fcm" | "webpush" | null;
  push_token?: string | null;
  notifications_enabled?: boolean;
  metadata?: Record<string, unknown>;
};

export type DeviceResponse = Omit<DeviceRegistrationRequest, "push_token" | "metadata"> & {
  id: string;
  push_token_present: boolean;
  notifications_enabled: boolean;
  created_at_utc: string | null;
  last_seen_at_utc: string | null;
  revoked_at_utc: string | null;
};

export type DevicesPageResponse = {
  items: DeviceResponse[];
  total: number;
};

export type SessionResponse = {
  id: string;
  current: boolean;
  created_at_utc: string | null;
  expires_at_utc: string | null;
  revoked_at_utc: string | null;
  user_agent: string | null;
  ip_address: string | null;
};

export type SessionsPageResponse = {
  items: SessionResponse[];
  total: number;
};

export type InviteStatusResponse = {
  invite_required: boolean;
  invite_redeemed: boolean;
  admitted: boolean;
  contact_email: string;
  attempts_remaining: number;
};

export type SignInMethodsResponse = {
  email: string | null;
  phone: string | null;
  password_set: boolean;
  email_verified: boolean;
  oauth_providers: string[];
  magic_link_available: boolean;
  password_change_requires: "current_password" | "email_code" | "unavailable";
};

export type PasswordSetRequest = {
  new_password: string;
  current_password?: string;
  code?: string;
};

export type PasswordSetResponse = {
  status: string;
  password_set: boolean;
  other_sessions_revoked: number;
};

export type MeResponse = {
  id: string;
  email: string | null;
  phone: string | null;
  display_name: string | null;
  is_admin: boolean;
  auth_method: string;
  created_at_utc: string | null;
  last_login_utc: string | null;
};
