# Muse Relay Service Experience Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the implementation task and independent spec/quality review. Root performs browser validation and deployment. Execute all authorized work without another design gate.

**Goal:** Turn the existing relay into a cohesive Korean service experience and accurately explain Muse as the user's Meta AI.

**Architecture:** Keep the stdlib Python queue and account/device APIs. Rework the existing HTML/CSS/JS surfaces, add a user-initiated onboarding test using existing send/history endpoints, and preserve legacy VM URLs. Introduce no new backend capabilities or dependencies.

**Tech Stack:** Python 3.10+, SQLite, semantic HTML, CSS, vanilla JavaScript, unittest, browser QA.

**Workspace:** Isolated Git worktree at work/muse-service-polish, branch feat/service-experience. App worktree tool cannot choose this nested repository from the projectless root; git worktree is used explicitly against outputs/muse-relay. Baseline: all existing tests must pass before implementation.

## Task 1: Implement cohesive service experience

**Files:** static/muse.html, static/muse.css, static/muse.js, static/api-docs.html; optionally a focused frontend helper if needed; server.py only for an explicit new static asset; README.md, docs/USER-GUIDE.md. Update existing CI syntax checks if adding browser JS.

- [x] Rebuild visitor home with readable 15–16px text, ink/mint/light visual system, clear start/login actions, a labeled example of web/Codex/API → Relay → VM inbox, three connection steps, use cases, FAQ and service footer. No fake users, security claims, pricing or completion indicators. Move old VM navigation to a secondary footer link.
- [x] Present signup/login as an intentional section revealed by start/login, with working native form validation and loading/error states. URL hash may expose the auth panel. Preserve existing session behavior and show a real error if login/session retrieval fails.
- [x] Rebuild authenticated dashboard around clear Muse creation/selection, device status and scoped history. Maintain public/private settings, pairing and revoke flows, API and Codex copy features, pagination and per-Muse isolation.
- [x] Add an onboarding checklist: register, connect agent, explicitly send test, confirm localhost ACK. Derive connected/online separately from delivery state; never treat claim heartbeat as delivery success. Status pure contract: no device → connect; device without test → test; test pending/leased → waiting; exact test acked → receiver confirmed. Existing older ACKs must not complete a new test.
- [x] Test action uses selected Muse only: POST /api/muses/{id}/send, text/plain, generated Idempotency-Key. No automatic test sends. Capture selected Muse ID before await and ignore stale UI updates if selection changes. Disable during request, retain the same retry key/text when network/5xx outcome is uncertain, clear retry only on acknowledged response or definitive rejection (429 remains retryable). Retain the returned message ID per Muse in sessionStorage and query its individual history endpoint while waiting so pagination cannot hide the test. Readiness cannot imply Meta AI has read or executed it. Surface timeout/offline as waiting, not failure if durable queue still contains it.
- [x] Public sender remains anonymous for public Muse; preserve exact request retry behavior and byte limit, handle not found and owner-only states. Receipt clearly says server accepted, with a distinct explanation of VM inbox vs Meta AI read/execute.
- [x] Explain throughout: Muse here means Meta AI; Relay delivers to the VM localhost receiver; Meta AI must separately be able to read/process that inbox. HTTP/TCP receiver required, Python3.10+, localhost auth optional, device keys private. Include a copyable prompt for asking Muse to inspect its receiver environment, without actual secrets or claims of automatic execution.
- [x] Restyle API docs with matching header/navigation/type/spacing and sections anchored for getting started, JavaScript plain-text POST, receipt vs localhost ACK vs unobserved Meta execution, retry and errors. No key for public sending; owner/device authentication still required for those roles. Match current API contracts.
- [x] Use progressive responsive layout at desktop and 390px, clear focus states, accessible labels/live regions/reduced motion support. All important text remains legible, no overflow, no horizontal page scrolling. Do not use a framework, remote fonts, or new external requests.
- [x] Add meaningful targeted tests for new state/retry logic only if a focused helper is introduced; do not test CSS or exact prose. Browser QA covers rendered interactions. Run `node --check static/muse.js` and full Python tests, existing container smoke in CI.
- [x] Update README and user guide for new flow, Meta AI meaning, receiver boundary, current service origin and existing VM continuity. No changes to old VM worker configuration, production queues, credentials or unrelated app.js/app.css.
- [x] Implementer self-review and commit all scoped code. Report changed files, validation and any remaining concerns.

## Task 2: Independent review and browser verification

- [x] Spec reviewer checks Task1 requirements and Meta AI delivery boundaries; implementer resolves findings.
- [x] Quality reviewer checks concurrent selection changes, stale responses, idempotent test retries, polling/error behavior, auth, DOM safety and responsive/accessibility issues; implementer resolves findings.
- [x] Root starts local service with disposable DB/tokens and local PUBLIC_ORIGIN, then uses browser to validate landing/auth/create/pair/test/history/public send/copy/docs and mobile 390px. Use disposable test Muse/receiver only. Verify keyboard focus and screenshots. Preserve live existing VM queue.
- [x] Run full tests and JS checks once final code changes stabilize; check diff and secrets. Commit review fixes, push feature branch, open PR, attach to task.

## Task 3: Ship and verify

- [ ] Wait for CI success, merge authorized PR, confirm main CI passes and Universe Railway automatically deploys new commit.
- [ ] Verify public service health, landing Meta AI description, new guide/docs, existing test account/data preserved; run isolated receiver smoke if needed. Do not send legacy VM test messages.
- [ ] Save final desktop/mobile screenshots and mark service/browser deliverables. Report service URL, changed experience, actual checks, material limitations and screenshot. Record final metadata; preserve recoverable source changes/worktree until verified clean integration.
