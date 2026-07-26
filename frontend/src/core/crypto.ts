const KEY_ALGORITHM = "AES-GCM";
const KEY_LENGTH = 256;
const IV_BYTES = 12;

export type EncryptedEnvelope = {
  v: 1;
  alg: "AES-GCM";
  iv: string;
  data: string;
};

export function hasWebCrypto(): boolean {
  return typeof crypto !== "undefined" && Boolean(crypto.subtle);
}

export async function generateAesKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey(
    { name: KEY_ALGORITHM, length: KEY_LENGTH },
    true,
    ["encrypt", "decrypt"],
  );
}

export async function exportAesKey(key: CryptoKey): Promise<string> {
  const raw = await crypto.subtle.exportKey("raw", key);
  return bytesToBase64(new Uint8Array(raw));
}

export async function importAesKey(rawBase64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    bytesToArrayBuffer(base64ToBytes(rawBase64)),
    { name: KEY_ALGORITHM },
    true,
    ["encrypt", "decrypt"],
  );
}

export async function encryptJson(value: unknown, key: CryptoKey): Promise<EncryptedEnvelope> {
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const encoded = new TextEncoder().encode(JSON.stringify(value));
  const encrypted = await crypto.subtle.encrypt({ name: KEY_ALGORITHM, iv }, key, encoded);
  return {
    v: 1,
    alg: KEY_ALGORITHM,
    iv: bytesToBase64(iv),
    data: bytesToBase64(new Uint8Array(encrypted)),
  };
}

export async function decryptJson<T>(envelope: EncryptedEnvelope, key: CryptoKey): Promise<T> {
  const iv = bytesToArrayBuffer(base64ToBytes(envelope.iv));
  const data = bytesToArrayBuffer(base64ToBytes(envelope.data));
  const decrypted = await crypto.subtle.decrypt(
    { name: KEY_ALGORITHM, iv },
    key,
    data,
  );
  return JSON.parse(new TextDecoder().decode(decrypted)) as T;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function bytesToArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}
