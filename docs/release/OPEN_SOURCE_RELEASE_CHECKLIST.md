# Open-Source Release Checklist

Thought Pins can remain offline until the owner chooses to publish. Running this
checklist does not push code or create a remote repository.

## Blocking Decisions

- [x] Apache-2.0 selected and declared in `LICENSE` and `pyproject.toml`. Confirm
  this owner/legal choice once more before the first public push.
- [ ] Choose the public repository owner and private security-reporting route.
- [ ] Decide whether the founder adapter's two public runbooks remain in the
  public tree or move to a separate private repository.
- [ ] Rotate every credential ever used in the local workspace before public
  release, even if scanners report that it is absent from the export.

## Public Export

- [x] Run `python scripts/check_public_export.py`.
- [x] Run `python scripts/forbidden_scan.py`.
- [x] Generate the public export from the allowlisted source tree, not by
  uploading the working folder. Use
  `python scripts/create_public_export.py --force`.
  Verified 2026-08-06: 808 files, 5.6 MB,
  sha256 `bee4486956fdc6223ce87599cf3285759ebbcb4e8b7f6aef6d3a257deb1d6dc5`.
- [x] Verify `.env`, databases, vaults, reports, logs, backups, screenshots with
  private data, local signing records, and `founder/private/` are absent.
  Verified against the extracted archive, not the working tree: no `.env`
  (only the four `.env.example` templates), no database, backup, report or
  private founder file, and no credential-shaped string. The one pattern hit
  is `PROOF_CURRENT_PASSWORD = "current_password"`, a constant name.
- [ ] Inspect the exported archive on a second machine before creating Git
  history.
- [~] Initialize Git inside the sanitized export, not inside a folder containing
  active secrets. **Overtaken by events and cannot be satisfied as written.**
  History was created in the working folder and pushed to a private GitHub
  repository on 2026-08-01, so the export-first sequence this item describes is
  no longer available. Audited on 2026-08-09 in place of it, across all 76
  commits: `.env` was never added, no database, vault, log, backup or report
  file was ever committed, no private-looking file was ever deleted, and no diff
  in any commit matches a Telegram bot token, an `sk-` key, an AWS key id, a
  GitHub token, a PEM private key, or an `api_key`/`jwt_secret`/`password`
  assignment. The working tree passes the same scan. The residual risk this item
  guarded against is therefore believed closed, but it was closed by inspection
  after the fact rather than by construction, which is weaker. Rotating
  credentials before publishing (below) remains the compensating control.

## Engineering Evidence

- [ ] `python scripts/release_check.py --strict-quality` passes.
- [ ] PostgreSQL RLS passes using the non-owner application role.
- [ ] Web build and Playwright smoke tests pass from a clean dependency install.
- [ ] Android tests/build pass from the checked-in Gradle wrapper.
- [ ] iOS generation and unsigned simulator build pass on current Xcode.
- [ ] Dependency and secret scans pass on the exact exported tree.
- [x] Architecture budget passes and the debt register matches reality.

## Community Surface

- [x] `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`,
  `CODE_OF_CONDUCT.md`, and `AGENTS.md` are present and internally consistent.
- [x] Issue/PR templates request reproduction, privacy-safe logs, and tests.
- [ ] Private vulnerability reporting is enabled before public issues are open.
- [ ] Branch protection requires test, web, Android, iOS-source, and secret gates.
  Blocked while private: GitHub restricts protected branches to Pro or public
  repositories. It is free the moment the repository is published, and CI now
  enforces 26 gates rather than 11, so there is something worth requiring.
- [ ] Generated files and local evidence remain excluded from releases.

## Store Separation

Open-source readiness does not imply App Store readiness. Signed archives,
provisioning, App Store Connect credentials, reviewer accounts, screenshots,
and device evidence remain private release artifacts and must never be committed.
