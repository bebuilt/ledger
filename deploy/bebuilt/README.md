# deploy/bebuilt

bebuilt's deployment of this fork: one RAGFlow box per client, built to be handed over. This directory is
the only thing bebuilt adds to the fork; everything else tracks upstream.

| File | What it is |
|---|---|
| `box-setup.sh` | Brings a box to its intended state. Runs as root from `/opt/ragflow` at the pinned ref. Re-runnable. |
| `compose.bebuilt.yml` | Compose override: nothing is published to the host except nginx on `127.0.0.1:8080`, which cloudflared reaches. |
| `env.bebuilt` | Non-secret settings layered onto `docker/.env`: the image pinned by digest, OpenSearch, local embeddings, no self-registration. |
| `tenant-setup.py` | Runs inside the RAGFlow container: this box's app user, its API key and the `shared` dataset (embedding model pinned; never changed once the dataset exists). Writes `/etc/bebuilt/ragflow-tenant.json`. |
| `ingest.py` + `bebuilt-ingest.{service,timer}` | The ingestion worker, every five minutes: walks the confirmed selection through Composio, sends new and changed files to RAGFlow, records progress in the platform DB as `worker_<slug>` (RLS: this org's rows only). |
| `ragflow-dump.sh` | Nightly consistent MySQL dump onto the box's own disk (keeps three), so each Hetzner backup holds a clean copy. |

It is driven from the laptop by `scripts/ragflow-provision.sh <client> <host> [ref]` in
`bebuilt/bebuilt-platform-v2`, which pushes that client's secrets from its own 1Password vault to
`/etc/bebuilt/` and checks this repo out at a pinned tag (`bebuilt-YYYY-MM-DD`). The same run serves the
first build, a rebuild after restore, and the handoff to a new owner.

Rules this directory keeps:

- **Code reaches a box only through git**, at a tag. No files are copied onto a box by hand.
- **No port on a public interface.** `box-setup.sh` fails if any container publishes one.
- **No secret in this repo** (it is public). Secrets live in the client's vault and in `/etc/bebuilt/` (0600).
- **Nothing multi-tenant on a box.** Every credential on it belongs to that client alone.
- **The image is pinned by digest** to a build that contains the CVE-2026-93013 fix (PR #19591); the
  released `v0.27.2` does not.
