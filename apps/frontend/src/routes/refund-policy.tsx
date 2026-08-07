import { createFileRoute, redirect } from "@tanstack/react-router";

/** Superseded by `/refund` (the path `Footer.tsx`'s `LEGAL_GROUPS` actually links to) -- kept as
 * a redirect, not deleted, since this route may already be bookmarked/indexed under this path. */
export const Route = createFileRoute("/refund-policy")({
  beforeLoad: () => {
    throw redirect({ to: "/refund" });
  },
});
