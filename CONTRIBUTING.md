# Contributing to Muse Relay

Bug reports, documentation improvements and pull requests are welcome. The UI and most user documentation are currently in Korean; English issues and pull requests are welcome too.

## Before starting

- Read the [README](README.md), [architecture](docs/ARCHITECTURE.md) and [test guide](TESTING.md).
- Use an issue to discuss larger changes before implementation. Include the problem, expected behavior and a small reproduction for bugs.
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md), rather than a public issue.

## Development

Python 3.10 or newer is required. The application uses only the Python standard library. Node.js 18 or newer runs the browser-logic tests; Docker is optional for container validation.

```sh
git clone https://github.com/AuroraEthan/muse-relay.git
cd muse-relay
git switch -c fix/my-change
python3 -m unittest discover -s tests -v
node --test tests/test_setup_prompt.cjs tests/test_onboarding.cjs
node --check static/muse.js
node --check static/muse-setup.js
node --check static/muse-test.js
node --check static/app.js
```

Use the README local setup for manual testing. Run all tests against temporary or local data, never another person's inbox or the hosted service. Test both desktop and mobile layouts when changing the UI.

## Pull requests

Explain the problem, resulting behavior and relevant validation. Keep changes focused and update the docs when behavior changes. Include screenshots for visible UI changes, with credentials and private data hidden. Add regression coverage for bugs affecting delivery, authentication or persistence.

Preserve inbox isolation, send-only key scope, owner-only management and device-only claim/ACK. A receiver ACK does not prove that Muse read or completed a request. Document any changes to those boundaries explicitly.

Do not commit real API keys, pairing codes, cookies, database files, receiver contents or production logs. Example values must be obvious placeholders. Use synthetic accounts and secrets for tests.

By submitting a contribution, you agree to license your contribution under this repository's [MIT License](LICENSE). Please communicate respectfully and focus feedback on the work.
