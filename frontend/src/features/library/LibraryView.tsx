import { ArrowUpRight, Archive, BookOpen, CheckCircle2, FileText, FileUp, Link2, RefreshCw, Search, Send, X } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useMemo, useState, useEffect } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { LibraryIngestResponse, LibrarySourceResponse, UploadDestination, UploadIngestResponse } from "../../types";
import { cleanDisplayText, displayStatus, formatShortDate, humanizeIdentifier } from "../../components/format";
import { ContentSkeleton, EmptyState, IconButton, Panel, PanelTitle, PrimaryButton, SecondaryButton, StatusPill, useContentSwap } from "../../components/ui";

type AddMode = "link" | "text" | "file";

export function LibraryView({ token, run }: ScreenProps) {
  const [addMode, setAddMode] = useState<AddMode>("link");
  const [sourceType, setSourceType] = useState("article");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileDestination, setFileDestination] = useState<UploadDestination>("library");
  const [sources, setSources] = useState<LibrarySourceResponse[]>([]);
  const [query, setQuery] = useState("");
  const [last, setLast] = useState<LibraryIngestResponse | null>(null);
  const [lastUpload, setLastUpload] = useState<UploadIngestResponse | null>(null);
  const [selected, setSelected] = useState<LibrarySourceResponse | null>(null);
  const [loaded, setLoaded] = useState(false);
  const swap = useContentSwap(loaded);

  const load = useCallback(async () => {
    const result = await run(() => api.librarySources(token, 100));
    if (result) setSources(result);
    setLoaded(true);
  }, [run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredSources = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return sources;
    return sources.filter((source) => [source.title, source.publisher, source.source_domain, source.author, ...(source.topics || [])]
      .some((value) => String(value || "").toLowerCase().includes(needle)));
  }, [query, sources]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (addMode === "file") {
      if (!file) return;
      const result = await run(
        () => api.uploadFile(token, file, {
          destination: fileDestination,
          title: title.trim() || null,
          caption: text.trim() || null,
          source_type: sourceType,
        }),
        "File added",
      );
      if (result) {
        setLastUpload(result);
        setLast(null);
        clearComposer();
        void load();
      }
      return;
    }

    const result = await run(
      () => api.createLibrarySource(token, {
        source_type: addMode === "link" ? "article" : sourceType,
        title: addMode === "text" ? title.trim() || null : null,
        author: addMode === "text" ? author.trim() || null : null,
        url: addMode === "link" ? url.trim() || null : null,
        text: text.trim() || null,
      }),
      "Source saved",
    );
    if (result) {
      setLast(result);
      setLastUpload(null);
      clearComposer();
      void load();
    }
  };

  const clearComposer = () => {
    setTitle("");
    setAuthor("");
    setUrl("");
    setText("");
    setFile(null);
  };

  const inspect = async (sourceRef: string) => {
    const result = await run(() => api.librarySource(token, sourceRef));
    if (result) setSelected(result);
  };

  const canSubmit = addMode === "file" ? Boolean(file) : addMode === "link" ? Boolean(url.trim()) : Boolean(text.trim());

  return (
    <section className="library-view">
      <div className="library-intro">
        <div>
          <span className="section-label">Reading memory</span>
          <h2>Keep what changes how you think</h2>
          <p>Paste a link, add your own text, or bring in a document. Thought Pins keeps sources separate from your journal while making both available in conversation.</p>
        </div>
      </div>

      <div className="library-layout">
        <form className={`panel library-add mode-${addMode}`} onSubmit={submit}>
          <PanelTitle icon={<Archive size={18} />} title="Add a source" />
          <div className="segmented library-mode" role="tablist" aria-label="Source format">
            <button className={addMode === "link" ? "active" : ""} type="button" onClick={() => setAddMode("link")}><Link2 size={15} />Link</button>
            <button className={addMode === "text" ? "active" : ""} type="button" onClick={() => setAddMode("text")}><FileText size={15} />Text</button>
            <button className={addMode === "file" ? "active" : ""} type="button" onClick={() => setAddMode("file")}><FileUp size={15} />File</button>
          </div>

          <div className="form-stack library-fields">
            {addMode === "link" && (
              <>
                <label>Article link<input value={url} onChange={(event) => setUrl(event.target.value)} type="url" maxLength={4000} placeholder="https://..." autoComplete="url" required /></label>
                <label>Personal note <span className="optional-label">Optional</span><textarea value={text} onChange={(event) => setText(event.target.value)} rows={4} maxLength={200000} placeholder="Why this is worth remembering..." /></label>
              </>
            )}

            {addMode === "text" && (
              <>
                <div className="two-col">
                  <label>Type<select value={sourceType} onChange={(event) => setSourceType(event.target.value)}><option value="article">Article</option><option value="book">Book</option><option value="essay">Essay</option><option value="paper">Paper</option><option value="text">Note</option></select></label>
                  <label>Title<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={512} /></label>
                </div>
                <label>Author <span className="optional-label">Optional</span><input value={author} onChange={(event) => setAuthor(event.target.value)} maxLength={255} /></label>
                <label>Text<textarea value={text} onChange={(event) => setText(event.target.value)} rows={9} maxLength={200000} required /></label>
              </>
            )}

            {addMode === "file" && (
              <>
                <label>Title <span className="optional-label">Optional</span><input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={512} /></label>
                <label className="file-picker">File Upload<input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} required /><span>{file ? file.name : "Choose a document, image, or audio note"}</span></label>
                <label>Save as<select aria-label="Destination" value={fileDestination} onChange={(event) => setFileDestination(event.target.value as UploadDestination)}><option value="library">Reading memory</option><option value="journal">Journal memory</option><option value="auto">Decide automatically</option></select></label>
                <label>Context <span className="optional-label">Optional</span><textarea value={text} onChange={(event) => setText(event.target.value)} rows={3} maxLength={200000} placeholder="Add a note about this file..." /></label>
              </>
            )}
          </div>

          <div className="form-actions">
            <span className="subtle">{text.length ? `${text.length.toLocaleString()} characters` : "Private to your memory"}</span>
            <PrimaryButton disabled={!canSubmit}>{addMode === "file" ? <><FileUp size={16} />Upload File</> : <><Send size={16} />Save Source</>}</PrimaryButton>
          </div>

          {(last || lastUpload) && (
            <div className="library-result" role="status">
              <CheckCircle2 size={18} />
              <div>
                <strong>{lastUpload ? "Last Upload" : "Last Source"}</strong>
                <span>{lastUpload
                  ? `${lastUpload.filename} was added to ${humanizeIdentifier(lastUpload.destination)}.`
                  : last?.status === "processed"
                    ? `${last.title} is ready in your reading memory.`
                    : `${last?.title || "The link"} is saved. Add readable text later for full recall.`}</span>
              </div>
            </div>
          )}
        </form>

        <Panel className="library-browser">
          <PanelTitle icon={<BookOpen size={18} />} title="Your sources" action={<IconButton onClick={load} aria-label="Refresh sources" title="Refresh sources"><RefreshCw size={17} /></IconButton>} />
          <label className="search-field library-search">
            <Search size={16} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search titles, authors, and topics" aria-label="Search sources" />
            {query && <button type="button" onClick={() => setQuery("")} aria-label="Clear search"><X size={15} /></button>}
          </label>
          <div className="source-list content-swap">
            {swap !== "ready" && <ContentSkeleton rows={5} label="Loading saved sources" leaving={swap === "leaving"} />}
            {swap !== "loading" && filteredSources.map((source) => (
              <article className={`source-row${selected?.id === source.id ? " selected" : ""}`} key={source.id}>
                <div className="source-row-copy">
                  <span>{sourceLabel(source)}</span>
                  <strong>{cleanDisplayText(source.title) || source.source_url || "Untitled source"}</strong>
                  <small>{source.chunks} memory {source.chunks === 1 ? "section" : "sections"}{source.published_at ? ` / ${formatShortDate(source.published_at)}` : ""}</small>
                </div>
                <div className="row-actions"><StatusPill status={source.status} /><SecondaryButton onClick={() => inspect(source.id)} type="button">Open</SecondaryButton></div>
              </article>
            ))}
            {swap === "ready" && !filteredSources.length && <EmptyState title={query ? "No matching sources" : "No readings yet"} detail={query ? "Try another title, author, or topic." : "Paste an article link or add a document to begin."} />}
          </div>
        </Panel>
      </div>

      {selected && (
        <Panel className="library-detail">
          <div className="library-detail-header">
            <div>
              <span className="section-label">{sourceLabel(selected)}</span>
              <h2>{cleanDisplayText(selected.title) || "Untitled source"}</h2>
              {selected.author && <p>By {cleanDisplayText(selected.author)}</p>}
            </div>
            <IconButton onClick={() => setSelected(null)} aria-label="Close source details" title="Close"><X size={17} /></IconButton>
          </div>
          {selected.summary && <p className="library-summary">{cleanDisplayText(selected.summary)}</p>}
          <dl className="library-detail-meta">
            <div><dt>Format</dt><dd>{humanizeIdentifier(selected.source_type)}</dd></div>
            <div><dt>Memory sections</dt><dd>{selected.chunks}</dd></div>
            <div><dt>Status</dt><dd>{displayStatus(selected.fetch_status || selected.status)}</dd></div>
            {selected.published_at && <div><dt>Published</dt><dd>{formatShortDate(selected.published_at)}</dd></div>}
          </dl>
          {(selected.topics || []).length > 0 && <div className="pin-taxonomy"><strong>Topics</strong><div>{selected.topics.map((topic) => <span key={topic}>{humanizeIdentifier(topic)}</span>)}</div></div>}
          {(selected.key_concepts || []).length > 0 && <div className="pin-concepts"><strong>Key ideas</strong><p>{selected.key_concepts.slice(0, 10).map(cleanDisplayText).join(" / ")}</p></div>}
          {selected.status !== "processed" && <p className="source-availability">The link and public details are saved. Thought Pins will use an authorized open copy when one is available.</p>}
          {originalSourceUrl(selected) && <a className="source-link" href={originalSourceUrl(selected)} target="_blank" rel="noreferrer">Open original on {sourceLabel(selected)} <ArrowUpRight size={15} /></a>}
        </Panel>
      )}
    </section>
  );
}

function sourceLabel(source: LibrarySourceResponse) {
  return cleanDisplayText(source.publisher || source.source_domain || source.author || humanizeIdentifier(source.source_type));
}

function originalSourceUrl(source: LibrarySourceResponse) {
  return source.canonical_url || source.source_url || source.original_url || "";
}
