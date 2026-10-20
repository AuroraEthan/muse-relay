# Muse sender API keys

Approved design: replace public sending with one active sender key per Muse. External clients POST UTF-8 text/plain to /api/send with Authorization: Bearer <key>; registry resolves the target. Never accept a caller-supplied target override. No JSON or user-assigned ID required. Optional Idempotency-Key remains scoped to the target queue.

Owners create/rotate/revoke via same-origin authenticated JSON endpoints /api/muses/{id}/sender-key and /sender-key/revoke. Store only SHA-256 hashes, nonsecret prefix, created timestamp and key version. Return the secret only at issuance, keep browser copies in memory, clear on selection/account/metadata changes; no persistence or shared detail-modal fallback. One active key; rotation invalidates previous key. Key is send-only, cannot read history, pair, claim, ack, or manage keys. Device keys remain independent.

Existing public flags must no longer grant anonymous send or metadata access; normalize registry flags off without changing device keys or queues. Old Muse-specific send URLs remain owner-session-only for web compose and test. Remove public controls and anonymous sharing guidance. Current service legacy /send requires producer auth even if PUBLIC_SEND is set; separately deployed legacy VM service is outside this migration.

Dashboard provides API URL, key status, issue/rotate/revoke, key copy and one-copy integration instructions. Key-loss guidance explains reissue, no plaintext recovery. Request failures cannot silently hide an uncertain rotation. Web compose is owner-only. Documentation/OpenAPI reflect auth, CORS, errors and migration. Verify cross-user ownership, missing/invalid/revoked/device keys, rotation/persistence, idempotency and full API-to-receiver ACK.
