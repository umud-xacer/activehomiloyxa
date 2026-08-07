import { createFileRoute, redirect } from "@tanstack/react-router";

/** Superseded by `/offer` (the path `Footer.tsx`'s `LEGAL_GROUPS` actually links to) -- kept as a
 * redirect, not deleted, since this route may already be bookmarked/indexed under this path. */
export const Route = createFileRoute("/public-offer")({
  beforeLoad: () => {
    throw redirect({ to: "/offer" });
  },
});
