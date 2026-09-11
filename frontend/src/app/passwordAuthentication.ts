import { api } from "../api";

type PasswordAttempt = {
  register: boolean;
  identifier: string;
  email: string;
  phone: string;
  password: string;
  legalVersion: string;
};

/** Resume a confirmed registration when login or consent delivery needs retry. */
export function createPasswordAuthentication() {
  const registeredContacts = new Set<string>();
  return async (attempt: PasswordAttempt) => {
    const email = attempt.email.trim();
    const phone = attempt.phone.trim();
    const contact = JSON.stringify([email, phone]);
    if (attempt.register && !registeredContacts.has(contact)) {
      await api.register({ email: email || null, phone: phone || null, password: attempt.password });
      // Remember only a server-confirmed creation, scoped to this mounted form.
      // Credentials remain in the submitted closure and never enter storage.
      registeredContacts.add(contact);
    }
    const tokens = await api.login(attempt.identifier.trim(), attempt.password);
    if (attempt.register) {
      await Promise.all([
        api.acceptLegalDocument(tokens.access_token, "privacy", attempt.legalVersion),
        api.acceptLegalDocument(tokens.access_token, "terms", attempt.legalVersion),
        api.acceptLegalDocument(tokens.access_token, "ai_disclosure", attempt.legalVersion),
      ]);
    }
    return tokens;
  };
}
