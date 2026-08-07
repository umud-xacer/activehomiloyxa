import { createFileRoute, redirect } from "@tanstack/react-router";

/** Superseded by `/rules` (the path `Footer.tsx`'s `LEGAL_GROUPS` actually links to) -- kept as a
 * redirect, not deleted, since this route may already be bookmarked/indexed under this path. */
export const Route = createFileRoute("/ad-rules")({
  beforeLoad: () => {
    throw redirect({ to: "/rules" });
  },
});
