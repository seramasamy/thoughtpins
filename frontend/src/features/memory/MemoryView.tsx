import { ArrowUpRight, Landmark, MapPin, RefreshCw, Search, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { MemoryCardDetailResponse, MemoryCardResponse, MemoryCardsResponse } from "../../types";
import { cleanDisplayText, displayEntityName, displayReferenceTitle, displayStatus, formatShortDate, humanizeIdentifier, truncate } from "../../components/format";
import { ContentSkeleton, EmptyState, IconButton, KeyValue, Panel, PanelTitle, StatusPill, useContentSwap } from "../../components/ui";
import { runOnEnter } from "../../components/keyboard";

const SECTIONS = ["people", "places", "projects", "organizations", "events", "things", "concepts", "all"];

export function MemoryView({
  token,
  run,
  initialSection = "people",
  lockedSection = false,
}: ScreenProps & { initialSection?: string; lockedSection?: boolean }) {
  const [section, setSection] = useState(initialSection);
  const [query, setQuery] = useState("");
  const [cards, setCards] = useState<MemoryCardsResponse | null>(null);
  const [selected, setSelected] = useState<MemoryCardDetailResponse | null>(null);
  const swap = useContentSwap(cards !== null);

  const load = useCallback(async () => {
    const result = await run(() => api.memoryCards(token, section, query, 36));
    if (result) setCards(result);
  }, [query, run, section, token]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSelected(null);
  }, [section]);

  useEffect(() => {
    const first = cards?.items[0];
    if (selected || !first) return;
    let active = true;
    void run(() => api.memoryCard(token, first.id)).then((detail) => {
      if (active && detail) setSelected(detail);
    });
    return () => { active = false; };
  }, [cards, run, selected, token]);

  const inspect = async (card: MemoryCardResponse) => {
    const detail = await run(() => api.memoryCard(token, card.id));
    if (detail) setSelected(detail);
  };

  return (
    <section className={`memory-layout memory-${section}`}>
      <Panel className="memory-browser">
        <div className="memory-view-heading">
          <div className="memory-heading-icon">{section === "people" ? <UserRound size={20} /> : section === "places" ? <MapPin size={20} /> : <Landmark size={20} />}</div>
          <div>
            <span className="eyebrow">Living index</span>
            <h2>{section === "people" ? "People in your life" : section === "places" ? "Places in your memory" : "Memory cards"}</h2>
            <p>{section === "people" ? "A relationship view built from the details and moments you have saved." : section === "places" ? "A personal atlas of where things happened and who was there." : "Browse the people, places, projects, events, and concepts connected across your memory."}</p>
          </div>
          <IconButton onClick={load} aria-label="Refresh memory" title="Refresh memory"><RefreshCw size={17} /></IconButton>
        </div>
        <div className="memory-controls">
          {!lockedSection && (
            <div className="segmented compact-segments" role="group" aria-label="Memory section">
              {SECTIONS.map((item) => (
                <button key={item} aria-pressed={section === item} className={section === item ? "active" : ""} onClick={() => setSection(item)} type="button">{item}</button>
              ))}
            </div>
          )}
          <label className="search-field">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => runOnEnter(event, () => { const first = cards?.items[0]; if (first) void inspect(first); })} placeholder="Search memory" aria-label="Search memory" enterKeyHint="search" />
          </label>
        </div>
        <div className="memory-card-grid content-swap stagger">
          {swap !== "ready" && <ContentSkeleton rows={5} label="Loading memory cards" leaving={swap === "leaving"} />}
          {swap !== "loading" && (cards?.items || []).map((card) => (
            <button className={`memory-card${selected?.id === card.id ? " selected" : ""}`} key={card.id} onClick={() => inspect(card)} type="button" aria-pressed={selected?.id === card.id}>
              <span className="memory-card-avatar" aria-hidden="true">
                {section === "places" ? <MapPin size={19} /> : initials(displayEntityName(card.name))}
              </span>
              <div className="memory-card-head">
                <strong>{displayEntityName(card.name)}</strong>
                <StatusPill status={card.type} />
              </div>
              <p>{truncate(cleanDisplayText(card.subtitle) || "No summary yet.", 180)}</p>
              <div className="statline">
                <span><strong>{card.memory_count}</strong> memories</span>
                <span><strong>{card.mention_count}</strong> mentions</span>
                <span><strong>{card.relationship_count}</strong> connections</span>
              </div>
            </button>
          ))}
          {swap === "ready" && cards !== null && !cards.items.length && <EmptyState title="No memory cards yet" detail="Chat or capture entries to create people, places, projects, and concepts." />}
        </div>
      </Panel>
      <Panel className="memory-detail">
        <PanelTitle icon={section === "places" ? <MapPin size={18} /> : <Landmark size={18} />} title="Memory profile" />
        {cards === null ? <ContentSkeleton rows={6} label="Loading memory profile" /> : selected ? (
          <div className="stack compact-stack">
            <div className="memory-detail-identity">
              <span className="memory-card-avatar">{section === "places" ? <MapPin size={19} /> : initials(displayEntityName(selected.name))}</span>
              <div><span className="eyebrow">{humanizeIdentifier(selected.type)}</span><h3>{displayEntityName(selected.name)}</h3></div>
            </div>
            {selected.subtitle && <p className="memory-detail-summary">{cleanDisplayText(selected.subtitle)}</p>}
            <div className="profile-metrics" aria-label="Memory summary">
              <div><strong>{selected.memory_count}</strong><span>Memories</span></div>
              <div><strong>{selected.mention_count}</strong><span>Mentions</span></div>
              <div><strong>{selected.relationship_count}</strong><span>Connections</span></div>
            </div>
            <p className="profile-last-seen">Last mentioned {formatShortDate(selected.last_seen)}</p>
            {section === "places" && (
              <a className="source-link" href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(selected.name)}`} target="_blank" rel="noreferrer">
                Open in Maps <ArrowUpRight size={15} />
              </a>
            )}
            <div className="detail-section">
              <strong>Recent memories</strong>
              {(selected.all_memories || []).slice(0, 8).map((memory) => (
                <p key={memory.id || `${memory.date}-${memory.text}`}>{cleanDisplayText(memory.text)}</p>
              ))}
              {!selected.all_memories?.length && <p className="detail-empty">No memories connected yet.</p>}
            </div>
            <div className="detail-section">
              <strong>Relationships</strong>
              {selected.relationships.map((relationship, index) => (
                <p className="relationship-row" key={`${relationship.type}-${relationship.other}-${index}`}>
                  <span>{relationshipLabel(relationship.type, selected.type)}</span>
                  <strong>{displayEntityName(relationship.other)}</strong>
                </p>
              ))}
              {!selected.relationships.length && <p className="detail-empty">No relationships connected yet.</p>}
            </div>
            <div className="detail-section">
              <strong>Timeline</strong>
              {(selected.timeline || []).slice(0, 8).map((item) => (
                <p className="timeline-row" key={`${item.date}-${item.label}`}><time>{formatShortDate(item.date)}</time><span>{truncate(cleanDisplayText(item.label), 220)}</span></p>
              ))}
              {!selected.timeline?.length && <p className="detail-empty">No dated moments yet.</p>}
            </div>
            <div className="detail-section">
              <strong>Source documents</strong>
              {(selected.source_documents || []).slice(0, 6).map((source) => (
                <p className="source-reference-row" key={source.id}><strong>{cleanDisplayText(source.title)}</strong><span>{humanizeIdentifier(source.source_type)} / {displayStatus(source.status)}</span></p>
              ))}
              {!selected.source_documents?.length && <p className="detail-empty">No sources connected yet.</p>}
            </div>
            <details className="profile-provenance">
              <summary>About this memory</summary>
              <KeyValue label="Type" value={humanizeIdentifier(selected.type)} />
              <KeyValue label="Memories" value={selected.memory_count} />
              <KeyValue label="Mentions" value={selected.mention_count} />
              <KeyValue label="Relationships" value={selected.relationship_count} />
              {selected.salience_model_version && <KeyValue label="Prominence" value={humanizeIdentifier(selected.salience_tier)} />}
              <KeyValue label="Last seen" value={formatShortDate(selected.last_seen)} />
              <KeyValue label="Confidence" value={humanizeIdentifier(String(selected.provenance?.confidence || "unknown"))} />
              <KeyValue label="Archive reference" value={displayReferenceTitle(selected.obsidian_path, displayEntityName(selected.name))} />
            </details>
          </div>
        ) : (
          <EmptyState title="Select a card" detail="Choose a card to revisit the memories and moments connected to it." />
        )}
      </Panel>
    </section>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "TP";
}

function relationshipLabel(type: string, entityType: string) {
  if (type.toLowerCase() === "met_at" && entityType.toLowerCase() === "place") return "Met here with";
  return humanizeIdentifier(type);
}
