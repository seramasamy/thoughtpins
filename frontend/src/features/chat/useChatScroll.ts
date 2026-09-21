import { useLayoutEffect, useRef, useState } from "react";

/** Follow new replies only while the reader remains near the latest message. */
export function useChatScroll(messageCount: number, busy: boolean) {
  const streamRef = useRef<HTMLDivElement | null>(null);
  const follow = useRef(true);
  const [unread, setUnread] = useState(false);
  function jump(animate = true) {
    const stream = streamRef.current;
    if (!stream) return;
    follow.current = true;
    setUnread(false);
    stream.scrollTo({ top: stream.scrollHeight,
      behavior: animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "instant" });
  }
  function onScroll() {
    const stream = streamRef.current;
    if (!stream) return;
    follow.current = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 64;
    if (follow.current) setUnread(false);
  }
  useLayoutEffect(() => {
    if (!messageCount && !busy) return;
    if (follow.current) jump(false);
    else setUnread(true);
  }, [messageCount, busy]);
  return { streamRef, onScroll, unread, jump: () => jump() };
}
