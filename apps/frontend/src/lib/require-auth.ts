import { redirect } from "@tanstack/react-router";
import { authApi } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { verifyOwnerAdminSlug } from "@/lib/owner-admin-client";

/**
 * Client-side auth guard for protected routes. Use in `beforeLoad`.
 * Runs in the browser (routes with this guard should not rely on SSR-gated data).
 *
 * Returns the full `account` (not just its id) so route components can branch on
 * ADR-0007's `accountKind`/`reviewStatus` (see `ReviewGate`) without a second `/me` call.
 */
export const requireAuth = async ({ location }: { location: { href: string } }) => {
  if (typeof window === "undefined") return;

  try {
    const account = await authApi.me();
    return { userId: account.id, account };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      throw redirect({
        to: "/auth/sign-in",
        search: { redirect: location.href },
      });
    }
    throw error;
  }
};

/** ADR-0007: where a fully-approved account's role routes to. Individual falls back to the
 * generic `/dashboard` (the only one of the three that predates the role system). */
export function dashboardPathForAccount(account: { accountKind?: string | null }): string {
  if (account.accountKind === "LEGAL_ENTITY") return "/dashboard/seller";
  if (account.accountKind === "INVESTOR") return "/dashboard/investor";
  return "/dashboard";
}

/**
 * Guard for the `/admin` area (registration review, and the hub linking to it). Unlike
 * `requireSuperAdmin`'s "pretend this URL doesn't exist" posture, `/admin` is meant to be a
 * known, typeable entry point -- so an unauthenticated visitor is sent to `/boss` (the one
 * dedicated admin login gateway, not the public sign-in page -- admin auth never routes through
 * `/auth/sign-in`), and an authenticated-but-unprivileged one gets a clear "no access" outcome
 * rather than a silent bounce. Grants either `administrator` or `super-admin` (super-admin is a
 * superset -- Config Framework Sec 2.3). The backend's own `identity:registration:review` check
 * is the real security boundary; this only saves an unauthorized visitor a round trip.
 */
export const requireAdmin = async ({ location }: { location: { href: string } }) => {
  if (typeof window === "undefined") return;

  // Any failure to establish who's asking -- an explicit 401, a network hiccup, anything --
  // must fail closed (treated as "not authorized") rather than crash the route or, worse,
  // let the request through. This is an admin surface; the safe failure mode is "ask them to
  // sign in again," never "render the panel anyway."
  let account: Awaited<ReturnType<typeof authApi.me>>;
  try {
    account = await authApi.me();
  } catch {
    throw redirect({ to: "/boss", search: { redirect: location.href } });
  }

  if (!(account.roles ?? []).some((r) => r === "super-admin" || r === "administrator")) {
    throw redirect({ to: "/" });
  }
  return { userId: account.id, account };
};

/**
 * Guard for the secret owner-admin area (route `/$ownerAdminSlug`). The panel's real URL segment
 * is a super-admin-editable platform setting (`admin.owner_panel_slug`, changeable from inside
 * the panel itself, see `owner-admin-client.ts`'s `updateOwnerPanelSlug`) rather than anything
 * fixed in this (public) repo's source -- `verifyOwnerAdminSlug` checks the visitor's guess
 * against it through a yes/no-only backend call that never reveals the real value in its
 * response, so it doesn't have to sit in plaintext in the shipped JS bundle either.
 *
 * Unlike `requireAuth`, a visitor whose guess doesn't match, or who isn't a super-admin, is sent
 * to the homepage rather than shown a 401/403 page -- the route's own existence is meant to stay
 * unadvertised, so the failure mode for "wrong person found this URL" should look exactly like
 * "this URL doesn't exist", not like "here's a locked door". An unauthenticated visitor who *did*
 * guess right is sent to `/boss` instead (the one dedicated admin login gateway) so they can
 * still get in without needing to guess the slug twice. The backend's own permission checks
 * (`config:category:manage`/`approve`) are the real security boundary; this is a client-side
 * fast-fail so the wrong visitor never even sees the panel's shell render.
 */
export const requireOwnerAdminSlug = async ({
  params,
  location,
}: {
  params: { ownerAdminSlug: string };
  location: { href: string };
}) => {
  if (typeof window === "undefined") return;

  const validSlug = await verifyOwnerAdminSlug(params.ownerAdminSlug).catch(() => false);
  if (!validSlug) {
    throw redirect({ to: "/" });
  }

  let account: Awaited<ReturnType<typeof authApi.me>>;
  try {
    account = await authApi.me();
  } catch {
    throw redirect({ to: "/boss", search: { redirect: location.href } });
  }

  if (!(account.roles ?? []).includes("super-admin")) {
    throw redirect({ to: "/" });
  }
  return { userId: account.id, account };
};
