# Security policy

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

**[Report a vulnerability privately](https://github.com/AuroraEthan/muse-relay/security/advisories/new)**

Do not open a public issue containing an exploit, real credentials or private inbox data. Include the affected commit, reproduction using synthetic data, expected security boundary and potential impact. Do not test against other users or the hosted deployment without separate authorization. If the private report form is unavailable, open a generic issue asking for a private contact route without disclosing the vulnerability.

## Supported code

Security fixes target the latest `main` branch. The project is an early beta and does not currently maintain separate long-term-support release branches or promise a response SLA.

## Security boundaries

- Sender API keys select one Relay inbox and permit sending only. Store them in trusted application secret settings, not public frontend code or URLs.
- Owner session cookies manage inboxes, keys and delivery history.
- Device credentials claim and acknowledge messages for their paired inbox only.
- The localhost receiver must durably store messages and deduplicate IDs before responding successfully.
- Incoming text is untrusted input. A valid sender key grants delivery access, not permission for destructive operations, payments or arbitrary command execution.

## Operating your own instance

Terminate public traffic with HTTPS and set `PUBLIC_ORIGIN` to that exact origin. Use distinct random legacy producer/consumer tokens and a persistent data volume. Keep one server process/replica with the current SQLite architecture. Keep your Python runtime and container base image updated.

Protect backups of both the registry database and inbox queues. Do not commit `.env` files, device configuration, cookies or inbox databases. If a sender key leaks, rotate or revoke it in the owner dashboard. If a device key leaks, revoke the device and pair it again. If an owner account is compromised, treat access to that account's keys and message history as compromised; password recovery and account-wide session revocation are not implemented in this beta.
