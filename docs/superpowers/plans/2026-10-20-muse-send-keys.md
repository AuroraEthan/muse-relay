# Muse sender API key implementation plan

**Goal:** Replace anonymous Muse delivery with scoped sender keys and a shared plaintext API.
**Architecture:** Add a separate hash-only sender-key table in Registry; resolve authenticated /api/send to the existing per-Muse queue. Owner web sends use existing session route. UI secrets live only in selected-Muse memory.
**Tech Stack:** Python stdlib/SQLite, static JavaScript and HTML.

- [x] Add integration tests in tests/test_muses.py for key ownership, routing, rotation/revoke/persistence, role separation, public flag migration, CSRF and plaintext idempotency; observe failures before implementing.
- [x] Implement Registry sender_key/rotate_sender_key/revoke_sender_key/sender methods and owner-only metadata; implement common send and key lifecycle routes in muse_api.py. Disable anonymous legacy /send in server.py and adjust legacy tests.
- [x] Update static/muse.js and muse.html: remove public controls; add issue/rotate/revoke/copy and scoped clipboard fallback; keep owner web compose and test. Clear secrets on switch/revoke/metadata changes and prevent stale async exposure.
- [x] Update API docs, OpenAPI, README, user guide, connection prompt auth wording and container checks.
- [ ] Run Python and Node checks, isolated end-to-end test and browser desktop/mobile; independent code review, fix issues, commit/push PR, CI, merge and production verify. Production QA uses only existing synthetic test account, never sends to real Muse.
