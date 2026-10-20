# Sender key validation

- Python unittest: 51 passing (local isolated SQLite and HTTP/TCP).
- Node: 9 passing; browser JavaScript syntax and Python compilation pass.
- Browser issued a key and copied the full guide with actual local API URL and key. POST to common API reached the intended Muse, persisted at localhost and became acked; same retry did not duplicate and second Muse queue stayed empty.
- Switching Muse disabled key/guide copy and cleared raw key; reselecting original showed metadata only. Fresh page retained key status but not raw key. 390px viewport had equal client/scroll width.
- Independent code review found stale clipboard fallback on same-Muse rotation. Fixed by capturing secret identity and mutation epoch; reviewer verified delayed rejection after rotation/revoke/metadata/selection changes is blocked, and unchanged copying still works. No remaining actionable findings.
- A browser automation timeout prevented completing the native confirmation dialog test for rotation; fresh tab continued normally and the test tab was closed. Backend rotation/revoke/concurrency tests passed. No production keys or actual Muse queues used for these local checks.
