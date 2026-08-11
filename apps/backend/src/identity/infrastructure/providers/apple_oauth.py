"""Apple OAuth ("Sign in with Apple") provider adapter. Implements
`identity.application.ports.AppleOAuthProviderPort` -- mirrors `google_oauth.py`'s shape and
intent, but Apple's own OAuth wire protocol differs from Google's in two structural ways this
adapter has to bridge:

1. Apple has no static client secret -- the token endpoint requires a short-lived JWT
   (`_client_secret_jwt`, ES256) signed with the developer's own Apple-issued private key
   (`APPLE_PRIVATE_KEY`, `APPLE_KEY_ID`, `APPLE_TEAM_ID`), regenerated fresh per exchange rather
   than cached (cheap to compute, and avoids any expiry-window bookkeeping).
2. Apple has no separate userinfo endpoint -- identity claims (subject/email/email-verified)
   travel inside the token response's own signed `id_token` (a JWT), verified here against
   Apple's published JWKS (`_JWKS_URL`) before any claim is trusted (`aud` must match our own
   client id, `iss` must be Apple's issuer -- standard OIDC verification, not optional)."""

from __future__ import annotations

import time

import httpx
import jwt
from jwt import PyJWKClient

from backbone.persistence.env import required_env
from identity.application.exceptions import InvalidAppleCredentialError
from identity.application.ports import AppleIdentity

_TOKEN_URL = "https://appleid.apple.com/auth/token"  # nosec B105 -- a public endpoint URL, not a secret
_JWKS_URL = "https://appleid.apple.com/auth/keys"
_ISSUER = "https://appleid.apple.com"
_CLIENT_SECRET_TTL_SECONDS = 300


class AppleOAuthProviderAdapter:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._client_id = required_env("APPLE_CLIENT_ID")
        self._team_id = required_env("APPLE_TEAM_ID")
        self._key_id = required_env("APPLE_KEY_ID")
        # The .p8 private key is PEM (multi-line); stored in the env as a single line with
        # literal "\n" escapes (the only way a PEM survives most env-var mechanisms unmangled),
        # unescaped back to real newlines here before it reaches `jwt.encode`.
        self._private_key = required_env("APPLE_PRIVATE_KEY").replace("\\n", "\n")
        self._jwks_client = PyJWKClient(_JWKS_URL)

    def _client_secret_jwt(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": self._team_id,
                "iat": now,
                "exp": now + _CLIENT_SECRET_TTL_SECONDS,
                "aud": _ISSUER,
                "sub": self._client_id,
            },
            self._private_key,
            algorithm="ES256",
            headers={"kid": self._key_id},
        )

    async def exchange_authorization_code(
        self, *, authorization_code: str, redirect_uri: str
    ) -> AppleIdentity:
        token_response = await self._client.post(
            _TOKEN_URL,
            data={
                "code": authorization_code,
                "client_id": self._client_id,
                "client_secret": self._client_secret_jwt(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise InvalidAppleCredentialError()
        id_token = token_response.json().get("id_token")
        if not id_token:
            raise InvalidAppleCredentialError()

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=_ISSUER,
            )
        except jwt.PyJWTError as exc:
            raise InvalidAppleCredentialError() from exc

        subject = claims.get("sub")
        email = claims.get("email")
        if not subject or not email:
            raise InvalidAppleCredentialError()

        # Apple encodes this as the string "true"/"false" in some token versions, a real bool in
        # others -- normalise rather than trust either shape blindly.
        email_verified = str(claims.get("email_verified", "false")).lower() == "true"

        return AppleIdentity(
            subject=subject,
            email=email,
            email_verified=email_verified,
            # Apple only ever sends the user's name in the client-side authorization callback's
            # `user` payload on the very first consent, never inside the id_token this endpoint
            # sees -- there is no server-side way to recover it, so this is always None.
            display_name=None,
        )
