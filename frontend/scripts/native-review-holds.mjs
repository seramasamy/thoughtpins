// Loopback fixture control: let XCTest inspect a request before releasing it.
// Permits also handle a release that arrives before the app's HTTP request.
export class NativeReviewHolds {
  routes = new Set();
  pending = new Map();
  permits = new Map();

  configure(routes = []) {
    this.reset();
    this.routes = new Set(routes);
  }

  async wait(route) {
    if (!this.routes.has(route)) return;
    const permits = this.permits.get(route) || 0;
    if (permits > 0) {
      this.permits.set(route, permits - 1);
      return;
    }
    await new Promise(resolve => {
      const waiting = this.pending.get(route) || [];
      waiting.push(resolve);
      this.pending.set(route, waiting);
    });
  }

  release(route) {
    if (!this.routes.has(route)) return;
    const resolve = this.pending.get(route)?.shift();
    if (resolve) resolve();
    else this.permits.set(route, (this.permits.get(route) || 0) + 1);
  }

  reset() {
    for (const waiting of this.pending.values()) for (const resolve of waiting) resolve();
    this.pending.clear();
    this.permits.clear();
    this.routes.clear();
  }
}
