import { Star, X } from "lucide-react";

type ImportanceRatingProps = {
  value: number | null;
  onChange?: (value: number | null) => void;
  disabled?: boolean;
  readOnly?: boolean;
  compact?: boolean;
};

export function ImportanceRating({
  value,
  onChange,
  disabled = false,
  readOnly = false,
  compact = false,
}: ImportanceRatingProps) {
  const label = value === null ? "Unrated" : `${value} out of 5`;

  return (
    <div className={`importance-rating${compact ? " compact" : ""}${readOnly ? " read-only" : ""}`}>
      <span className="importance-label">Importance <small>{label}</small></span>
      <div className="importance-stars" role={readOnly ? undefined : "group"} aria-label={readOnly ? `Importance: ${label}` : "Rate entry importance"}>
        {[1, 2, 3, 4, 5].map((rating) => (
          readOnly ? (
            <Star key={rating} size={compact ? 14 : 17} aria-hidden="true" className={value !== null && rating <= value ? "filled" : ""} />
          ) : (
            <button
              key={rating}
              type="button"
              className={value !== null && rating <= value ? "filled" : ""}
              aria-label={`Set importance to ${rating} out of 5`}
              aria-pressed={value === rating}
              title={`${rating} out of 5`}
              disabled={disabled}
              onClick={() => onChange?.(rating)}
            >
              <Star size={17} aria-hidden="true" />
            </button>
          )
        ))}
        {!readOnly && value !== null && (
          <button
            type="button"
            className="importance-clear"
            aria-label="Clear importance rating"
            title="Clear rating"
            disabled={disabled}
            onClick={() => onChange?.(null)}
          >
            <X size={16} aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
