# Muse restart recovery implementation plan

**Goal:** Extend the approved connection instructions with durable automatic recovery and quiet operation.
**Architecture:** Keep pairing lifecycle and APIs unchanged. Update buildConnectionPrompt and user-facing copy together; Muse implements environment-specific supervision and processing.
**Tech Stack:** Existing static JavaScript/HTML, Python stdlib service.

- [x] Update static/muse-setup.js: persistent paths, boot supervision of all components, bounded retries, pending processing recovery, quiet normal operation, honest validation and no unrequested reboot.
- [x] Update static/muse.html, static/api-docs.html, README.md, docs/USER-GUIDE.md and ZIP START.md to describe that behavior consistently while retaining the ACK boundary.
- [ ] Run node --check static/muse-setup.js, existing Node tests, Python unittest discovery; review diff.
- [ ] Publish PR, verify CI, merge and verify production assets/health and browser layout.
