/**
 * Google / Apple Sign-In redirect-URL builders. Both providers use the plain
 * authorization-code OAuth flow (no SDK): a full-page redirect to the provider, which redirects
 * back to a callback route that exchanges the `code` for a first-party session via
 * `authApi.loginGoogle`/`loginApple` (see `routes/auth/callback/google.tsx`/`callback/apple.tsx`).
 *
 * Same "missing provider key is an expected, recoverable state" convention as
 * `lib/yandex-maps.ts`'s `getYandexMapsApiKey()`: until a real client id is configured, the
 * getters return null and the sign-in buttons render a "sozlanmagan" notice instead of starting a
 * redirect that would only fail on the provider's own consent screen.
 *
 * `getGoogleRedirectUri`/`getAppleRedirectUri` are functions, not module-scope constants -- this
 * app renders on the server first (TanStack Start SSR), where `window` does not exist; a
 * top-level `window.location.origin` read would crash every SSR render of any page importing
 * this module, not just the auth pages. Callers only ever invoke them client-side (inside a click
 * handler or an effect), never at module-eval time.
 */
import { API_BASE_URL } from "./http";

export function getGoogleRedirectUri(): string {
  return `${window.location.origin}/auth/callback/google`;
}

/** The `redirect_uri` Apple's login_apple exchange must be called with -- Apple validates it
 * against what it was told during authorization, which is the *backend's* relay endpoint (Apple
 * itself never talks to the frontend route directly, see `buildAppleAuthorizeUrl`). Safe to read
 * at module scope (unlike the Google one): `API_BASE_URL` already falls back to a fixed default
 * server-side rather than touching `window`. */
export const APPLE_REDIRECT_URI = `${API_BASE_URL}/auth/callback/apple`;

export function getGoogleClientId(): string | null {
  const id = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID as string | undefined;
  return id && id.trim().length > 0 ? id.trim() : null;
}

export function getAppleClientId(): string | null {
  const id = import.meta.env.VITE_APPLE_CLIENT_ID as string | undefined;
  return id && id.trim().length > 0 ? id.trim() : null;
}

export function buildGoogleAuthorizeUrl(clientId: string): string {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: getGoogleRedirectUri(),
    response_type: "code",
    scope: "openid email profile",
    access_type: "online",
    prompt: "select_account",
  });
  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export function buildAppleAuthorizeUrl(clientId: string): string {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: APPLE_REDIRECT_URI,
    response_type: "code",
    scope: "name email",
    response_mode: "form_post",
  });
  return `https://appleid.apple.com/auth/authorize?${params.toString()}`;
}
