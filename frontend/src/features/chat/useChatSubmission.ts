import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { api } from "../../api";
import type { Runner } from "../../app/types";
import type { ChatResponse } from "../../types";
import { confirmationIntent } from "./confirmation";

export type ThreadMessage = {
  id: string;
  role: string;
  text: string;
  routeType?: string | null;
  status?: string | null;
  createdAt?: string | null;
};

type Setter<T> = Dispatch<SetStateAction<T>>;
type Options = {
  token: string;
  run: Runner;
  busy: boolean;
  includePrivate: boolean;
  maintenanceMessage: string | null;
  pendingActionId: string | null;
  messages: ThreadMessage[];
  setMessages: Setter<ThreadMessage[]>;
  setText: Setter<string>;
  setBusy: Setter<boolean>;
  setBusyLabel: Setter<string>;
  setLastResponse: Setter<ChatResponse | null>;
  setPendingActionId: Setter<string | null>;
  setKeptEntryCount: Setter<number>;
  setEditingId: Setter<string | null>;
  setEditDraft: Setter<string>;
  setSendPulse: Setter<boolean>;
};

/** One explicit submission at a time, with recoverable drafts on failure. */
export function useChatSubmission(options: Options) {
  const abortRef = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const pulseTimer = useRef<number | undefined>(undefined);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      abortRef.current?.abort();
      window.clearTimeout(pulseTimer.current);
    };
  }, []);

  async function sendMessage(rawText: string, forceConfirm = false, supersedesId: string | null = null) {
    const o = options;
    const body = rawText.trim();
    if (!body || o.busy || abortRef.current) return;
    const original = o.messages;
    const localId = `local-${crypto.randomUUID()}`;
    const controller = new AbortController();
    abortRef.current = controller;
    o.setMessages(current => {
      const cut = supersedesId ? current.findIndex(item => item.id === supersedesId) : -1;
      const kept = cut < 0 ? current : current.slice(0, cut);
      return [...kept.filter(item => !(item.status === "failed" && item.text === body)), {
        id: localId, role: "user", text: body, createdAt: new Date().toISOString(),
      }];
    });
    // Editing the thread must not discard an unrelated composer draft.
    if (!supersedesId) o.setText("");

    function recoverDraft() {
      if (supersedesId) {
        o.setMessages(original);
        o.setEditingId(supersedesId);
        o.setEditDraft(rawText);
      } else {
        o.setMessages(current => current.map(item => item.id === localId ? { ...item, status: "failed" } : item));
        o.setText(current => current || rawText);
      }
    }

    o.setBusyLabel("Thinking with your memory");
    o.setBusy(true);
    try {
      if (o.maintenanceMessage) {
        o.setMessages(current => [...current, {
          id: `maintenance-${crypto.randomUUID()}`, role: "assistant", text: o.maintenanceMessage!,
          routeType: "maintenance", status: "paused", createdAt: new Date().toISOString(),
        }]);
        return;
      }
      const intent = o.pendingActionId ? confirmationIntent(body) : null;
      const result = await o.run(() => api.chat(o.token, {
        text: body, conversation_id: "main", include_private: o.includePrivate,
        confirm_action: Boolean(forceConfirm || (o.pendingActionId && intent === "confirm")),
        pending_action_id: o.pendingActionId, supersedes_message_id: supersedesId,
      }, controller.signal), "");
      if (!mounted.current || controller.signal.aborted) return;
      if (!result) { recoverDraft(); return; }
      o.setLastResponse(result);
      const pending = result.metadata?.pending_action_id;
      o.setPendingActionId(result.requires_confirmation && typeof pending === "string" && pending ? pending : null);
      o.setKeptEntryCount(result.orphaned_entry_ids?.length ?? 0);
      o.setMessages(current => [...current.map(item => item.id === localId && result.user_message_id
        ? { ...item, id: result.user_message_id } : item), {
        id: `assistant-${crypto.randomUUID()}`, role: "assistant",
        text: result.reply || result.confirmation_prompt || "Done.",
        routeType: result.route_type, status: result.status, createdAt: new Date().toISOString(),
      }]);
      o.setSendPulse(true);
      pulseTimer.current = window.setTimeout(() => o.setSendPulse(false), 240);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof DOMException && error.name === "AbortError") {
        if (supersedesId) recoverDraft();
        o.setMessages(current => [...current, {
          id: `stopped-${crypto.randomUUID()}`, role: "assistant",
          text: "Stopped before a reply came back. Ask again whenever you are ready.",
          routeType: "stopped", status: "paused", createdAt: new Date().toISOString(),
        }]);
      } else {
        recoverDraft();
      }
    } finally {
      abortRef.current = null;
      if (mounted.current) o.setBusy(false);
    }
  }

  return { sendMessage, canStop: abortRef.current !== null, stopReply: () => abortRef.current?.abort() };
}
