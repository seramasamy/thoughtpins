/* Editing one of your own turns, in place.
 *
 * Rewinding a conversation is familiar from every chat product. What differs
 * in a journal is that the turns being discarded may have written something
 * durable, so the note below the field says plainly what survives. People edit
 * a message expecting to undo its consequences; here some of those
 * consequences are their own writing, and quietly deleting that would be
 * worse than leaving it.
 */
import { useEffect, useRef } from "react";
import { submitFormOnEnter } from "../../components/keyboard";

const MIN_ROWS = 2;
const MAX_ROWS = 8;

type Props = {
  messageId: string;
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onCancel: () => void;
};

export function MessageEditor({ messageId, draft, onDraftChange, onSubmit, onCancel }: Props) {
  const fieldRef = useRef<HTMLTextAreaElement | null>(null);

  /* Focus lands at the end rather than the start: an edit is almost always a
     continuation or a correction near the end, not a rewrite from the front. */
  useEffect(() => {
    const field = fieldRef.current;
    if (!field) return;
    field.focus();
    field.setSelectionRange(field.value.length, field.value.length);
  }, [messageId]);

  const rows = Math.min(MAX_ROWS, Math.max(MIN_ROWS, draft.split("\n").length));

  return (
    <form
      className="message-edit"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(draft.trim());
      }}
    >
      <label className="sr-only" htmlFor={`edit-${messageId}`}>
        Edit your message and send it again
      </label>
      <textarea
        id={`edit-${messageId}`}
        ref={fieldRef}
        value={draft}
        rows={rows}
        maxLength={50000}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
          /* Enter sends, Shift+Enter breaks the line — the same contract as the
             main composer, so the muscle memory carries over. */
          submitFormOnEnter(event);
        }}
      />
      <div className="message-edit-actions">
        <button type="button" className="button-quiet" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="button-small" disabled={!draft.trim()}>
          Send again
        </button>
      </div>
      <p className="message-edit-note">
        Replies after this point are replaced. Anything already saved to your journal stays.
      </p>
    </form>
  );
}
