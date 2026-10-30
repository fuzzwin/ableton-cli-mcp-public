# Local trust and reporting

Use the bridge only on loopback. Keep its generated token/config private and owned by your OS user. Read-only Live access and silent file processing are defaults; opt-in mutations and playback are separate. Do not expose the progress viewer or bridge through port forwarding. Local processes running as your user are inside this trust boundary.

A selected third-party plugin executes native code in a child process. Time/CPU/log limits do not provide an OS sandbox. Only test plugins you trust; installation metadata is not proof of safety, licensing or usability.

Never post bridge configs, tokens, private audio, inventories or feedback ledgers in an issue. If a secret is exposed, revoke/rotate it before relying on Git history removal. For sensitive reports, use GitHub's private vulnerability reporting if enabled; otherwise ask for a private contact without posting exploit details or secrets publicly.

Source: [GitHub sensitive-data guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository), checked 2026-10-30. This document does not certify security or supported deployment outside a single-user local host.
