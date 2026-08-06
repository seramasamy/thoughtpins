/* What an edit did not throw away.
 *
 * Rewinding a conversation removes the replies below it. If one of those turns
 * had already saved a journal entry, that entry is still there — deleting
 * someone's writing because they reworded a question would be destroying work
 * they never asked to lose.
 *
 * Saying so once, plainly, is the whole job. It is not an error and not a task
 * to complete, so it reads as a quiet statement and dismisses on
 * acknowledgement rather than lingering as an unread badge.
 */

type Props = {
  count: number;
  onDismiss: () => void;
};

export function KeptEntryNotice({ count, onDismiss }: Props) {
  if (count < 1) return null;

  return (
    <div className="chat-kept-notice" role="status">
      <p>
        {count === 1
          ? "The message you replaced had already saved a journal entry. It is still in your journal."
          : `The messages you replaced had already saved ${count} journal entries. They are still in your journal.`}
      </p>
      <button type="button" className="button-quiet" onClick={onDismiss}>
        Got it
      </button>
    </div>
  );
}
