# Verification stack environment (isolated from the developer's dev stack).
# Postgres: same container, separate DB. Redis/OpenSearch: dedicated containers.
# MinIO/ClamAV/Mailpit: shared containers, separate bucket.
export REPO=/home/ameer/extra/work/umidjon/active-home-platform/active-home-platform/.claude/worktrees/verify-p-verify
export PYTHONPATH="$REPO/apps/backend/src:$REPO/packages/shared/src:$REPO"
export ENV_NAME=local
export LOG_LEVEL=info

export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=active_home_verify
export POSTGRES_USER=active_home
export POSTGRES_PASSWORD=<redacted-local-dev-password>

export REDIS_HOST=localhost
export REDIS_PORT=6380

export OPENSEARCH_HOST=localhost
export OPENSEARCH_PORT=9201

export MINIO_ENDPOINT=localhost:9000
export MINIO_ROOT_USER=active_home
export MINIO_ROOT_PASSWORD=<redacted-local-dev-password>
export MINIO_MEDIA_BUCKET=active-home-media-verify
export MINIO_USE_TLS=false

export MEDIA_CDN_BASE_URL=http://localhost:8100/media
export MEDIA_PRESIGN_EXPIRY_SECONDS=900
export CLAMAV_HOST=localhost
export CLAMAV_PORT=3310

export SESSION_COOKIE_NAME=ah_session
export SESSION_SIGNING_KEY=<redacted-local-signing-key>

export CORS_ALLOWED_ORIGINS=http://localhost:3100,http://127.0.0.1:3100

export ESKIZ_API_BASE_URL=https://notify.eskiz.uz/api
export ESKIZ_EMAIL=verify@example.invalid
export ESKIZ_PASSWORD=not-a-real-password
export ESKIZ_SENDER_NICKNAME=4546
export YANDEX_MAPS_API_KEY=not-a-real-key
export GOOGLE_OAUTH_CLIENT_ID=not-a-real-client-id
export GOOGLE_OAUTH_CLIENT_SECRET=not-a-real-client-secret

# Mailpit (shared local sink, no TLS/auth needed)
export SMTP_HOST=localhost
export SMTP_PORT=1025
export SMTP_USER=verify
export SMTP_PASSWORD=verify

export WEB_PUSH_VAPID_PUBLIC_KEY=<redacted-local-test-value>
export WEB_PUSH_VAPID_PRIVATE_KEY=<redacted-local-test-value>
