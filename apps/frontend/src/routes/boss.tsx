import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router";
import { authApi } from "@/lib/auth-client";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { AdminLoginForm } from "@/components/auth/AdminLoginForm";

/**
 * The one entry point into the admin surface (`/admin`, `/owner-admin`) that isn't reachable
 * through the public sign-in flow. An already-authenticated non-admin never sees the login form
 * at all -- they're bounced to `/` before it renders, the same "this URL doesn't exist" posture
 * `requireSuperAdmin` uses. The real security boundary stays the backend's own
 * `AuthorizationService` permission checks on every admin API call (see require-auth.ts) -- this
 * route is a social-engineering deterrent, not the access-control mechanism itself.
 */
export const Route = createFileRoute("/boss")({
  beforeLoad: async () => {
    if (typeof window === "undefined") return;
    // Any failure to establish who's asking -- 401, a network hiccup, anything -- is treated as
    // "not authenticated" and falls through to rendering the login form, matching
    // requireAdmin/requireSuperAdmin's fail-closed convention (require-auth.ts).
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

  return (
    <AdminLoginForm
      onSuccess={() => {
        invalidateAuth();
        navigate({ to: "/admin" });
      }}
    />
  );
}
