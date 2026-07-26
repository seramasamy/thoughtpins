export type KeyValueStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};

export function createMemoryStorage(seed: Record<string, string> = {}): KeyValueStorage {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
}

export function createPrefixedStorage(storage: KeyValueStorage, prefix: string): KeyValueStorage {
  const normalize = (key: string) => `${prefix}${key}`;
  return {
    getItem: (key) => storage.getItem(normalize(key)),
    setItem: (key, value) => storage.setItem(normalize(key), value),
    removeItem: (key) => storage.removeItem(normalize(key)),
  };
}

export function browserStorage(): KeyValueStorage | null {
  try {
    if (typeof localStorage === "undefined") {
      return null;
    }
    return localStorage;
  } catch {
    return null;
  }
}
