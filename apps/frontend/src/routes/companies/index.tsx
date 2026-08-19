import { createFileRoute, redirect } from "@tanstack/react-router";

/** The single-page, query-param-filtered directory that used to live here was replaced
 * (2026-08-19) by a proper category-hub + per-category-page architecture: `/organizations` (hub,
 * 6 `MainCategory` cards, no org listings) and `/organizations/$categorySlug` (the actual
 * directory, one category at a time). Kept as a redirect, not deleted, so old bookmarks/links
 * (and `companies/$slug.tsx`'s own "back to list" link) still resolve somewhere sensible --
 * exactly the same precedent `routes/organizations.tsx` itself used to redirect here before this
 * swap, just now pointing the other way. */
export const Route = createFileRoute("/companies/")({
  beforeLoad: () => {
    throw redirect({ to: "/organizations" });
  },
});
