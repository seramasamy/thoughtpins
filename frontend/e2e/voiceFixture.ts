import type { Page } from "@playwright/test";

/** Synthetic recorder events exercise lifecycle behavior without a microphone or provider. */
export async function installVoiceFixture(page: Page, delayedPermission = false) {
  await page.addInitScript(({ delayedPermission }) => {
    localStorage.setItem("thoughtpins.voice-disclosure.2026-07-13", "accepted");
    const state = { stops: 0, release: () => {}, fail: () => {} };
    Object.assign(window, { voiceFixture: state });
    class Recorder {
      static isTypeSupported(type: string) { return type === "audio/webm"; }
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor() { state.fail = () => this.onerror?.(); }
      start() { this.state = "recording"; }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["synthetic recording"], { type: this.mimeType }) });
        this.onstop?.();
      }
    }
    const stream = { getTracks: () => [{ stop() { state.stops += 1; } }] };
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: {
      getUserMedia: () => delayedPermission
        ? new Promise(resolve => { state.release = () => resolve(stream); }) : Promise.resolve(stream),
    } });
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: Recorder });
  }, { delayedPermission });
}

