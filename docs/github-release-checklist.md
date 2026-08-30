# GitHub Release Checklist

Language: English | [한국어](github-release-checklist.ko.md)

Use this checklist before publishing `oslab` on GitHub for the first time.

## Public Positioning

- [x] Position `README.md` around a generic OS/VM integration test platform rather than a private product.
- [x] Present `docs/oslab-platform-plan.md` as the public, generic platform plan.
- [x] Use the generic demo suite for the first-run example.
- [x] Keep product-specific content in product-owned or private documentation.
- [x] Preserve the previous product-specific platform plan in private or product-owned documentation.
- [ ] Complete a final audit to remove local lab run IDs, real Proxmox IP addresses, and real node names from public Markdown and media.

## Onboarding

- [x] Provide the initial installation commands.
- [x] Explain how to copy `config/oslab.local.example.yaml` and `config/oslab.local.example.env`.
- [x] Explain where to create a Proxmox API token and how its token ID is formatted.
- [x] State that the Proxmox token guidance is intended for a lab demo and requires a least-privilege review before use on a production or shared cluster.
- [x] Provide the staged preflight flow.
- [x] Provide PowerShell, Python, and C demo commands and a demo catalog.
- [x] Explain how to inspect results under `runs/<run-id>/`.
- [x] Explain the purposes of the JUnit, JSON, and HTML reports.
- [x] Provide a manual recovery runbook for stale VMs and VMID ranges.
- [x] Explain the CI pattern that preserves `runs/**` artifacts even when a job fails.
- [x] Organize the README as a 30-second overview, overview animation, one step-by-step video covering Dashboard → 10-step workflow → real Proxmox and Windows footage → cleanup → Results, quick start, current support, and detailed documentation.
- [x] Keep the key message, commands, and supported scope aligned between the English and Korean READMEs.
- [x] Validate the README links, language switches, and all 14 English/Korean public document pairs with `scripts/check-doc-links.ps1`.

## Repository Hygiene

- [x] Ignore `config/oslab.local.yaml` and `config/oslab.local.env`.
- [x] Ignore `runs/`.
- [x] Do not ignore demo artifact files under `validation/artifacts/`.
- [x] Keep real secrets out of example environment files.
- [x] Ignore timestamped dummy outputs produced by development, browser, and authoring smoke tests.
- [x] Separate product-specific overlays that must not be included in the public repository under `private/`, `*.local.*`, or `*.private.yaml` conventions.
- [x] Track README media under `docs/media/` and document its regeneration procedure in `docs/media/DEMO_SCRIPT.md`.
- [x] Use only deterministic fixtures for the overview, workflow, and Dashboard demos.
- [x] Verify in a fresh Chromium/Playwright capture that Dashboard recording blocks service workers and blocks HTTP and WebSocket traffic using an allowlist.
- [x] Record real lab footage only during a dedicated run, crop the resource tree, node, account, IP address, and unrelated task history, and clean up the recording VM afterward.
- [x] Revalidate the SHA-256 hashes of the four real-lab source images and two run-evidence records, along with `sameRun`, `guestPowerShellMatchesRun`, `sensitiveRegionsReviewed`, `cleanupVerified`, and cleanup `resourceAbsent`, against `source-approval.json`.
- [x] Compare the final real-lab MP4, GIF, and poster hashes, private run-evidence hashes, execution summary, `cleanup.resourceAbsent`, and `privacy.manualPublicFrameReview` against the public attestation.
- [x] Mark the boundaries between the Dashboard fixture, explainer fixture, separately recorded real footage, and fixture Results in the single step-by-step video with source badges; record its title and lower-third, source and output hashes, 11-segment EDL, 10 transitions, inherited cleanup status, and independent visual review in a separate attestation.
- [ ] Add internal product markers and private domain markers to `config/public-release-blocklist.local.txt`.
- [x] Run `scripts/check-public-release.ps1 -IncludeUntracked` to check tracked and untracked files for the default public-blocking markers and dummy outputs. (Adding the local private-marker blocklist remains incomplete.)
- [ ] Exclude the modified `apps/api/prisma/prisma/dev.db` from the public commit and replace it with a distribution fixture database that contains no session tokens, password hashes, or execution metadata.
- [ ] Run one more secret scan before the final commit.

## Validation

- [x] Demo scenario schema validation passes.
- [ ] Rerun the local unit test suite successfully against the public candidate. (Tests that reference removed product-specific scenarios still need cleanup.)
- [ ] Pass the public release audit script with the local private-marker blocklist.
- [ ] Add a GitHub Actions workflow.
- [ ] Add a CI badge to the README.

## Known Limits For First Release

- The Windows/Proxmox/QEMU Guest Agent path is the implemented path.
- Linux support is documented as a target, but not the first complete implementation path.
- WinRM/SSH credentials in config are reserved for future guest channels.
- Proxmox least-privilege role guidance should be tightened before production cluster use.
