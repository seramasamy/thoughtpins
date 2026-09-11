export type SessionTokenPair = { accessToken: string; refreshToken: string };
type Snapshot = { session: SessionTokenPair; lineage: object };
type Access = {
  get: () => SessionTokenPair | null;
  set: (session: SessionTokenPair | null) => void;
};

/** Rotate once per session; an older request never adopts a different account. */
export function createSessionRecovery(
  access: Access,
  renew: (refreshToken: string) => Promise<SessionTokenPair>,
  isRejected: (error: unknown) => boolean,
) {
  // Weak keys retain neither an account history nor tokens after callers finish.
  const lineages = new WeakMap<SessionTokenPair, object>();
  let pending: { session: SessionTokenPair; promise: Promise<SessionTokenPair | null> } | null = null;

  function capture(): Snapshot | null {
    const session = access.get();
    if (!session?.accessToken || !session.refreshToken) return null;
    let lineage = lineages.get(session);
    if (!lineage) {
      lineage = {};
      lineages.set(session, lineage);
    }
    return { session, lineage };
  }

  function recover(original: Snapshot | null, rejectedToken: string | null): Promise<SessionTokenPair | null> {
    const current = capture();
    if (!original || !current || !rejectedToken || original.session.accessToken !== rejectedToken
      || current.lineage !== original.lineage) return Promise.resolve(null);
    // A delayed 401 may arrive after another request already rotated this session.
    if (current.session !== original.session) return Promise.resolve(current.session);
    if (pending?.session === current.session) return pending.promise;

    const promise = Promise.resolve().then(() => renew(current.session.refreshToken)).then(next => {
      if (access.get() !== current.session) return null;
      lineages.set(next, current.lineage);
      access.set(next);
      return next;
    }).catch(error => {
      // Logout, a new login, or unmount may have replaced the original account.
      // Neither success nor rejection from the older operation may overwrite it.
      if (access.get() === current.session && isRejected(error)) access.set(null);
      throw error;
    }).finally(() => {
      if (pending?.promise === promise) pending = null;
    });
    pending = { session: current.session, promise };
    return promise;
  }

  return { capture, recover };
}
