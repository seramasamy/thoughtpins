import { ArrowUp, CheckCircle2, Lightbulb, Lock, Mic, Paperclip, RefreshCw, ShieldCheck, Sparkles, Square, UsersRound, XCircle } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { ChatMessageResponse, ChatResponse, UploadIngestResponse } from "../../types";
import { formatConversationDay, formatConversationTime } from "../../components/format";
import { ChatGlyph, IconButton, PrimaryButton, SecondaryButton } from "../../components/ui";
import { confirmationIntent } from "./confirmation";
import { KeptEntryNotice } from "./KeptEntryNotice";
import { MessageEditor } from "./MessageEditor";
import { submitFormOnEnter } from "../../components/keyboard";

type ThreadMessage = {
  id: string;
  role: "user" | "assistant" | string;
  text: string;
  routeType?: string | null;
  status?: string | null;
  createdAt?: string | null;
};

const CONVERSATION_ID = "main";
const VOICE_DISCLOSURE_KEY = "thoughtpins.voice-disclosure.2026-07-13";
const MAX_RECORDING_MS = 10 * 60 * 1000;
const STARTERS = [
  { text: "What has been on my mind?", icon: Lightbulb },
  { text: "Help me reflect on this week", icon: Sparkles },
  { text: "Who have I mentioned lately?", icon: UsersRound },
];

export function ChatView({ token, run, maintenanceMessage = null, voiceArchiveEnabled = false }: ScreenProps & { maintenanceMessage?: string | null; voiceArchiveEnabled?: boolean }) {
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [includePrivate, setIncludePrivate] = useState(false);
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState("Thinking with your memory");
  const [thinkingHandoff, setThinkingHandoff] = useState(false);
  /* Which of your own turns is open for editing, and the draft replacing it.
     Editing rewinds the conversation to that point the way it does in any
     chat product — the difference here is that a rewound turn may have saved
     a journal entry, so the server reports what it left behind. */
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [keptEntryCount, setKeptEntryCount] = useState(0);
  const [sendPulse, setSendPulse] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingElapsed, setRecordingElapsed] = useState(0);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [showVoiceDisclosure, setShowVoiceDisclosure] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const wasBusyRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordingStreamRef = useRef<MediaStream | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<number | null>(null);
  const recordingStartRef = useRef(0);
  const compactComposer = useCompactComposer();

  const loadThread = useCallback(async () => {
    const conversations = await run(() => api.chatConversations(token, 1, 50));
    const conversation = conversations?.items.find((item) => item.conversation_key === `web:${CONVERSATION_ID}` || item.title === CONVERSATION_ID);
    if (!conversation) return;
    const page = await run(() => api.chatMessages(token, conversation.id, 1, 100));
    if (page) setMessages(page.items.map(mapServerMessage));
  }, [run, token]);

  useEffect(() => {
    void loadThread();
  }, [loadThread]);

  useEffect(() => {
    void run(() => api.preferences(token)).then((preferences) => {
      if (preferences) setIncludePrivate(preferences.private_entries_in_ask);
    });
  }, [run, token]);

  useEffect(() => {
    if (!messages.length && !busy) return;
    bottomRef.current?.scrollIntoView({ block: "end", behavior: messages.length > 1 ? "smooth" : "auto" });
  }, [messages.length, busy]);

  /* When the wait ends, the thinking dots linger for a 160ms fade-out while
     the arriving message rises, so the handoff reads as one exchange. */
  useEffect(() => {
    if (busy) {
      wasBusyRef.current = true;
      return undefined;
    }
    if (!wasBusyRef.current) return undefined;
    wasBusyRef.current = false;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    setThinkingHandoff(true);
    const timer = window.setTimeout(() => setThinkingHandoff(false), 160);
    return () => window.clearTimeout(timer);
  }, [busy]);

  const placeholder = useMemo(() => {
    if (pendingActionId) {
      return compactComposer ? "Confirm or cancel..." : "Confirm or cancel the pending action...";
    }
    return compactComposer ? "Message..." : "Message Thought Pins...";
  }, [compactComposer, pendingActionId]);

  const sendMessage = useCallback(async (rawText: string, forceConfirm = false, supersedesId: string | null = null) => {
    const body = rawText.trim();
    if (!body || busy) return;
    // Drop the rewound turn and everything after it before the replacement
    // lands, so the thread never shows both versions at once.
    if (supersedesId) {
      setMessages((current) => {
        const cut = current.findIndex((item) => item.id === supersedesId);
        return cut === -1 ? current : current.slice(0, cut);
      });
    }
    setMessages((current) => [...current, {
      id: `local-${crypto.randomUUID()}`,
      role: "user",
      text: body,
      createdAt: new Date().toISOString(),
    }]);
    setText("");

    if (maintenanceMessage) {
      setMessages((current) => [...current, {
        id: `maintenance-${crypto.randomUUID()}`,
        role: "assistant",
        text: maintenanceMessage,
        routeType: "maintenance",
        status: "paused",
        createdAt: new Date().toISOString(),
      }]);
      return;
    }

    const intent = pendingActionId ? confirmationIntent(body) : null;
    setBusyLabel("Thinking with your memory");
    setBusy(true);
    // A reply can take a while when the model is reasoning over a lot of
    // memory. Without a way out, a slow or stalled turn leaves the person
    // watching a spinner with no recourse.
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await run(() => api.chat(token, {
        text: body,
        conversation_id: CONVERSATION_ID,
        include_private: includePrivate,
        confirm_action: Boolean(forceConfirm || (pendingActionId && intent === "confirm")),
        pending_action_id: pendingActionId,
        supersedes_message_id: supersedesId,
      }, controller.signal));
      if (!result) return;
      setLastResponse(result);
      // Adopt the stored id so this turn can itself be edited without a reload.
      if (result.user_message_id) {
        setMessages((current) => {
          const index = [...current].reverse().findIndex((item) => item.role === "user");
          if (index === -1) return current;
          const at = current.length - 1 - index;
          return current.map((item, i) => (i === at ? { ...item, id: result.user_message_id as string } : item));
        });
      }
      setKeptEntryCount(result.orphaned_entry_ids?.length ?? 0);
      setPendingActionId(extractPendingActionId(result));
      setMessages((current) => [...current, {
        id: `assistant-${crypto.randomUUID()}`,
        role: "assistant",
        text: result.reply || result.confirmation_prompt || "Done.",
        routeType: result.route_type,
        status: result.status,
        createdAt: new Date().toISOString(),
      }]);
      setSendPulse(true);
      window.setTimeout(() => setSendPulse(false), 240);
    } catch (error) {
      // Stopping is a deliberate choice, not a failure, so it is acknowledged
      // in the thread rather than reported as an error.
      //
      // The composer is deliberately left empty. Restoring the stopped message
      // into it re-entered the submit path and sent the same question a second
      // time, which is worse than retyping.
      if (error instanceof DOMException && error.name === "AbortError") {
        setMessages((current) => [...current, {
          id: `stopped-${crypto.randomUUID()}`,
          role: "assistant",
          text: "Stopped before a reply came back. Ask again whenever you are ready.",
          routeType: "stopped",
          status: "paused",
          createdAt: new Date().toISOString(),
        }]);
        return;
      }
      throw error;
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }, [busy, includePrivate, maintenanceMessage, pendingActionId, run, token]);

  const stopReply = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage(text);
  };

  const uploadFile = async (file: File, displayText = `Shared ${file.name}`) => {
    if (busy) return;
    setMessages((current) => [...current, {
      id: `upload-${crypto.randomUUID()}`,
      role: "user",
      text: displayText,
      routeType: "upload",
      createdAt: new Date().toISOString(),
    }]);
    const isVoice = file.type.startsWith("audio/");
    setBusyLabel(isVoice ? "Transcribing your voice note" : `Reading ${file.name}`);
    setBusy(true);
    try {
      const result = await run(
        () => api.uploadFile(token, file, { destination: "auto", conversation_id: CONVERSATION_ID }),
        isVoice ? "Voice note processed" : "File added to memory",
      );
      if (result) setMessages((current) => [...current, {
        id: `upload-result-${crypto.randomUUID()}`,
        role: "assistant",
        text: isVoice
          ? voiceUploadReply(result)
          : result.destination === "journal"
            ? `I saved ${file.name} with your journal memories.`
            : `I read ${file.name} and pinned it to your source memory. You can ask me about it whenever it is relevant.`,
        routeType: result.destination,
        status: result.status,
        createdAt: new Date().toISOString(),
      }]);
    } finally {
      setBusy(false);
    }
  };

  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void uploadFile(file);
    event.target.value = "";
  };

  const startVoiceRecording = async () => {
    if (busy || isRecording) return;
    setVoiceError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceError("Voice notes are not supported in this browser. You can attach an audio file instead.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type)) || "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recordingChunksRef.current = [];
      recordingStreamRef.current = stream;
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordingChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        if (recordingTimeoutRef.current !== null) window.clearTimeout(recordingTimeoutRef.current);
        recordingTimeoutRef.current = null;
        const type = recorder.mimeType || "audio/webm";
        const extension = type.includes("mp4") ? "m4a" : "webm";
        const file = new File(recordingChunksRef.current, `voice-note-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`, { type });
        recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
        recordingStreamRef.current = null;
        recorderRef.current = null;
        recordingChunksRef.current = [];
        setIsRecording(false);
        if (file.size > 0) {
          void uploadFile(file, "Shared a voice note");
        } else {
          setVoiceError("No audio was captured. Please try recording again.");
        }
      };
      recorder.onerror = () => {
        setVoiceError("The recording stopped unexpectedly. Please try again.");
        if (recorder.state === "recording") recorder.stop();
      };
      recorder.start(1000);
      setIsRecording(true);
      recordingTimeoutRef.current = window.setTimeout(() => {
        if (recorderRef.current?.state === "recording") recorderRef.current.stop();
      }, MAX_RECORDING_MS);
    } catch {
      recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
      recordingStreamRef.current = null;
      setVoiceError("Microphone access was not granted. You can attach an audio file instead.");
    }
  };

  const stopVoiceRecording = () => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
  };

  const requestVoiceRecording = () => {
    try {
      if (localStorage.getItem(VOICE_DISCLOSURE_KEY) === "accepted") {
        void startVoiceRecording();
        return;
      }
    } catch {
      // Storage may be unavailable in a private browser; the disclosure still works.
    }
    setShowVoiceDisclosure(true);
  };

  const acceptVoiceDisclosure = () => {
    try {
      localStorage.setItem(VOICE_DISCLOSURE_KEY, "accepted");
    } catch {
      // Consent applies to this action even when the browser cannot persist it.
    }
    setShowVoiceDisclosure(false);
    void startVoiceRecording();
  };

  useEffect(() => () => {
    recorderRef.current?.stop();
    recordingStreamRef.current?.getTracks().forEach((track) => track.stop());
    if (recordingTimeoutRef.current !== null) window.clearTimeout(recordingTimeoutRef.current);
  }, []);

  /* Elapsed clock for the recording state: ticks once a second while capture
     is active and drives both the mm:ss readout and the 10-minute hairline. */
  useEffect(() => {
    if (!isRecording) return undefined;
    recordingStartRef.current = Date.now();
    setRecordingElapsed(0);
    const timer = window.setInterval(() => {
      setRecordingElapsed(Math.floor((Date.now() - recordingStartRef.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isRecording]);

  return (
    <section className="chat-view">
      <header className="chat-header">
        <div className="chat-memory-status">
          <span className="presence-dot" />
          <ShieldCheck size={15} />
          <span>Memory ready</span>
        </div>
        <div className="chat-header-actions">
          <label className="private-memory-toggle" title="Allow private memories to inform this reply">
            <input aria-label="Use private memories in this reply" type="checkbox" checked={includePrivate} onChange={(event) => setIncludePrivate(event.target.checked)} />
            <Lock size={15} />
            <span className="private-memory-label-long">Use private memories</span>
            <span className="private-memory-label-short" aria-hidden="true">{includePrivate ? "Private on" : "Private off"}</span>
          </label>
          <IconButton onClick={loadThread} aria-label="Restore conversation" title="Restore conversation"><RefreshCw size={17} /></IconButton>
        </div>
      </header>

      <div className="chat-stream" role="log" aria-label="Conversation history" aria-live="polite" tabIndex={0}>
        {!messages.length && (
          <div className="chat-welcome">
            <img className="welcome-mark" src={`${import.meta.env.BASE_URL}assets/thought-pins-mark.svg?v=20260712-memory-pin-v4`} alt="" width="56" height="56" />
            <h2>What is on your mind?</h2>
            <p>I am here with everything you have chosen to remember.</p>
            <div className="starter-list">
              {STARTERS.map(({ text: starter, icon: StarterIcon }) => (
                <button key={starter} type="button" onClick={() => void sendMessage(starter)}>
                  <StarterIcon size={18} aria-hidden="true" />
                  <span>{starter}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <Fragment key={message.id}>
            {startsConversationDay(messages, index) && (
              <div className="chat-date-divider" aria-label={`Messages from ${formatConversationDay(message.createdAt)}`}>
                <span>{formatConversationDay(message.createdAt)}</span>
              </div>
            )}
            <article className={`chat-message-row ${message.role === "user" ? "user" : "assistant"}${editingId === message.id ? " is-editing" : ""}`}>
              {message.role !== "user" && <span className="message-avatar"><ChatGlyph size={19} /></span>}
              <div className="message-content">
                {editingId === message.id ? (
                  <MessageEditor
                    messageId={message.id}
                    draft={editDraft}
                    onDraftChange={setEditDraft}
                    onCancel={() => setEditingId(null)}
                    onSubmit={(next) => {
                      setEditingId(null);
                      if (next && next !== message.text) void sendMessage(next, false, message.id);
                    }}
                  />
                ) : (
                  <MessageBody text={message.text} />
                )}
                <footer>
                  <span>{message.role === "user" ? "You" : "Thought Pins"}</span>
                  {message.routeType && !["chat", "conversation"].includes(message.routeType) && <span className="classification-label">{friendlyRoute(message.routeType)}</span>}
                  {message.createdAt && <time dateTime={message.createdAt}>{formatConversationTime(message.createdAt)}</time>}
                  {message.role === "user" && editingId !== message.id && !message.id.startsWith("local-") && (
                    <button
                      type="button"
                      className="message-edit-trigger"
                      onClick={() => { setEditingId(message.id); setEditDraft(message.text); }}
                      disabled={busy}
                    >
                      Edit
                    </button>
                  )}
                </footer>
              </div>
            </article>
          </Fragment>
        ))}

        <KeptEntryNotice count={keptEntryCount} onDismiss={() => setKeptEntryCount(0)} />

        {(busy || thinkingHandoff) && (
          <div className={`chat-message-row assistant thinking-row${!busy && thinkingHandoff ? " is-leaving" : ""}`} role="status" aria-live="polite" aria-label={busyLabel} aria-hidden={!busy || undefined}>
            <span className="message-avatar"><ChatGlyph size={19} /></span>
            <div className="thinking-indicator"><span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span><span>{busyLabel}</span></div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-composer-wrap">
        {showVoiceDisclosure && (
          <div className="voice-disclosure" role="dialog" aria-modal="true" aria-labelledby="voice-disclosure-title">
            <strong id="voice-disclosure-title">Record a voice note</strong>
            <p>{voiceArchiveEnabled
              ? "Thought Pins will send this recording for transcription. Audio is discarded after processing unless you separately enable Personal voice archive in Account."
              : "Thought Pins will send this recording for transcription and discard the audio after processing. The transcript is saved as a journal entry."}</p>
            <div>
              <SecondaryButton type="button" onClick={() => setShowVoiceDisclosure(false)}>Cancel</SecondaryButton>
              <PrimaryButton type="button" onClick={acceptVoiceDisclosure}>Continue</PrimaryButton>
            </div>
          </div>
        )}
        {pendingActionId && (
          <div className="pending-action-bar" role="group" aria-label="Pending confirmation">
            <span>This action needs your confirmation.</span>
            <div>
              <SecondaryButton type="button" disabled={busy} onClick={() => void sendMessage("cancel")}><XCircle size={16} />Cancel</SecondaryButton>
              <PrimaryButton type="button" disabled={busy} onClick={() => void sendMessage("confirm", true)}><CheckCircle2 size={16} />Confirm</PrimaryButton>
            </div>
          </div>
        )}
        <form className={isRecording ? "chat-composer is-recording" : "chat-composer"} onSubmit={submit}>
          <input ref={fileRef} className="visually-hidden" type="file" onChange={upload} aria-label="Choose a file to attach" />
          <IconButton type="button" onClick={() => fileRef.current?.click()} disabled={busy} aria-label="Attach a file" title="Attach a file"><Paperclip size={18} /></IconButton>
          <IconButton className={isRecording ? "voice-recording" : ""} type="button" onClick={isRecording ? stopVoiceRecording : requestVoiceRecording} disabled={busy} aria-label={isRecording ? "Stop voice note" : "Record a voice note"} title={isRecording ? "Stop voice note" : "Record a voice note"}>
            {isRecording ? <Square size={16} fill="currentColor" /> : <Mic size={18} />}
          </IconButton>
          <div className="composer-field">
            <textarea value={text} onChange={(event) => setText(event.target.value)} onKeyDown={submitFormOnEnter} placeholder={placeholder} aria-label="Message Thought Pins" enterKeyHint="send" rows={1} maxLength={50000} />
            {isRecording && (
              <span className="voice-live" aria-hidden="true">
                <span className="voice-bars"><i /><i /><i /><i /><i /></span>
                <span className="voice-timer">{formatRecordingTime(recordingElapsed)}</span>
              </span>
            )}
          </div>
          {busy ? (
            // Same position as send, so stopping is where the hand already is.
            <PrimaryButton type="button" onClick={stopReply} aria-label="Stop reply" title="Stop reply">
              <Square size={16} fill="currentColor" />
            </PrimaryButton>
          ) : (
            <PrimaryButton className={sendPulse ? "send-pulse" : ""} disabled={!text.trim()} aria-label="Send message"><ArrowUp size={19} /></PrimaryButton>
          )}
        </form>
        {isRecording && (
          <div className="voice-progress" role="progressbar" aria-label="Recording time used" aria-valuemin={0} aria-valuemax={600} aria-valuenow={Math.min(600, recordingElapsed)}>
            <span style={{ width: `${Math.min(100, ((recordingElapsed * 1000) / MAX_RECORDING_MS) * 100)}%` }} />
          </div>
        )}
        <div className="composer-caption">
          <span role={voiceError ? "status" : undefined}>{voiceError || (isRecording ? "Recording voice note..." : routingCaption(lastResponse))}</span>
          <span>{includePrivate ? "Private memories may inform this reply" : "Private memories stay out of replies"}</span>
        </div>
      </div>
    </section>
  );
}

function formatRecordingTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function voiceUploadReply(result: UploadIngestResponse) {  if (result.status === "needs_text") return result.error || "I could not hear enough speech to create a journal entry.";
  if (result.voice_asset_id) return "I transcribed this voice note, saved the journal memory, and retained the encrypted recording in your personal voice archive.";
  return "I transcribed this voice note and saved the journal memory. The recording was discarded after processing.";
}

function mapServerMessage(message: ChatMessageResponse): ThreadMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.text,
    routeType: message.route_type,
    status: message.status,
    createdAt: message.created_at_utc,
  };
}

function extractPendingActionId(response: ChatResponse): string | null {
  if (!response.requires_confirmation) return null;
  const value = response.metadata?.pending_action_id;
  return typeof value === "string" && value ? value : null;
}

function friendlyRoute(route: string) {
  return ({
    journal: "Saved as journal",
    library: "Pinned source",
    reminder: "Reminder",
    search: "Memory search",
    upload: "Attachment",
    mixed: "Memory + sources",
    system: "Memory update",
  } as Record<string, string>)[route] || route.replaceAll("_", " ");
}

function routingCaption(response: ChatResponse | null) {
  const hint = response?.metadata?.routing_hint;
  return typeof hint === "string" && hint.trim() ? hint : "Memory connected";
}

function startsConversationDay(messages: ThreadMessage[], index: number) {
  const current = messages[index]?.createdAt;
  if (!current) return false;
  const previous = messages[index - 1]?.createdAt;
  if (!previous) return true;
  const currentDate = new Date(current);
  const previousDate = new Date(previous);
  if (Number.isNaN(currentDate.valueOf()) || Number.isNaN(previousDate.valueOf())) return false;
  return currentDate.toDateString() !== previousDate.toDateString();
}

function useCompactComposer() {
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 520px)").matches);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 520px)");
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return compact;
}

function MessageBody({ text }: { text: string }) {
  const blocks = text.trim().split(/\n{2,}/).filter(Boolean);
  return (
    <div className="message-body">
      {blocks.map((block, blockIndex) => {
        const lines = block.split(/\n/).map((line) => line.trim()).filter(Boolean);
        if (lines.length && lines.every((line) => /^[-*]\s+/.test(line))) {
          return <ul key={`list-${blockIndex}`}>{lines.map((line, lineIndex) => <li key={lineIndex}>{inlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>)}</ul>;
        }
        return lines.map((line, lineIndex) => <p key={`${blockIndex}-${lineIndex}`}>{inlineMarkdown(line)}</p>);
      })}
    </div>
  );
}

function inlineMarkdown(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    return <span key={index}>{part}</span>;
  });
}
