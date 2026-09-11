import { Loader2, LogOut, Moon, PanelLeftClose, PanelRightClose, Plus, RefreshCw, Send, Settings2, Sun, X } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { PRIMARY_NAV_ITEMS, UTILITY_NAV_ITEMS, viewSubtitle, viewTitle } from "./navigation";
import type { GlobalComposeMode, Notice, View } from "./types";
import type { MeResponse } from "../types";
import { BrandMark, ChatGlyph, IconButton, NoticeBanner, PrimaryButton } from "../components/ui";
import { submitFormOnEnter } from "../components/keyboard";
import { toggleTheme, useResolvedTheme } from "../core/theme";

type SidebarSide = "left" | "right";

export function AppShell({
  view,
  setView,
  notice,
  clearNotice,
  me,
  localMode,
  busy,
  composePending,
  refreshMe,
  logout,
  maintenanceMessage,
  onGlobalCompose,
  children,
}: {
  view: View;
  setView: (view: View) => void;
  notice: Notice | null;
  clearNotice: () => void;
  me: MeResponse | null;
  localMode: boolean;
  busy: boolean;
  composePending: GlobalComposeMode | null;
  refreshMe: () => void;
  logout: () => Promise<void>;
  maintenanceMessage?: string | null;
  onGlobalCompose: (text: string, mode: GlobalComposeMode) => Promise<boolean>;
  children: ReactNode;
}) {
  const [utilityOpen, setUtilityOpen] = useState(false);
  const [sidebarSide, setSidebarSide] = useState<SidebarSide>(() => localStorage.getItem("thoughtpins.sidebar.side") === "right" ? "right" : "left");
  const showGlobalComposer = view !== "chat";
  const userLabel = me?.display_name || me?.email || (localMode ? "Local memory" : "Your account");
  const libraryItem = UTILITY_NAV_ITEMS.find((item) => item.view === "library");
  const theme = useResolvedTheme();

  const changeView = (next: View) => {
    setView(next);
    setUtilityOpen(false);
  };

  const toggleSidebar = () => {
    const next = sidebarSide === "left" ? "right" : "left";
    setSidebarSide(next);
    localStorage.setItem("thoughtpins.sidebar.side", next);
  };

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setUtilityOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  return (
    <div className={`app-shell sidebar-${sidebarSide}${showGlobalComposer ? " has-global-composer" : ""}`}>
      <aside className="sidebar" aria-label="Workspace navigation">
        <div className="sidebar-brand-row">
          <BrandMark />
          <IconButton className="sidebar-side-toggle" onClick={toggleSidebar} aria-label={`Move navigation to the ${sidebarSide === "left" ? "right" : "left"}`} title={`Move navigation to the ${sidebarSide === "left" ? "right" : "left"}`}>
            {sidebarSide === "left" ? <PanelRightClose size={17} /> : <PanelLeftClose size={17} />}
          </IconButton>
        </div>

        <div className="rail-section-label">Your space</div>
        <nav className="primary-nav" aria-label="Primary">
          {PRIMARY_NAV_ITEMS.map((item) => (
            <NavButton
              key={item.view}
              active={view === item.view}
              featured={item.view === "chat"}
              onClick={() => changeView(item.view)}
              icon={item.icon}
              label={item.label}
            />
          ))}
        </nav>

        {libraryItem && (
          <nav className="sidebar-secondary-nav" aria-label="Library">
            <NavButton
              active={view === libraryItem.view}
              featured={false}
              onClick={() => changeView(libraryItem.view)}
              icon={libraryItem.icon}
              label={libraryItem.label}
            />
          </nav>
        )}

        <div className="sidebar-footer">
          <button className="profile-button" type="button" onClick={() => setUtilityOpen((open) => !open)} aria-expanded={utilityOpen}>
            <span className="profile-avatar">{initials(userLabel)}</span>
            <span className="identity"><strong>{userLabel}</strong><small>{localMode ? "Private local space" : "Your personal space"}</small></span>
            <Settings2 size={17} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <span className="workspace-eyebrow">THOUGHT PINS <span aria-hidden="true">/</span> YOUR SPACE</span>
            <h1>{viewTitle(view)}</h1>
            <span className="subtle">{viewSubtitle(view)}</span>
          </div>
          <div className="topbar-actions">
            <IconButton onClick={() => toggleTheme()} aria-label={theme === "dark" ? "Switch to light appearance" : "Switch to dark appearance"} title="Appearance">{theme === "dark" ? <Moon size={18} /> : <Sun size={18} />}</IconButton>
            <IconButton className="mobile-settings" onClick={() => setUtilityOpen((open) => !open)} aria-label="Open settings menu" title="Settings"><Settings2 size={18} /></IconButton>
          </div>
        </header>

        {maintenanceMessage && <div className="maintenance-banner" role="status">{maintenanceMessage}</div>}
        {notice && <NoticeBanner notice={notice} clear={clearNotice} />}
        <div className={`view-stage view-stage--${viewStageKind(view)}`} key={view}>{children}</div>
      </main>

      {showGlobalComposer && <GlobalComposer busy={busy} pendingMode={composePending} onSubmit={onGlobalCompose} />}

      <nav className="mobile-tabbar" aria-label="Mobile primary navigation">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <button
            key={item.view}
            className={`${view === item.view ? "active" : ""}${item.view === "chat" ? " featured" : ""}`}
            onClick={() => changeView(item.view)}
            type="button"
            aria-label={item.label}
            aria-current={view === item.view ? "page" : undefined}
            title={item.label}
          >
            <span className="mobile-nav-icon">{item.icon}</span>
            <span className="mobile-nav-label">{item.shortLabel}</span>
          </button>
        ))}
      </nav>

      {utilityOpen && (
        <div className="utility-popover" role="dialog" aria-label="Thought Pins menu">
          <div className="utility-popover-head">
            <strong>More</strong>
            <div>
              <IconButton onClick={() => toggleTheme()} aria-label={theme === "dark" ? "Appearance: dark. Switch to light." : "Appearance: light. Switch to dark."} title={theme === "dark" ? "Appearance: dark - switch to light" : "Appearance: light - switch to dark"}>
                {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
              </IconButton>
              <IconButton onClick={refreshMe} disabled={busy} aria-label="Sync account" title="Sync account"><RefreshCw className={busy ? "spin" : ""} size={16} /></IconButton>
              <IconButton onClick={() => setUtilityOpen(false)} aria-label="Close menu" title="Close"><X size={17} /></IconButton>
            </div>
          </div>
          <nav aria-label="Utilities">
            {UTILITY_NAV_ITEMS.map((item) => (
              <button key={item.view} className={view === item.view ? "active" : ""} onClick={() => changeView(item.view)} type="button">
                {item.icon}<span>{item.label}</span>
              </button>
            ))}
          </nav>
          <button className="utility-logout" type="button" onClick={logout}><LogOut size={17} /><span>Sign out</span></button>
        </div>
      )}
    </div>
  );
}

function NavButton({ active, featured, onClick, icon, label }: { active: boolean; featured: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button className={`${active ? "active" : ""}${featured ? " featured" : ""}`} onClick={onClick} type="button" aria-label={label} aria-current={active ? "page" : undefined}>
      <span className="nav-icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function GlobalComposer({ busy, pendingMode, onSubmit }: { busy: boolean; pendingMode: GlobalComposeMode | null; onSubmit: (text: string, mode: GlobalComposeMode) => Promise<boolean> }) {
  const [mode, setMode] = useState<GlobalComposeMode>("chat");
  const [value, setValue] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const body = value.trim();
    if (!body || busy) return;
    setValue("");
    const sent = await onSubmit(body, mode);
    if (!sent) setValue(body);
  };

  return (
    <form className="global-composer" aria-label="Quick chat or journal composer" onSubmit={submit}>
      {pendingMode && (
        <div className="global-composer-status" role="status" aria-live="polite">
          <Loader2 className="spin" size={15} />
          <span>{pendingMode === "chat" ? "Thinking with your memory" : "Saving to your journal"}</span>
        </div>
      )}
      <button className="composer-mode-button" type="button" disabled={busy} onClick={() => setMode((current) => current === "chat" ? "journal" : "chat")} title="Switch between chat and journal">
        {mode === "chat" ? <ChatGlyph size={17} /> : <Plus size={17} />}
        <span>{mode === "chat" ? "Ask" : "Save"}</span>
      </button>
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={submitFormOnEnter}
        disabled={busy}
        placeholder={mode === "chat" ? "Ask Thought Pins..." : "Write a journal note..."}
        aria-label={mode === "chat" ? "Ask Thought Pins" : "Write a journal note"}
        enterKeyHint="send"
        rows={1}
        maxLength={50000}
      />
      <PrimaryButton disabled={!value.trim() || busy} aria-label={mode === "chat" ? "Send message" : "Save journal note"}>
        {pendingMode ? <Loader2 className="spin" size={17} /> : <Send size={17} />}
      </PrimaryButton>
    </form>
  );
}

function viewStageKind(view: View): "list" | "focus" | "detail" {
  if (view === "chat" || view === "capture") return "focus";
  if (view === "account" || view === "legal" || view === "memory") return "detail";
  return "list";
}

function initials(value: string) {
  return value.split(/\s+|@/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "TP";
}
