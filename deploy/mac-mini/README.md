# Mac mini deployment

This bundle uses the upstream Postiz **v2.24.0** ARM64 image, with the existing UI,
OAuth connection screens, publishing workers, public API, PostgreSQL, Redis and
Temporal. It is a deployment baseline for this fork. If application code is
changed later, build and pin an image from this fork before deploying those changes.

## Prerequisites

- Mac mini with current Docker Desktop and at least 8 GB RAM available for this
  stack (more is preferable). Keep macOS, Docker Desktop and the Mac awake.
- A domain managed in Cloudflare and a named Cloudflare Tunnel.
- OAuth application credentials for each social platform. A Postiz installation
  alone cannot grant Instagram, TikTok or YouTube publishing permissions.

## Install

1. In this directory run `chmod +x init.sh backup.sh check.sh` and
   `./init.sh postiz.example.org`, using your actual hostname.
2. In Cloudflare Zero Trust, create a named Tunnel for the Mac and route that
   hostname to `http://localhost:4007`. Install `cloudflared` as a macOS service
   with the token provided by Cloudflare. Keep the token outside this repo.
3. For first admin registration only, change `DISABLE_REGISTRATION=true` to
   `false` in `.env`. Start with `docker compose --env-file .env -f compose.yaml up -d`.
   Create the admin user, set the value back to `true`, and run the same compose
   command again to recreate the app with registration closed.
4. Run `./check.sh`. Confirm that the HTTPS hostname serves the app and that
   uploaded media under `/uploads/` is reachable from outside your network.
5. Add platform credentials to `.env` and recreate the app. Configure each
   provider's redirect URI for the same HTTPS hostname, then connect one test
   account and publish a private/test item per platform before production use.

Only port 4007 on **127.0.0.1** is published by Docker. PostgreSQL, Redis,
Elasticsearch and Temporal are reachable only on the internal Docker network.
Do not put Cloudflare Access in front of the entire hostname: OAuth callbacks
and platforms fetching `/uploads/` would be blocked. Restrict app access with
Postiz accounts, and add path-aware Cloudflare rules only after testing.

## Reliability and recovery

- Services restart after crashes; state is kept in named volumes. Pinning the
  app version avoids unattended changes. Docker Desktop must start at login.
- Run `./backup.sh` during a maintenance window. It stops the stack briefly to
  capture a consistent archive of all six data volumes, checks the archive, then
  starts the stack. Keep the resulting archive **and `.env`** in encrypted
  off-machine storage. `.env` includes signing and database secrets.
- Test a restore on a separate machine before relying on backups. Restore by
  creating the same volumes, stopping the stack, extracting the archive into
  those volumes, restoring `.env`, and starting the stack. Do not overwrite a
  live installation as a test.
- Before an update, take a backup, change the pinned image tag only after
  reviewing release notes and security advisories, then run `docker compose
  --env-file .env -f compose.yaml pull` and `docker compose --env-file .env
  -f compose.yaml up -d`. Run `./check.sh` and one draft/test post afterward.
- A single Mac mini cannot guarantee continuous service through hardware,
  power, network, Docker or provider outages. Add a UPS, off-machine backups
  and external uptime alerting; true failover requires a second host and
  externalized state.

## Integration with another system

The existing Postiz public API can accept uploaded media and create/schedule
posts. Integrate via API key and the public HTTPS base URL, with a durable job
queue on the calling side. Store one job ID per source item and destination;
retry transient failures with backoff, but check whether a post was already
created before retrying so a timeout does not publish a duplicate. Reconcile
scheduled/published status rather than assuming an accepted API call means a
platform published the media. Platform specific media requirements and review
status must be checked before dispatch. The exact adapter depends on the
existing application's API, storage and event flow.

## Links

- [Postiz self-hosting documentation](https://docs.postiz.com/self-host/installation/system-requirements)
- [Postiz uploads and public media](https://docs.postiz.com/self-host/configuration/uploads)
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/)
- [Postiz public API](https://docs.postiz.com/public-api)
