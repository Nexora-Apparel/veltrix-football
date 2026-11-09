# Provider Qualification Evidence Review Contract

Status: REQUIRED GATE — offline evidence review design. This contract does not authorize provider requests, production imports, prediction publication, scheduling changes, or PR merges.

## 1. Purpose

Prevent a self-declared `qualification_status: qualified` registry row from admitting a provider/competition into daily fixture selection. A registry entry is valid only after its underlying GitHub Actions run and downloadable evidence artifact have been independently verified.

## 2. Required evidence bundle

Each reviewed qualification must identify:

- Repository full name.
- GitHub Actions workflow run ID.
- Workflow file path and workflow name.
- Run event, conclusion, and completion timestamp.
- Exact head branch and commit SHA.
- Artifact ID, artifact name, artifact digest, and download URL/reference.
- Locally computed SHA-256 of the downloaded artifact bytes.
- Qualification report path inside the artifact.
- Provider and competition key(s) covered.
- Final/scheduled windows and pagination-completeness evidence.
- Input, accepted, quarantined, invalid, duplicate, and truncated counts.
- Reviewer timestamp and reviewer identity.

No credential, authorization header, raw API key, or unrestricted provider payload may be copied into the registry.

## 3. Trust boundary

The local artifact JSON is untrusted input. Its own `acceptance_pass`, `qualified`, counts, run ID, commit, and artifact hash fields are claims, not proof.

A reviewer must obtain run metadata and artifact metadata directly from GitHub's authenticated API (or an equivalent trusted GitHub CLI/API client) for the configured repository. A hand-authored metadata JSON file is not sufficient.

The reviewer must verify:

1. The run belongs to the configured repository.
2. The workflow path is on an explicit allowlist for provider qualification.
3. The run is completed with conclusion `success`.
4. The event is an explicitly permitted manual dispatch; push, pull-request, fork, or unknown events are rejected unless a future policy explicitly allows them.
5. The branch and head SHA match the intended qualification source and reviewed code.
6. The artifact belongs to that exact run and is not expired.
7. The downloaded artifact digest matches GitHub's artifact digest where supplied, and its locally computed SHA-256 is recorded.
8. The report schema and report integrity hash validate.
9. The report's provider, competition scope, windows, pagination, and accounting are internally consistent.
10. No invalid, duplicate, ambiguous, or truncated rows exist for the qualification scope.
11. Every claimed competition has actual accepted observations in the required checks; an empty scheduled window is recorded as empty and is not treated as a fixture-coverage failure by itself.
12. No report or workflow output indicates production writes, imports, canonical merges, checkpoints, or prediction publication.

If GitHub metadata, artifact digest, report, or any required field is unavailable, the result is `pending_review` or `rejected`, never `qualified`.

## 4. Qualification scope

Qualification is scoped to a provider, competition key, season (when applicable), endpoint family, and measured date window. Evidence for one competition or endpoint does not qualify another. A bounded rolling-window sample is not a claim of full-season completeness.

Provider data products must be qualified independently: fixtures/results, lineups, events, xG/shot data, Elo, and odds. Fixture qualification does not imply metric or odds coverage.

## 5. Registry admission

The production selection registry must contain only reviewer-generated entries that reference:

- Verified workflow run ID and head SHA.
- Verified artifact ID and artifact digest.
- Local artifact SHA-256.
- Qualification report hash.
- Exact provider/competition/season/endpoint scope.
- Pagination-complete and quality counters.
- Review decision and review timestamp.

A free-form evidence URL, manually supplied run ID, manually supplied SHA-256, or self-declared `qualification_status` alone is insufficient.

The selection code must fail closed when a registry entry lacks a valid reviewer attestation. The empty template continues to select zero fixtures.

## 6. Operational constraints

- Evidence review is offline with respect to football providers; it must not call StrikerAPI, 5DollarFootballAPI, or GOAL API.
- GitHub metadata access is read-only.
- Do not spend provider credits during unit tests or evidence review.
- Do not connect to Neon or write canonical data.
- Do not merge PR #42 or PR #43.
- Do not reconnect prediction publication, Telegram delivery, or the 06:00 WAT schedule until the preceding roadmap phases and release gates are complete.

## 7. Acceptance tests

The reviewer implementation must reject:

- A self-declared qualified registry row without a reviewer attestation.
- A run ID that does not resolve in the configured repository.
- A run from the wrong workflow, branch, commit, event, or conclusion.
- An artifact not attached to the verified run.
- An artifact whose digest or local SHA-256 differs.
- A tampered or malformed report.
- Missing competitions, incomplete pagination, invalid/duplicate/truncated records, or inconsistent accounting.
- Evidence with nonzero prohibited side effects.
- Evidence whose coverage scope is broader than the actual report.

It must accept only a fully verified, narrowly scoped evidence bundle and must preserve the exact scope in the generated registry entry.

## 8. Implemented offline reviewer

Implementation entry point: `scripts/review_provider_qualification.py`.

The reviewer uses the authenticated GitHub CLI session and GitHub Actions read-only API endpoints. It does not call football providers. It requires:

- `--repository Nexora-Apparel/veltrix-football`
- `--run-id <completed workflow run ID>`
- `--expected-branch <exact qualification branch>`
- `--expected-head-sha <exact 40-character reviewed commit SHA>`
- `--reviewer <reviewer identifier>`
- Optional `--output <registry JSON path>`

Example (run only after a real, successful manual qualification workflow exists):

```bash
python scripts/review_provider_qualification.py \
  --repository Nexora-Apparel/veltrix-football \
  --run-id 123456789 \
  --expected-branch phase-3/strikerapi-readonly-qualification \
  --expected-head-sha <40-character-reviewed-commit-sha> \
  --reviewer <reviewer-id> \
  --output data/provider_qualification_registry.reviewed.json
```

The script fetches run and artifact metadata from GitHub, requires exactly one expected artifact, downloads the ZIP through the GitHub artifact endpoint, compares the local archive SHA-256 with GitHub's artifact digest, locates exactly one coverage report, and validates all 34 competition/status checks before emitting a reviewer-attested registry. A failed check emits no registry.

The generated registry is a review record, not an assertion of complete season coverage. Its attestation is bound to the workflow run, branch, commit, artifact ID/digest, local report hash, and exact measured competition scope. It remains subject to normal repository review and must not be hand-edited to widen scope.

The StrikerAPI reviewer remains provider-specific. A separate 5Dollar reviewer is implemented at `scripts/review_fivedollar_qualification.py`, using:
- Workflow: `.github/workflows/qualify-fivedollar-competitions.yml`
- Artifact: `fivedollar-competition-qualification`
- Report: `fivedollar_competition_qualification.json`
- Exact branch: `phase-3/budget-aware-acquisition-contract`
- Validator: `app/fivedollar_qualification_report.py`
- Registry signer: `app/fivedollar_qualification_review.py`

The 5Dollar reviewer independently fetches the manual run and artifact metadata from GitHub, verifies the artifact digest and report SHA-256, validates the complete account catalogue and per-competition pagination/accounting, and emits one HMAC-attested registry entry per measured competition. It rejects non-qualifying reports and never calls football providers. The daily selection registry validator has separate allowlisted workflow, branch, and artifact identity for 5Dollar. Do not reuse the StrikerAPI report validator for 5Dollar evidence.

## 9. Attestation authenticity and runtime key

Reviewer attestations are authenticated with HMAC-SHA256 over canonical JSON. This prevents a user from fabricating or editing a registry row and merely copying the expected attestation fields.

The reviewer and daily selection process require the same independently provisioned secret:

- Environment variable: `VELTRIX_QUALIFICATION_ATTESTATION_KEY`
- Minimum length: 32 characters.
- Store it as a protected GitHub Actions secret for any future CI job that validates a populated registry, and provide it only to the trusted offline reviewer/runtime environment.
- Never commit the value, place it in a registry, or print it in logs.
- Missing or invalid key means fail closed; the reviewer emits no qualified registry and daily selection rejects qualified entries.

The key has not been provisioned in this repository by this change. Provisioning it is an operational prerequisite before any reviewer can issue a usable signed registry.

## 10. Empty competition windows

All 17 competition keys must be represented in the report with both final and scheduled checks, but an empty final-history window does not become a qualified competition. The reviewer qualifies only competitions with at least one validated final result in the measured window. Empty windows remain explicitly represented in the audit evidence. A report with no competition having final history is rejected.
