// Share an in-flight load and allow a real retry after a failed/blocked script.
const loads = new Map<string, Promise<void>>();

export function loadProviderScript(src: string, id: string): Promise<void> {
  const pending = loads.get(id);
  if (pending) return pending;
  const promise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.async = true;
    const finish = (failed: boolean) => {
      window.clearTimeout(timeout);
      script.onload = null;
      script.onerror = null;
      if (failed) {
        script.remove();
        loads.delete(id);
        reject(new Error("Could not reach the sign-in provider. Check your connection and try again."));
      } else resolve();
    };
    const timeout = window.setTimeout(() => finish(true), 15_000);
    script.onload = () => finish(false);
    script.onerror = () => finish(true);
    document.head.appendChild(script);
  });
  loads.set(id, promise);
  return promise;
}
