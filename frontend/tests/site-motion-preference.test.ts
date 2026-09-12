import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../../site/assets/motion-preference.js", import.meta.url), "utf8");

function harness(blocked = false) {
  const values = new Map<string, string>();
  const button = Object.assign(new EventTarget(), { hidden: true, textContent: "" });
  const media = Object.assign(new EventTarget(), { matches: false });
  const page = new EventTarget();
  const root = { dataset: {} as Record<string, string> };
  const document = Object.assign(new EventTarget(), {
    documentElement: root, querySelector: () => button,
  });
  runInNewContext(source, {
    Event, document, window: page, matchMedia: () => media,
    sessionStorage: {
      getItem(key: string) { if (blocked) throw new Error("Unavailable"); return values.get(key); },
      setItem(key: string, value: string) { if (blocked) throw new Error("Unavailable"); values.set(key, value); },
    },
  });
  return { values, button, media, page, root };
}

test("a restored document observes the choice made on another homepage", () => {
  const h = harness();
  assert.equal(h.root.dataset.motionPaused, "false");
  h.values.set("thoughtpins.motionPaused", "true");
  h.page.dispatchEvent(new Event("pageshow"));
  assert.equal(h.root.dataset.motionPaused, "true");
  assert.equal(h.button.textContent, "Resume motion");
  h.values.set("thoughtpins.motionPaused", "false");
  h.page.dispatchEvent(new Event("pageshow"));
  assert.equal(h.root.dataset.motionPaused, "false");
});

test("unavailable storage preserves the in-memory pause choice on restoration", () => {
  const h = harness(true);
  h.button.dispatchEvent(new Event("click"));
  h.page.dispatchEvent(new Event("pageshow"));
  assert.equal(h.root.dataset.motionPaused, "true");
  assert.equal(h.button.textContent, "Resume motion");
});

test("system Reduce Motion does not overwrite an explicit pause choice", () => {
  const h = harness();
  h.button.dispatchEvent(new Event("click"));
  h.media.matches = true;
  h.media.dispatchEvent(new Event("change"));
  assert.equal(h.button.hidden, true);
  assert.equal(h.root.dataset.motionPaused, "true");
  h.media.matches = false;
  h.media.dispatchEvent(new Event("change"));
  assert.equal(h.button.hidden, false);
  assert.equal(h.button.textContent, "Resume motion");
  assert.equal(h.root.dataset.motionPaused, "true");
});
