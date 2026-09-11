import { Eye, EyeOff } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";

export function PasswordField({ value, onChange, disabled, registering }: {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  registering: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [revealed, setRevealed] = useState(false);
  const selection = useRef<{ start: number; end: number; direction: "forward" | "backward" | "none" } | null>(null);
  useLayoutEffect(() => {
    const saved = selection.current;
    if (!saved || !input.current) return;
    input.current.focus({ preventScroll: true });
    input.current.setSelectionRange(saved.start, saved.end, saved.direction);
    selection.current = null;
  }, [revealed]);
  return (
    <div className="password-field">
      <label htmlFor={id}>Password</label>
      <div className="password-input-wrap">
        <input
          ref={input} id={id} value={value} disabled={disabled}
          onChange={event => onChange(event.target.value)}
          type={revealed ? "text" : "password"}
          autoComplete={registering ? "new-password" : "current-password"}
          minLength={registering ? 12 : undefined} maxLength={256} required
          aria-describedby={registering ? "password-requirement" : undefined}
          autoCapitalize="none" spellCheck={false}
        />
        <button type="button" className="password-visibility" disabled={disabled}
          aria-label={revealed ? "Hide password" : "Show password"} aria-controls={id}
          aria-pressed={revealed} onClick={() => {
            const field = input.current;
            if (field) selection.current = {
              start: field.selectionStart ?? value.length,
              end: field.selectionEnd ?? value.length,
              direction: field.selectionDirection ?? "none",
            };
            setRevealed(current => !current);
          }}>
          {revealed ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}
