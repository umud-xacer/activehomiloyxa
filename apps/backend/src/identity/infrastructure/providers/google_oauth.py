"""Google OAuth provider adapter (DEC-18, FR-AUTH-003). Implements
`identity.application.ports.GoogleOAuthProviderPort` via plain OAuth2/OIDC HTTP calls (no Google
SDK dependency needed) -- Google's own token/userinfo response shapes are confined to this file;
only the plain `GoogleIdentity` dataclass crosses back out, and the access token itself is never
returned to the caller (Security Sec 3.1: "no Google token is exposed to the client
afterwards")."""

from __future__ import annotations

import httpx

from backbone.persistence.env import required_env
from identity.application.exceptions import InvalidGoogleCredentialError
from identity.application.ports import GoogleIdentity

_TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105 -- a public endpoint URL, not a secret; bandit's B105 flags the word "token" in the variable name
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthProviderAdapter:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._client_id = required_env("GOOGLE_OAUTH_CLIENT_ID")
        self._client_secret = required_env("GOOGLE_OAUTH_CLIENT_SECRET")

    async def exchange_authorization_code(
        self, *, authorization_code: str, redirect_uri: str
    ) -> GoogleIdentity:
        token_response = await self._client.post(
            _TOKEN_URL,
            data={
                "code": authorization_code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise InvalidGoogleCredentialError()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise InvalidGoogleCredentialError()

        userinfo_response = await self._client.get(
            _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_response.status_code != 200:
            raise InvalidGoogleCredentialError()
        userinfo = userinfo_response.json()
        subject = userinfo.get("sub")
        email = userinfo.get("email")
        if not subject or not email:
            raise InvalidGoogleCredentialError()

        return GoogleIdentity(
            subject=subject,
            email=email,
            email_verified=bool(userinfo.get("email_verified", False)),
            display_name=userinfo.get("name"),
        )
