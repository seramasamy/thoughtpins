import { ArrowUpRight, Lightbulb, Sparkles, UsersRound } from "lucide-react";

const STARTERS = [
  { title: "Find a thread", text: "What has been on my mind?", icon: Lightbulb },
  { title: "Take a moment", text: "Help me reflect on this week", icon: Sparkles },
  { title: "Reconnect", text: "Who have I mentioned lately?", icon: UsersRound },
];

export function ChatWelcome({ onChoose }: { onChoose: (text: string) => void }) {
  return (
    <div className="chat-welcome">
      <div className="memory-orbit" aria-hidden="true">
        <span className="orbit-track orbit-track--outer" />
        <span className="orbit-track orbit-track--inner" />
        <img className="welcome-mark" src={`${import.meta.env.BASE_URL}assets/thought-pins-mark.svg?v=20260712-memory-pin-v4`} alt="" width="64" height="64" />
        <i className="orbit-node orbit-node--one" /><i className="orbit-node orbit-node--two" />
      </div>
      <span className="welcome-eyebrow">A little space for your mind</span>
      <h2>What is on your mind?</h2>
      <p>A thought, a moment, a question.<br />Start anywhere. Make a connection.</p>
      <div className="starter-list">
        {STARTERS.map(({ title, text, icon: Icon }) => (
          <button key={text} type="button" onClick={() => onChoose(text)} aria-label={text}>
            <Icon size={19} aria-hidden="true" />
            <span><strong>{title}</strong><span>{text}</span></span>
            <ArrowUpRight className="starter-arrow" size={16} aria-hidden="true" />
          </button>
        ))}
      </div>
    </div>
  );
}
