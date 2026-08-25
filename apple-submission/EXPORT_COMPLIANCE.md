# Export compliance — Thought Pins

**Decision: the app qualifies for the exemption.**
`ITSAppUsesNonExemptEncryption` is set to `false` in
`mobile/ios/ThoughtPinsNative/Resources/Info.plist`, which is correct and means
App Store Connect will not ask the encryption questions on each upload, and no
annual self-classification report (ERN) is owed.

This file records the reasoning, because the answer is only defensible if
someone can reconstruct what the binary actually does.

---

## What the app binary does with cryptography

There are exactly three uses, all found by grepping the shipped Swift rather
than from memory.

| Use | Where | What it is |
|---|---|---|
| HTTPS | Every `URLSession` call in `APIClient.swift` | TLS performed by the operating system. The app never implements or configures a cipher |
| Keychain | `SessionStore.swift`, via `import Security` | Storing the session with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`. Encryption at rest performed by the operating system |
| SHA-256 | `APIClient.swift:351`, `SHA256.hash(data: chunk)` from CryptoKit | A digest over each upload chunk, sent as `chunk_sha256` so the server can verify the chunk arrived intact |

That is the whole of it. There is no proprietary algorithm, no bundled crypto
library, no key exchange the app performs itself, and nothing the app encrypts
and decrypts on its own behalf.

## Why each one is exempt

Under Category 5 Part 2 of the US Export Administration Regulations, and
Apple's own summary of it:

- **TLS through the OS.** Apple names this explicitly: an app whose encryption
  is limited to what the operating system performs for HTTPS is exempt. The app
  calls `URLSession`; it does not ship or configure a TLS stack.
- **Keychain.** Same reasoning — the encryption is the operating system's, used
  for authentication material.
- **SHA-256.** A hash is not encryption at all. It is one-way, has no key, and
  cannot be reversed, so it is not controlled. Apple lists hashing and digital
  signature among the uses that do not make an app non-exempt.

None of the three is proprietary, and none is encryption the app performs for
its own purposes beyond authentication and transport.

## What is deliberately out of scope

The **backend** encrypts data at rest with Fernet (AES) via the `cryptography`
package — see `src/thoughtpins/crypto.py`. That is server-side and is not part
of the iOS binary. Export classification for an App Store submission concerns
the software Apple distributes, which is the app. The server is not distributed
through Apple and does not change this answer.

## If any of this changes

Re-open this decision, and change `ITSAppUsesNonExemptEncryption`, if the app
ever:

- implements its own encryption of user content on the device (end-to-end
  encrypted journals, an encrypted local database, an encrypted export)
- bundles a third-party crypto library rather than using Apple's frameworks
- performs its own key exchange or certificate pinning with custom crypto

Adding a dependency is the likeliest way this becomes wrong without anyone
noticing, so check it when the dependency list changes.

## What to answer in App Store Connect

Because `ITSAppUsesNonExemptEncryption` is `false` in the Info.plist, the
questions are answered from the binary and are not asked per-upload. If you are
ever asked them manually, the answers are:

- *Does your app use encryption?* — **Yes** (HTTPS).
- *Does it qualify for any of the exemptions?* — **Yes**: the app uses only
  encryption provided by the operating system, and hashing.
- *Is it exempt from export compliance documentation?* — **Yes.** No ERN, no
  annual self-classification report.
