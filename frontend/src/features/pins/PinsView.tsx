import { ArrowUpRight, BookOpen, FileUp, Link2, Pin, Plus, RefreshCw, Search, Sparkles, X } from "lucide-react";
import type { ChangeEvent, FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { LibrarySourceResponse } from "../../types";
import { cleanDisplayText, displayStatus, formatShortDate, humanizeIdentifier } from "../../components/format";
import { ContentSkeleton, EmptyState, IconButton, PrimaryButton, StatusPill, useContentSwap } from "../../components/ui";
import { runOnEnter } from "../../components/keyboard";

export function PinsView({ token, run }: ScreenProps) {
  const [sources, setSources] = useState<LibrarySourceResponse[]>([]);
  const [selected, setSelected] = useState<LibrarySourceResponse | null>(null);
  const [query, setQuery] = useState("");
  const [capture, setCapture] = useState("");
  const [loaded, setLoaded] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const swap = useContentSwap(loaded);

  const load = useCallback(async () => {
    const result = await run(() => api.librarySources(token, 100));
    if (result) setSources(result);
    setLoaded(true);
  }, [run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return sources;
    return sources.filter((source) => [source.title, source.source_domain, source.author, source.summary, source.source_type]
      .some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, sources]);

  const savePin = async (event: FormEvent) => {
    event.preventDefault();
    const value = capture.trim();
    if (!value) return;
    const isUrl = /^https?:\/\/\S+$/i.test(value);
    const result = await run(() => api.createLibrarySource(token, {
      url: isUrl ? value : null,
      text: isUrl ? null : value,
      source_type: isUrl ? "article" : "note",
    }), isUrl ? "Link pinned" : "Note pinned");
    if (result) {
      setCapture("");
      await load();
    }
  };

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const result = await run(() => api.uploadFile(token, file, { destination: "library", source_type: "document" }), "Document pinned");
    event.target.value = "";
    if (result) await load();
  };

  const openSource = async (source: LibrarySourceResponse) => {
    const detail = await run(() => api.librarySource(token, source.id));
    if (detail) setSelected(detail);
  };

  return (
    <section className="pins-view">
      <div className="pins-heading">
        <div>
          <span className="eyebrow"><Pin size={14} /> Your collected mind</span>
          <h2>Things worth returning to</h2>
          <p>Articles, books, documents, and ideas stay distinct from lived memories, but remain available in conversation.</p>
        </div>
        <IconButton onClick={load} aria-label="Refresh pins" title="Refresh pins"><RefreshCw size={17} /></IconButton>
      </div>

      <form className="pin-capture" onSubmit={savePin}>
        <div className="pin-capture-icon"><Plus size={18} /></div>
        <input value={capture} onChange={(event) => setCapture(event.target.value)} placeholder="Paste a link or note..." aria-label="New pin" enterKeyHint="done" />
        <input ref={fileRef} className="visually-hidden" type="file" onChange={upload} aria-label="Choose a document to pin" />
        <IconButton type="button" onClick={() => fileRef.current?.click()} aria-label="Upload a document" title="Upload a document"><FileUp size={17} /></IconButton>
        <PrimaryButton disabled={!capture.trim()} aria-label="Save pin"><Pin size={16} />Pin</PrimaryButton>
      </form>

      <div className="pins-toolbar">
        <label className="search-field pin-search">
          <Search size={16} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => runOnEnter(event, () => { const first = filtered[0]; if (first) void openSource(first); })} placeholder="Search everything you have read" aria-label="Search pins" enterKeyHint="search" />
          {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={15} /></button>}
        </label>
        <span aria-live="polite">{filtered.length} {filtered.length === 1 ? "pin" : "pins"}</span>
      </div>

      <div className={selected ? "pins-layout has-detail" : "pins-layout"}>
        <div className="pin-grid content-swap stagger">
          {swap !== "ready" && <ContentSkeleton rows={5} label="Loading pins" leaving={swap === "leaving"} />}
          {swap !== "loading" && filtered.map((source) => (
            <button className="pin-card" type="button" key={source.id} onClick={() => openSource(source)}>
              <div className="pin-card-top">
                <span className={`source-icon source-${source.source_type}`}>
                  {source.source_url ? <Link2 size={17} /> : <BookOpen size={17} />}
                </span>
                <StatusPill status={source.status} />
              </div>
              <div className="pin-card-copy">
                <span>{sourceLabel(source)}</span>
                <h3>{cleanDisplayText(source.title) || source.source_url || "Untitled pin"}</h3>
                <p>{cleanDisplayText(source.summary) || "Saved to your source memory and ready to surface when relevant."}</p>
              </div>
              <footer>
                <span>{source.chunks} memory {source.chunks === 1 ? "section" : "sections"}{source.published_at ? ` / ${formatShortDate(source.published_at)}` : ""}</span>
                <ArrowUpRight size={15} />
              </footer>
            </button>
          ))}
          {swap === "ready" && !filtered.length && <EmptyState title={query ? "No matching pins" : "Nothing pinned yet"} detail={query ? "Try a different phrase." : "Paste an article, upload a document, or write a note above."} />}
        </div>

        {selected && (
          <aside className="pin-detail">
            <header>
              <span className="source-icon"><Sparkles size={17} /></span>
              <IconButton onClick={() => setSelected(null)} aria-label="Close pin detail" title="Close"><X size={17} /></IconButton>
            </header>
            <span className="eyebrow">{sourceLabel(selected)}</span>
            <h2>{cleanDisplayText(selected.title) || "Untitled pin"}</h2>
            {selected.author && <p className="pin-author">By {cleanDisplayText(selected.author)}</p>}
            <p className="pin-summary">{cleanDisplayText(selected.summary) || "This source is saved and indexed for memory-backed conversation."}</p>
            <dl className="pin-meta">
              <div><dt>Type</dt><dd>{humanizeIdentifier(selected.source_type)}</dd></div>
              <div><dt>Sections</dt><dd>{selected.chunks}</dd></div>
              <div><dt>Status</dt><dd>{displayStatus(selected.fetch_status || selected.status)}</dd></div>
              {selected.published_at && <div><dt>Published</dt><dd>{formatShortDate(selected.published_at)}</dd></div>}
            </dl>
            {(selected.topics || []).length > 0 && (
              <div className="pin-taxonomy">
                <strong>Topics</strong>
                <div>{(selected.topics || []).map((topic) => <span key={topic}>{humanizeIdentifier(topic)}</span>)}</div>
              </div>
            )}
            {(selected.key_concepts || []).length > 0 && (
              <div className="pin-concepts">
                <strong>Key ideas</strong>
                <p>{(selected.key_concepts || []).slice(0, 8).map(cleanDisplayText).join(" / ")}</p>
              </div>
            )}
            {selected.status !== "processed" && (
              <p className="source-availability">The link and public details are saved. Thought Pins will use an authorized open copy when one is available.</p>
            )}
            {originalSourceUrl(selected) && <a className="source-link" href={originalSourceUrl(selected)} target="_blank" rel="noreferrer">Open original on {sourceLabel(selected)} <ArrowUpRight size={15} /></a>}
          </aside>
        )}
      </div>
    </section>
  );
}

function sourceLabel(source: LibrarySourceResponse) {
  return cleanDisplayText(source.publisher || source.source_domain || source.author || humanizeIdentifier(source.source_type));
}

function originalSourceUrl(source: LibrarySourceResponse) {
  return source.canonical_url || source.source_url || source.original_url || "";
}
