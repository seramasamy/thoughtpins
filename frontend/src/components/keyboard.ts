import type { KeyboardEvent } from "react";

type TextControl = HTMLInputElement | HTMLTextAreaElement;

export function isSendEnter(event: KeyboardEvent<TextControl>): boolean {
  return event.key === "Enter"
    && !event.shiftKey
    && !event.nativeEvent.isComposing
    && event.keyCode !== 229;
}

export function submitFormOnEnter(event: KeyboardEvent<TextControl>): void {
  if (!isSendEnter(event)) return;
  event.preventDefault();
  if (!event.repeat) event.currentTarget.form?.requestSubmit();
}

export function runOnEnter(event: KeyboardEvent<TextControl>, action: () => void): void {
  if (!isSendEnter(event)) return;
  event.preventDefault();
  if (!event.repeat) action();
}
