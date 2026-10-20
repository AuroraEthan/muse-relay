# Muse restart recovery and quiet operation

User approved scope: update the generated connection prompt and website so Muse configures restart recovery and resumes message processing. VM files survive reboot. Do not report every routine restart.

Persist agent/config/inbox/processing ledger in a verified durable private directory. Ask Muse to use the environment-supported boot supervisor for receiver, relay and processing/watch mechanism; avoid duplicate processes. Verify restart/recovery without rebooting the VM unasked. Reuse valid credentials; revoked credentials need pairing again. Retry temporary faults, preserve unacknowledged delivery, record message processing independently of receiver ACK, and do not blindly replay uncertain side effects. Routine healthy recovery stays in logs; report initial setup/test and actionable persistent failure only. Website describes requested setup, never claims AI processing is verified by relay status.

No backend protocol changes or actual remote VM reconfiguration in this change.
