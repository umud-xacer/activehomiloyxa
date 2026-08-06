# deployment/

Infrastructure-as-code (DEC-16): Docker, Compose, nginx config. No secrets committed.

- `compose/docker-compose.yml` -- datastore + edge topology (Infra Sec 6, Sec 7): `postgres`,
  `redis`, `opensearch`, `minio`, `nginx`, plus (Task P-10) the first application container,
  `realtime` (the WebSocket chat gateway, DEC-11). `api`, `web`, `worker` containers remain out
  of scope -- each gets its own multi-stage Dockerfile (DevSecOps Sec 9) in the task that first
  has code to build.
- `docker/realtime.Dockerfile` -- the `realtime` service's own multi-stage build (Task P-10).
- `nginx/nginx.conf` -- skeleton edge config; only a `/healthz` endpoint for now -- the
  reverse-proxy block for `realtime`'s own WSS upgrade (and TLS termination, Infra Sec 5) is not
  yet built (tracked as a TODO in that file).
- `env/.env.<environment>.example` -- the four environments (Infra Sec 17): `local`,
  `development`, `staging`, `production`. Copy the one you need to `.env.<environment>` (already
  gitignored) and fill in real values locally; staging/production never get real values
  committed -- they come from the secrets store / CI environment secrets (DevSecOps Sec 8).

Run locally: `scripts/dev-up.sh` (wraps `docker compose -f deployment/compose/docker-compose.yml
up -d`). Validate the compose file without starting anything:
`docker compose -f deployment/compose/docker-compose.yml config`.
