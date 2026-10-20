# Service experience validation — 2026-10-20

- Python: 51 tests pass.
- JavaScript onboarding: 4 Node tests pass; muse.js, muse-test.js and app.js syntax checks pass.
- Independent spec and correctness reviews approved.
- Disposable local browser flow: signup → register Muse → explicit test send before VM connection (stays pending) → device pairing → local receiver → exact test ID ACK. Reload retains the test receipt; a second Muse does not inherit it.
- Anonymous public web sender accepted text; local receiver received it. API and Muse prompt copy controls contain the intended endpoint/cloud VM instructions.
- Responsive browser QA at 390px: landing, auth, management, public sender and API docs; landing/management/docs measured without page overflow, public sender visually checked. API anchor navigation works. No browser JS errors observed during main flow.
- The receiver is a disposable local test fixture representing VM localhost. This does not claim Meta AI read or executed a message. No test messages were sent to the existing legacy VM.
- Deployment verification is recorded by the calling task after CI and Railway rollout.
