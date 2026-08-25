/**
 * Inserts one in-feed ad marker after every `every`-th real item, but only where a resolved
 * banner actually exists (`ads.length` caps how many ad markers ever appear) -- never an "ad
 * position with nothing to show" gap in the grid. Pure and pagination-safe: callers using
 * `useInfiniteQuery` pass the full accumulated `items` array each render, so ad positions never
 * reset or shift as more pages load in.
 */
export type FeedEntry<T> =
  { kind: "item"; item: T; key: string | number } | { kind: "ad"; adIndex: number; key: string };

export function interleaveAds<T>(
  items: readonly T[],
  every: number,
  adCount: number,
  itemKey: (item: T, index: number) => string | number,
): FeedEntry<T>[] {
  const out: FeedEntry<T>[] = [];
  let adIndex = 0;
  items.forEach((item, i) => {
    out.push({ kind: "item", item, key: itemKey(item, i) });
    if ((i + 1) % every === 0 && adIndex < adCount) {
      out.push({ kind: "ad", adIndex, key: `ad-${adIndex}` });
      adIndex += 1;
    }
  });
  return out;
}
