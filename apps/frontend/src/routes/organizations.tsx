import { createFileRoute, redirect } from "@tanstack/react-router";

/** Alias for `/companies` (the real, already-built organizations directory) -- the Organizations
 * Main-Category spec names this path explicitly, but the working catalog page, its data client,
 * and every existing link (`OrganizationsCarousel`, `/companies/$slug`'s "back to list" link)
 * already live at `/companies`; kept as one redirect rather than a second parallel page. */
export const Route = createFileRoute("/organizations")({
  beforeLoad: () => {
    throw redirect({ to: "/companies" });
  },
});
