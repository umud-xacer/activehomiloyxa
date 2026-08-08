import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { authApi } from "@/lib/auth-client";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { AdminLoginForm } from "@/components/auth/AdminLoginForm";

/**
 * The one entry point into the admin surface (`/admin`, and the secret owner-admin panel at
 * `/$ownerAdminSlug`) that isn't reachable through the public sign-in flow. An already-authenticated
 * non-admin never sees the login form at all -- they're bounced to `/` before it renders, the same
 * "this URL doesn't exist" posture `requireOwnerAdminSlug` uses. The real security boundary stays
 * the backend's own `AuthorizationService` permission checks on every admin API call (see
 * require-auth.ts) -- this route is a social-engineering deterrent, not the access-control
 * mechanism itself.
 */
export const Route = createFileRoute("/boss")({
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: typeof search.redirect === "string" ? search.redirect : undefined,
  }),
  beforeLoad: async () => {
    if (typeof window === "undefined") return;
    // Any failure to establish who's asking -- 401, a network hiccup, anything -- is treated as
    // "not authenticated" and falls through to rendering the login form, matching
    // requireAdmin/requireOwnerAdminSlug's fail-closed convention (require-auth.ts).
    let account: Awaited<ReturnType<typeof authApi.me>>;
    try {
      account = await authApi.me();
    } catch {
      return;
    }
    const isAdmin = (account.roles ?? []).some((r) => r === "super-admin" || r === "administrator");
    throw redirect({ to: isAdmin ? "/admin" : "/" });
  },
  ssr: false,
  head: () => ({
    meta: [{ title: "Sign in" }, { name: "robots", content: "noindex, nofollow" }],
  }),
  component: Page,
});

function Page() {
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const { redirect: redirectTo } = Route.useSearch();

  return (
    <AdminLoginForm
      onSuccess={() => {
        invalidateAuth();
        // `redirectTo` comes from `requireAdmin`/`requireOwnerAdminSlug` bouncing an
        // unauthenticated deep-link here -- send them back where they were headed instead of
        // always dumping them on the generic `/admin` hub.
        if (redirectTo) {
          navigate({ href: redirectTo });
        } else {
          navigate({ to: "/admin" });
        }
      }}
    />
  );
}
