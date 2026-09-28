# Mac mini deployment

This bundle uses the upstream Postiz **v2.24.0** ARM64 image pinned by digest, with the existing UI,
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

1. On the Mac mini, clone
   `https://github.com/talhafortress/postiz-app.git` and check out the
   `codex/mac-mini-deployment` branch. In this directory run
   `chmod +x init.sh backup.sh check.sh` and
   `./init.sh postiz.example.org`, using your actual hostname.
2. In Cloudflare Zero Trust, create a named Tunnel for the Mac and route that
   hostname to `http://localhost:4007`. Install `cloudflared` as a macOS service
   with the token provided by Cloudflare. Keep the token outside this repo.
3. For first admin registration only, change `DISABLE_REGISTRATION=true` to
   `false` in `.env`. Start with `docker compose --env-file .env -f compose.yaml up -d`.
   Create the admin user, set the value back to `true`, and run the same compose
   command again to recreate the app with registration closed.
4. Run `./check.sh`. Confirm that the HTTPS hostname serves the app and that
   a small uploaded test file is reachable from outside your network.
5. Add platform credentials to `.env` and recreate the app. Configure each
   provider's redirect URI for the same HTTPS hostname, then connect one test
   account and publish a private/test item per platform before production use.

Only port 4007 on **127.0.0.1** is published by Docker. PostgreSQL, Redis,
Elasticsearch and Temporal are reachable only on the internal Docker network.
Do not put Cloudflare Access in front of the entire hostname: OAuth callbacks
and platforms fetching `/uploads/` would be blocked. Restrict app access with
Postiz accounts, and add path-aware Cloudflare rules only after testing.

### Large videos

Cloudflare's proxied Free/Pro route accepts at most **100 MB per upload**.
Run the bridge on the Mac mini with `POSTIZ_API_URL=http://127.0.0.1:4007/api`
for large video uploads, or move files to the Mac via a private transfer first.
The generated public media URL still uses `FRONTEND_URL` so social platforms
can fetch it. Cloudflare also states that video delivery through a public
Tunnel on Free/Pro/Business requires an eligible paid video service. For a
production workflow with large videos, configure Postiz's R2 storage option
and a public R2 custom domain (set `STORAGE_PROVIDER=cloudflare` and the
`CLOUDFLARE_*` values in `.env`), or choose another compliant media delivery
architecture before relying on the tunnel for media. Keep the Tunnel for UI,
API callbacks and small requests. Test provider fetches with a real video.

## Reliability and recovery

- Services restart after crashes; state is kept in named volumes. Pinning the
  app image digest avoids unattended app changes. Docker Desktop must start at login.
- Run `./backup.sh` during a maintenance window. It stops the stack briefly to
  capture a consistent archive of all six data volumes, checks the archive, then
  starts the stack. Keep the resulting archive **and `.env`** in encrypted
  off-machine storage. `.env` includes signing and database secrets.
- Test a restore on a separate machine before relying on backups. Restore by
  creating the same volumes, stopping the stack, extracting the archive into
  those volumes, restoring `.env`, and starting the stack. Do not overwrite a
  live installation as a test.
- Before an update, take a backup, change the pinned image tag and digest only after
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
queue on the calling side. Store one job ID per source item and destination set;
retry transient failures with backoff, but check whether a post was already
created before retrying so a timeout does not publish a duplicate. Reconcile
scheduled/published status rather than assuming an accepted API call means a
platform published the media. Platform specific media requirements and review
status must be checked before dispatch. The exact adapter depends on the
existing application's API, storage and event flow.

`bridge/submit.py` is a small, dependency-free starting adapter. It streams a
local file to Postiz, then creates one multi-destination post request. Copy
`bridge/job.example.json`, replace media path and connected integration IDs,
and set `POSTIZ_API_URL=http://127.0.0.1:4007/api` and `POSTIZ_API_KEY` in the
calling process. Run `python3 bridge/submit.py job.json bridge-state.sqlite`.
The default mode is **draft** for review. `now` and `schedule` require each
platform's valid `settings`; for schedule also provide an ISO 8601 `date`.
Get integration IDs from Postiz's `GET /api/public/v1/integrations` endpoint.
The state database prevents a successful job from being submitted again. If
Postiz's response is lost or only some destinations are confirmed, the adapter
marks the job uncertain and refuses automatic retry; inspect Postiz first.
An API acceptance still needs a later publication-status check. Keep the API
key and state database out of Git and back up the state database separately.

## Links

- [Postiz self-hosting documentation](https://docs.postiz.com/self-host/installation/system-requirements)
- [Postiz uploads and public media](https://docs.postiz.com/self-host/configuration/uploads)
- [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/get-started/)
- [Cloudflare upload limits](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/#upload-limits)
- [Cloudflare Tunnel video delivery terms](https://developers.cloudflare.com/tunnel/concepts/routing/#published-applications)
- [Postiz public API](https://docs.postiz.com/public-api)
