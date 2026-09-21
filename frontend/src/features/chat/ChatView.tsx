import { ArrowUp, CheckCircle2, LoaderCircle, Lock, Mic, Paperclip, RefreshCw, ShieldCheck, Square, XCircle } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { ChatMessageResponse, ChatResponse } from "../../types";
import { formatConversationDay, formatConversationTime } from "../../components/format";
import { ChatGlyph, IconButton, PrimaryButton, SecondaryButton } from "../../components/ui";
import { useChatSubmission, type ThreadMessage } from "./useChatSubmission";
import { usePrivateRecall } from "./usePrivateRecall";
import { KeptEntryNotice } from "./KeptEntryNotice";
import { ChatWelcome } from "./ChatWelcome";
import { MessageEditor } from "./MessageEditor";
import { submitFormOnEnter } from "../../components/keyboard";
import { UPLOAD_ACCEPT, uploadOutcome } from "../../core/upload";
import { useVoiceRecorder, MAX_RECORDING_MS } from "./useVoiceRecorder";
import { VoiceDraft } from "./VoiceDraft";
import { useChatScroll } from "./useChatScroll";

const CONVERSATION_ID = "main";
const VOICE_DISCLOSURE_KEY = "thoughtpins.voice-disclosure.2026-07-13";


export function ChatView({ token, run, maintenanceMessage = null, voiceArchiveEnabled = false }: ScreenProps & { maintenanceMessage?: string | null; voiceArchiveEnabled?: boolean }) {
  const [text, setText] = useState("");
  const [attachmentDestination, setAttachmentDestination] = useState<"library" | "journal">("library");
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [includePrivate, setIncludePrivate] = usePrivateRecall(token, run);
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
  const [showVoiceDisclosure, setShowVoiceDisclosure] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const wasBusyRef = useRef(false);
  const compactComposer = useCompactComposer();
  const voice = useVoiceRecorder();
  const { isRecording, elapsed: recordingElapsed, error: voiceError } = voice;
  const chatScroll = useChatScroll(messages.length, busy);

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

  const { sendMessage, canStop, stopReply } = useChatSubmission({
    token, run, busy, includePrivate, maintenanceMessage, pendingActionId, messages,
    setMessages, setText, setBusy, setBusyLabel, setLastResponse, setPendingActionId,
    setKeptEntryCount, setEditingId, setEditDraft, setSendPulse,
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage(text);
  };

  const uploadFile = async (file: File, displayText = `Shared ${file.name}`, destination = attachmentDestination, idempotencyKey?: string) => {
    if (busy) return false;
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
        () => api.uploadFile(token, file, { destination, conversation_id: CONVERSATION_ID, idempotency_key: idempotencyKey }),
        "",
      );
      if (result) setMessages((current) => [...current, {
        id: `upload-result-${crypto.randomUUID()}`,
        role: "assistant",
        text: uploadOutcome(result).text,
        routeType: uploadOutcome(result).saved ? result.destination : "upload",
        status: result.status,
        createdAt: new Date().toISOString(),
      }]);
      return Boolean(result && uploadOutcome(result).saved && uploadOutcome(result).tone !== "error");
    } finally {
      setBusy(false);
    }
  };

  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void uploadFile(file);
    event.target.value = "";
  };

  const startVoiceRecording = () => { if (!busy) void voice.start(); };
  const stopVoiceRecording = voice.stop;

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
          <IconButton onClick={loadThread} disabled={busy} aria-label="Restore conversation" title="Restore conversation"><RefreshCw size={17} /></IconButton>
        </div>
      </header>

      <div ref={chatScroll.streamRef} onScroll={chatScroll.onScroll} className="chat-stream" role="log" aria-label="Conversation history" aria-live="polite" tabIndex={0}>
        {!messages.length && (
          <ChatWelcome onChoose={(starter) => void sendMessage(starter)} />
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
                  {message.status === "failed" && <span>Reply unavailable</span>}
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
      </div>

      <div className="chat-composer-wrap">
        {chatScroll.unread && <SecondaryButton type="button" onClick={chatScroll.jump}>Jump to latest messages</SecondaryButton>}
        {showVoiceDisclosure && (
          <div className="voice-disclosure" role="dialog" aria-modal="true" aria-labelledby="voice-disclosure-title">
            <strong id="voice-disclosure-title">Record a voice note</strong>
            <p>{voiceArchiveEnabled
              ? "Thought Pins will send this recording for transcription. Audio is discarded after processing unless you separately enable Personal voice archive in Account."
              : "When you save, Thought Pins will send this recording for transcription and discard the audio after processing. You can review or discard before saving."}</p>
            <div>
              <SecondaryButton type="button" onClick={() => setShowVoiceDisclosure(false)}>Cancel</SecondaryButton>
              <PrimaryButton type="button" onClick={acceptVoiceDisclosure}>Continue</PrimaryButton>
            </div>
          </div>
        )}
        {voice.draft && <VoiceDraft file={voice.draft} busy={busy} onDiscard={voice.clearDraft}
          onSave={async (destination, key) => {
            if (voice.draft && await uploadFile(voice.draft, "Shared a voice note", destination, key)) voice.clearDraft();
          }} />}
        {pendingActionId && (
          <div className="pending-action-bar" role="group" aria-label="Pending confirmation">
            <span>This action needs your confirmation.</span>
            <div>
              <SecondaryButton type="button" disabled={busy} onClick={() => void sendMessage("cancel")}><XCircle size={16} />Cancel</SecondaryButton>
              <PrimaryButton type="button" disabled={busy} onClick={() => void sendMessage("confirm", true)}><CheckCircle2 size={16} />Confirm</PrimaryButton>
            </div>
          </div>
        )}
        {!voice.draft && <>
          <form className={isRecording ? "chat-composer is-recording" : "chat-composer"} onSubmit={submit}>
            <input ref={fileRef} className="visually-hidden" type="file" accept={UPLOAD_ACCEPT} onChange={upload} aria-label="Choose a file to attach" />
            <IconButton type="button" onClick={() => fileRef.current?.click()} disabled={busy || isRecording || Boolean(voice.draft)} aria-label="Attach a file" title="Attach a file"><Paperclip size={18} /></IconButton>
            <IconButton className={isRecording ? "voice-recording" : ""} type="button" onClick={isRecording ? stopVoiceRecording : requestVoiceRecording} disabled={busy || Boolean(voice.draft)} aria-label={isRecording ? "Stop voice note" : "Record a voice note"} title={isRecording ? "Stop voice note" : "Record a voice note"}>
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
              // Only an active chat request supports cancellation.
              <PrimaryButton type="button" disabled={!canStop} onClick={stopReply} aria-label={canStop ? "Stop reply" : "Processing attachment"} title={canStop ? "Stop reply" : "Processing attachment"}>
                {canStop ? <Square size={16} fill="currentColor" /> : <LoaderCircle size={18} />}
              </PrimaryButton>
            ) : (
              <PrimaryButton className={sendPulse ? "send-pulse" : ""} disabled={!text.trim()} aria-label="Send message"><ArrowUp size={19} /></PrimaryButton>
            )}
          </form>
          {isRecording && <SecondaryButton type="button" onClick={voice.discard}>Discard recording</SecondaryButton>}
          {isRecording && (
            <div className="voice-progress" role="progressbar" aria-label="Recording time used" aria-valuemin={0} aria-valuemax={600} aria-valuenow={Math.min(600, recordingElapsed)}>
              <span style={{ width: `${Math.min(100, ((recordingElapsed * 1000) / MAX_RECORDING_MS) * 100)}%` }} />
            </div>
          )}
          <div className="composer-caption">
            <span role={voiceError ? "status" : undefined}>{voiceError || (isRecording ? "Recording voice note..." : routingCaption(lastResponse))}</span>
            <span>{includePrivate ? "Private memories may inform this reply" : "Private memories stay out of replies"}</span>
          </div>
          <label className="attachment-destination">Save attachments as
            <select value={attachmentDestination} onChange={event => setAttachmentDestination(event.target.value as "library" | "journal")} disabled={busy || isRecording}>
              <option value="library">Reference sources</option><option value="journal">Personal journal</option>
            </select>
          </label>
        </>}
      </div>
    </section>
  );
}

function formatRecordingTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
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
