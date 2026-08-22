/**
 * The two sticky side-gutter ad slots (2xl+ screens only) for `AppShell` (every inner page --
 * dashboard, /properties, /map, etc). The homepage does NOT use this anymore: it renders its own
 * `HOMEPAGE_SIDEBAR_LEFT/RIGHT` ad slots scoped inside `Hero.tsx` instead, because reserving a
 * page-spanning grid column for them (this component's approach) shrinks every section's own
 * width to make room, including Hero's navy band, which needs to stay a true `w-full`
 * edge-to-edge section -- see `Hero.tsx`'s own comment. `AppShell`'s inner pages have no such
 * full-bleed-background requirement, so the grid-column approach is still the right one here.
 *
 * Positioning: these render as real grid columns (`col-start-1`/`col-start-3`) inside
 * `AppShell.tsx`'s `2xl:grid-cols-[200px_minmax(0,1fr)_200px]` wrapper, with the main content in
 * `col-start-2` -- NOT `absolute`/`fixed` overlays. An overlay approach was tried first
 * (`absolute inset-y-0 left-0/right-0`) but it floats independently of how wide the centered
 * content actually renders at a given viewport, so on any screen narrower than "content's own
 * max-width plus 2x200px of gutter" (a wide, common range -- confirmed live e.g. at ~1568px
 * viewport, well within that gap) the sidebar visibly sat on top of real content instead of
 * beside it. A real grid column can't overlap the content column by construction: the browser
 * reserves the 200px track and the content column's own `max-w-*` simply has less room to grow
 * into, so there is no viewport width at which the two can collide.
 *
 * The row still needs the same two-level "don't stretch the sticky child" structure as before,
 * just one level: the grid parent (`AppShell.tsx`) uses the CSS Grid default `align-items:
 * stretch`, so this column div stretches to the full row height (== all the real content's
 * height, since the content column is the tallest item in the row) -- that's what gives the
 * inner `sticky top-32` element room to actually stick as you scroll. But THIS div is itself a
 * flex container with `items-start`, so *its own* child (the sticky div) does NOT stretch to
 * fill it -- without that, the sticky div's box would be as tall as the whole page and degenerate
 * to behaving like `position: static` (confirmed live in the previous overlay version, same
 * underlying CSS mechanism, see git history).
 */
import { AdSlot } from "./AdSlot";

export function GlobalAdSidebars() {
  return (
    <>
      <div className="z-20 col-start-1 row-start-1 hidden w-[200px] items-start justify-center pt-32 2xl:flex">
        <div className="sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_LEFT" variant="sidebar" />
        </div>
      </div>
      <div className="z-20 col-start-3 row-start-1 hidden w-[200px] items-start justify-center pt-32 2xl:flex">
        <div className="sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_RIGHT" variant="sidebar" />
        </div>
      </div>
    </>
  );
}
