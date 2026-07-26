export type ValidationIssue = {
  field: string;
  code: string;
  message: string;
};

export function normalizeJournalText(value: string): string {
  return value.replace(/\r\n/g, "\n").trim();
}

export function validateJournalText(value: string): ValidationIssue[] {
  const text = normalizeJournalText(value);
  const issues: ValidationIssue[] = [];
  if (!text) {
    issues.push({ field: "text", code: "required", message: "Entry text is required." });
  }
  if (text.length > 50_000) {
    issues.push({ field: "text", code: "too_long", message: "Entry must be 50,000 characters or fewer." });
  }
  return issues;
}

export function validateEmail(value: string): ValidationIssue[] {
  const email = value.trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return [{ field: "email", code: "invalid", message: "Enter a valid email address." }];
  }
  return [];
}

export function validatePassword(value: string): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (value.length < 12) {
    issues.push({ field: "password", code: "too_short", message: "Password must be at least 12 characters." });
  }
  if (!/\s/.test(value) && !/[0-9]/.test(value)) {
    issues.push({
      field: "password",
      code: "too_weak",
      message: "Use a longer passphrase or include numbers.",
    });
  }
  return issues;
}
