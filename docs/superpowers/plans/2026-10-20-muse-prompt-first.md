# Muse Prompt-First Implementation Plan

> Execute inline; the UI, pairing lifecycle and prompt builder are one tightly coupled task. Independent correctness review follows before shipping. The user approved this direction and implementation explicitly.

**Goal:** A user copies a ready connection prompt into Muse instead of configuring the VM manually.
**Architecture:** Existing pairing API and downloaded muse_agent.connect remain unchanged. A tested browser helper owns per-Muse ephemeral pairing lifecycle and builds precise natural-language instructions. The current management UI invokes it, renders copy/expiry/fallback state and refresh invalidation; manual controls are preserved in details.
**Tech stack:** Vanilla JS/HTML/CSS, Python stdlib backend, Node tests, existing GitHub CI and Universe Railway.

- [ ] Add `tests/test_setup_prompt.cjs`: issue once/reuse until expiration, force replacement, per-Muse requests, invalid payload rejection, connection invalidation, prompt actual origin/code/MuseID/download/expiry and no hypothetical shell flags. Run to demonstrate failure before implementation.
- [ ] Add `static/muse-setup.js`: exported ConnectionPrompts and buildConnectionPrompt. Validate origin/ID/code/TTL. Keep codes in memory only, cache in-flight issuance and bind connected_at. Build complete Korean task with operational instructions, receiver protocol, exact target check and honest tool/reading limits. Register new static asset, HTML script, CI Node tests and container asset smoke.
- [ ] Modify static/muse.html, muse.js, muse.css: copy-first hero/setup guide/FAQ; primary prompt create-and-copy, visible expiry, full selectable preview, explicit regenerate, main step list, manual controls in details; selection/expiry/connected/revoke clears preview; async stale selection never copies wrong Muse. Reuse existing test send/ACK and secret-safe copy fallback.
- [ ] Update README, USER-GUIDE, API docs and ZIP START.md to prompt-first flow, clarify intentional one-time code sharing vs private long-lived keys. Preserve existing endpoint/API contracts.
- [ ] Run Python suite and JS tests/syntax. Browser QA desktop/mobile: prompt generation includes local origin and actual selected ID/code, reuse same code, switching Muse, refresh/reissue, clipboard fallback/preview, pairing consumes code, old prompt cleared and connected state visible. Use disposable data/receiver only, never legacy VM test messages.
- [ ] Independent review, resolve any actual findings, commit/push PR and attach. CI pass then merge; main CI and Railway release verify new UI/helper/docs plus existing account/ACK persistence. Save live screenshot; preserve service page and clean disposable resources.
