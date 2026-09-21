import { useEffect, useRef, useState } from "react";

export const MAX_RECORDING_MS = 10 * 60 * 1000;

/** Recording stays local until an explicit save. Cleanup can never upload. */
export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<File | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const generation = useRef(0);
  const mounted = useRef(true);
  const starting = useRef(false);

  function stopTracks() {
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
    window.clearTimeout(timer.current);
  }

  function discard() {
    generation.current += 1;
    if (recorder.current) {
      recorder.current.onstop = null;
      recorder.current.ondataavailable = null;
      recorder.current.onerror = null;
      if (recorder.current.state !== "inactive") recorder.current.stop();
      recorder.current = null;
    }
    stopTracks();
    starting.current = false;
    setIsRecording(false);
    setDraft(null);
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      generation.current += 1;
      if (recorder.current) {
        recorder.current.onstop = null;
        recorder.current.ondataavailable = null;
        recorder.current.onerror = null;
        if (recorder.current.state !== "inactive") recorder.current.stop();
      }
      stopTracks();
    };
  }, []);

  useEffect(() => {
    if (!isRecording) return;
    const started = Date.now();
    setElapsed(0);
    const tick = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(tick);
  }, [isRecording]);

  async function start() {
    if (starting.current || recorder.current || draft) return;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice notes are not supported in this browser. You can attach an audio file instead.");
      return;
    }
    starting.current = true;
    const attempt = ++generation.current;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mounted.current || attempt !== generation.current) {
        acquired.getTracks().forEach(track => track.stop());
        return;
      }
      stream.current = acquired;
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find(type => MediaRecorder.isTypeSupported(type));
      const active = new MediaRecorder(acquired, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      recorder.current = active;
      active.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      active.onstop = () => {
        active.onerror = null;
        stopTracks();
        recorder.current = null;
        if (!mounted.current || attempt !== generation.current) return;
        setIsRecording(false);
        const type = active.mimeType || "audio/webm";
        const suffix = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
        const file = new File(chunks, `voice-note.${suffix}`, { type });
        if (file.size) setDraft(file);
        else setError("No audio was captured. Please try recording again.");
      };
      active.onerror = () => {
        discard();
        setError("The recording stopped unexpectedly. Nothing was uploaded. Please try again.");
      };
      active.start(1000);
      setIsRecording(true);
      timer.current = window.setTimeout(() => {
        if (active.state === "recording") active.stop();
      }, MAX_RECORDING_MS);
    } catch {
      if (!mounted.current || attempt !== generation.current) return;
      stopTracks();
      recorder.current = null;
      if (mounted.current && attempt === generation.current) {
        setError("Recording could not start. Check microphone permission or attach an audio file.");
      }
    } finally {
      if (attempt === generation.current) starting.current = false;
    }
  }

  return { isRecording, elapsed, error, draft, start, discard,
    stop: () => { if (recorder.current?.state === "recording") recorder.current.stop(); },
    clearDraft: () => setDraft(null),
  };
}
