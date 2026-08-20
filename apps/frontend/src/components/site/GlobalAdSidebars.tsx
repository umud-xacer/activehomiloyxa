/**
 * The two sticky side-gutter ad slots (2xl+ screens only), shared between `AppShell` (every
 * inner page) and the homepage (`routes/index.tsx`, which composes its own layout instead of
 * using `AppShell`). Pulled out once so both call sites render identically instead of drifting.
 *
 * Positioning: previously `fixed inset-y-0`, which pins to the *viewport* for the page's entire
 * scroll range with nothing to ever stop it -- confirmed live, it rode straight over the footer.
 * `absolute inset-y-0` here instead, scoped to the caller's own `relative`-positioned content
 * wrapper (everything except `<Footer/>` -- see `AppShell.tsx`/`routes/index.tsx`) -- that
 * wrapper's own height is exactly "all the real content," ending precisely where the footer
 * begins, so the inner `sticky` element runs out of room to stick in and scrolls off with its
 * container's bottom edge right as the footer reaches it. No IntersectionObserver/JS needed --
 * this is what CSS `position: sticky` is for, it stops at its own containing block's boundary by
 * definition, and that boundary is deliberately drawn at "everything but the footer."
 */
import { AdSlot } from "./AdSlot";

export function GlobalAdSidebars() {
  return (
    <>
      <div className="pointer-events-none absolute inset-y-0 left-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_LEFT" variant="sidebar" />
        </div>
      </div>
      <div className="pointer-events-none absolute inset-y-0 right-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_RIGHT" variant="sidebar" />
        </div>
      </div>
    </>
  );
}
