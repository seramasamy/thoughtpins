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

- [ ] Run `python scripts/check_public_export.py`.
- [ ] Run `python scripts/forbidden_scan.py`.
- [ ] Generate the public export from the allowlisted source tree, not by
  uploading the working folder. Use
  `python scripts/create_public_export.py --force`.
- [ ] Verify `.env`, databases, vaults, reports, logs, backups, screenshots with
  private data, local signing records, and `founder/private/` are absent.
- [ ] Inspect the exported archive on a second machine before creating Git
  history.
- [ ] Initialize Git inside the sanitized export, not inside a folder containing
  active secrets.

## Engineering Evidence

- [ ] `python scripts/release_check.py --strict-quality` passes.
- [ ] PostgreSQL RLS passes using the non-owner application role.
- [ ] Web build and Playwright smoke tests pass from a clean dependency install.
- [ ] Android tests/build pass from the checked-in Gradle wrapper.
- [ ] iOS generation and unsigned simulator build pass on current Xcode.
- [ ] Dependency and secret scans pass on the exact exported tree.
- [ ] Architecture budget passes and the debt register matches reality.

## Community Surface

- [x] `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`,
  `CODE_OF_CONDUCT.md`, and `AGENTS.md` are present and internally consistent.
- [x] Issue/PR templates request reproduction, privacy-safe logs, and tests.
- [ ] Private vulnerability reporting is enabled before public issues are open.
- [ ] Branch protection requires test, web, Android, iOS-source, and secret gates.
- [ ] Generated files and local evidence remain excluded from releases.

## Store Separation

Open-source readiness does not imply App Store readiness. Signed archives,
provisioning, App Store Connect credentials, reviewer accounts, screenshots,
and device evidence remain private release artifacts and must never be committed.
