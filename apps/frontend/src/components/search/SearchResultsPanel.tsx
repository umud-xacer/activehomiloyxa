/**
 * Site-wide search -- rebuilt 2026-08-19 from a centered `CommandDialog` (Radix Dialog overlay)
 * into a self-contained, non-modal dropdown: an input + results list that a caller positions via
 * a wrapping `relative` container (`className="absolute ... top-full"` on this component). No
 * portal, no backdrop -- closes on outside click / Escape / route navigation instead of Radix's
 * dialog semantics. Every earlier `GlobalSearchDialog` call site (Navbar, Hero, category pages)
 * now renders this in place of the old modal.
 *
 * Three result groups beyond the query/category suggestions: listings (`GET /search`, already
 * existed), business profiles ("Tashkilotlar va brendlar") and categories ("Kategoriyalar") --
 * both new, filtered client-side against a single shared fetch (14 orgs / ~500 categories is
 * cheap to hold in memory and filter per keystroke; a network round trip per debounce tick for
 * these two would be pure waste next to the real `/search` call already doing that for listings).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate, Link } from "@tanstack/react-router";
import {
  Search as SearchIcon,
  Loader2,
  Package,
  Building2,
  LayoutGrid,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { Command, CommandInput, CommandList, CommandGroup, CommandItem } from "@/components/ui/command";
import { searchApi, type Suggestion, type SearchHit } from "@/lib/search-client";
import { catalogClient, formatUzs, type CategorySummary } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { businessProfilesApi, type BusinessProfile } from "@/lib/business-profiles-client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Scopes the live listing preview (and the "barcha natijalar" full-search link) to one
   * category's subtree -- pass this from a category page's own search entry point. */
  categoryPathPrefix?: string;
  className?: string;
  placeholder?: string;
  /** Controlled-query mode: when both are passed, the panel renders results only -- no input of
   * its own -- and reads/drives the caller's own visible input instead. Used wherever the trigger
   * already IS a real search box (Hero's own input, Navbar's inline-expanding one) so typing lands
   * directly in that one field instead of a second, redundant input appearing inside the dropdown
   * below it (the exact "ikkita qidiruv qatori" duplicate-box complaint this replaced). */
  externalQuery?: string;
  onExternalQueryChange?: (value: string) => void;
}

function companyName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
}

/** Plain Levenshtein edit distance -- small inputs only (a single word against a single word),
 * so the classic O(n*m) DP table is fine, no need for a library. */
function levenshtein(a: string, b: string): number {
  const dp: number[][] = Array.from({ length: a.length + 1 }, (_, i) =>
    Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)),
  );
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[a.length][b.length];
}

/** Same edit-distance budget the backend's OpenSearch `fuzziness: AUTO` uses (search/infrastructure/
 * opensearch_index.py) -- kept identical on purpose so "how wrong can a typo be and still match"
 * feels consistent whether the hit came from the server or this client-side org/category list. */
function fuzzyThreshold(len: number): number {
  if (len < 3) return 0;
  if (len < 6) return 1;
  return 2;
}

/** Substring match first (cheap, handles normal prefix-as-you-type search); falls back to a
 * per-word edit-distance check only when that fails, so a typo ("mibel") still finds "mebel
 * ustasi" the same way the backend's fuzzy listing search already does -- orgs/categories had no
 * such tolerance before, a literal-only `.includes()`. Returns which kind of match it was so the
 * "did you mean" banner only fires for the fuzzy case, never for a plain exact hit. */
function fuzzyMatch(haystack: string, needle: string): "exact" | "fuzzy" | null {
  if (haystack.includes(needle)) return "exact";
  const threshold = fuzzyThreshold(needle.length);
  if (threshold === 0) return null;
  const isFuzzy = haystack
    .split(/\s+/)
    .some((word) => word.length > 0 && levenshtein(word, needle) <= threshold);
  return isFuzzy ? "fuzzy" : null;
}

// Shared in-memory cache for orgs, one per browser session -- a small, rarely-changing list, so
// re-fetching it on every panel open (let alone every keystroke) would be wasted work.
// `catalogClient.listCategories()` already TTL-caches itself the same way, no wrapper needed here.
let orgsCache: Promise<BusinessProfile[]> | null = null;

export function SearchResultsPanel({
  open,
  onOpenChange,
  categoryPathPrefix,
  className,
  placeholder = "Mahsulot, tashkilot, xizmat yoki kategoriya qidiring...",
  externalQuery,
  onExternalQueryChange,
}: Props) {
  const navigate = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const controlled = externalQuery !== undefined && onExternalQueryChange !== undefined;
  const [internalQuery, setInternalQuery] = useState("");
  const query = controlled ? externalQuery : internalQuery;
  const setQuery = controlled ? onExternalQueryChange : setInternalQuery;
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [orgs, setOrgs] = useState<BusinessProfile[]>([]);
  const [categories, setCategories] = useState<CategorySummary[]>([]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSuggestions([]);
      setHits([]);
      setLoading(false);
      return;
    }
    orgsCache ??= businessProfilesApi.listPublic().catch(() => []);
    orgsCache.then(setOrgs);
    catalogClient.listCategories().then(setCategories).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) {
      setSuggestions([]);
      setHits([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const controller = new AbortController();
    const timer = setTimeout(() => {
      Promise.all([
        searchApi.suggest(q, 5, controller.signal),
        searchApi.search({ q, categoryPathPrefix, limit: 5, signal: controller.signal }),
      ])
        .then(([sugg, res]) => {
          setSuggestions(sugg);
          setHits(res.items);
        })
        .catch(() => {
          // aborted (superseded by a newer keystroke) or a transient error -- leave stale
          // results on screen rather than flashing an empty state.
        })
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open, categoryPathPrefix]);

  // Outside click / Escape close -- Radix's Dialog gave us this for free before; a plain
  // positioned popover has to replicate it by hand.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) onOpenChange(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onOpenChange(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onOpenChange]);

  function runFullSearch(q: string) {
    onOpenChange(false);
    navigate({ to: "/search", search: { q } });
  }

  function goToListing(listingId: string) {
    onOpenChange(false);
    navigate({ to: "/listing/$listingId", params: { listingId } });
  }

  if (!open) return null;

  const trimmed = query.trim();
  const normalized = trimmed.toLowerCase();

  const orgMatches =
    normalized.length >= 2
      ? orgs
          .map((o) => {
            const haystack = [companyName(o), o.description?.uz_latn, o.description?.ru]
              .filter(Boolean)
              .join(" ")
              .toLowerCase();
            return { org: o, kind: fuzzyMatch(haystack, normalized), name: companyName(o) };
          })
          .filter((m): m is typeof m & { kind: "exact" | "fuzzy" } => m.kind !== null)
          .slice(0, 4)
      : [];
  const matchedOrgs = orgMatches.map((m) => m.org);

  const categoryMatches =
    normalized.length >= 2
      ? categories
          .map((c) => {
            const label = categoryLabel(c.name, "uz");
            return { category: c, kind: fuzzyMatch(label.toLowerCase(), normalized), label };
          })
          .filter((m): m is typeof m & { kind: "exact" | "fuzzy" } => m.kind !== null)
          .slice(0, 4)
      : [];
  const matchedCategories = categoryMatches.map((m) => m.category);

  // "Balki ... demoqchi bo'lgandirsiz?" -- only when NOTHING anywhere (listings, orgs,
  // categories) contains the literal typed text, but a fuzzy/edit-distance correction still
  // found something. Listing hits don't carry an exact/fuzzy flag from the backend, so an exact
  // literal-substring check against their own titles stands in for "was this corrected".
  const hasExactHit = hits.some((h) => h.title.toLowerCase().includes(normalized));
  const hasExactOrgOrCategory =
    orgMatches.some((m) => m.kind === "exact") || categoryMatches.some((m) => m.kind === "exact");
  const didYouMean =
    !loading && normalized.length >= 2 && !hasExactHit && !hasExactOrgOrCategory
      ? (hits[0]?.title ??
        orgMatches.find((m) => m.kind === "fuzzy")?.name ??
        categoryMatches.find((m) => m.kind === "fuzzy")?.label ??
        null)
      : null;

  const showEmpty =
    !loading &&
    trimmed.length >= 2 &&
    hits.length === 0 &&
    suggestions.length === 0 &&
    matchedOrgs.length === 0 &&
    matchedCategories.length === 0;

  return (
    <div
      ref={rootRef}
      className={
        className ??
        "absolute left-0 right-0 top-full z-50 mt-2 overflow-hidden rounded-2xl border border-slate-100 bg-card shadow-xl"
      }
    >
      <Command
        shouldFilter={false}
        className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:text-muted-foreground"
      >
        {!controlled && (
          <CommandInput
            autoFocus
            value={query}
            onValueChange={setQuery}
            placeholder={placeholder}
            className="h-12 text-[15px]"
            onKeyDown={(e) => {
              if (e.key === "Enter" && trimmed && suggestions.length === 0 && hits.length === 0) {
                runFullSearch(trimmed);
              }
            }}
          />
        )}
        <CommandList className="max-h-[420px]">
          {loading && (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Qidirilmoqda…
            </div>
          )}
          {didYouMean && (
            <button
              type="button"
              onClick={() => setQuery(didYouMean)}
              className="flex w-full items-center gap-2 border-b border-slate-100 bg-blue-50/50 px-4 py-2.5 text-left text-sm text-foreground transition hover:bg-blue-50"
            >
              <SearchIcon className="size-3.5 shrink-0 text-primary" />
              Balki{" "}
              <span className="font-semibold text-primary">&quot;{didYouMean}&quot;</span>{" "}
              demoqchi bo'lgandirsiz?
            </button>
          )}
          {/* Deliberately a plain div, not cmdk's own `<CommandEmpty>` -- that primitive shows
              itself based on cmdk's own "zero items anywhere in the list" detection, which never
              fires here: the "Qidiruv" group below always renders one item (the full-search
              link), so cmdk permanently treats the list as non-empty and silently drops
              `CommandEmpty`'s children regardless of this component's own `showEmpty` condition
              wrapping it -- confirmed live (rendered zero DOM nodes for a genuinely-zero-match
              query). This custom message needs its own unconditional element instead. */}
          {showEmpty && (
            <div className="flex flex-col items-center gap-1.5 py-8">
              <SearchIcon className="size-6 text-muted-foreground/50" />
              <p className="font-medium text-foreground">Afsuski, bunday tashkilot topilmadi</p>
              <p className="text-xs text-muted-foreground">
                Boshqa nom yoki kalit so'z bilan qayta urinib ko'ring.
              </p>
            </div>
          )}
          {!loading && trimmed.length > 0 && (
            <CommandGroup heading="Qidiruv">
              <ResultItem
                onSelect={() => runFullSearch(trimmed)}
                icon={<SearchIcon className="size-4 text-muted-foreground" />}
              >
                <span>&quot;{trimmed}&quot; uchun barcha natijalar</span>
                <ArrowRight className="ml-auto size-3.5 opacity-50" />
              </ResultItem>
            </CommandGroup>
          )}
          {!loading && suggestions.length > 0 && (
            <CommandGroup heading="Takliflar">
              {suggestions.map((s, i) => (
                <ResultItem
                  key={`sugg-${i}-${s.text}`}
                  onSelect={() =>
                    s.type === "LISTING" && s.refId ? goToListing(s.refId) : runFullSearch(s.text)
                  }
                  icon={<SearchIcon className="size-4 text-muted-foreground" />}
                >
                  <span>{s.text}</span>
                </ResultItem>
              ))}
            </CommandGroup>
          )}
          {!loading && hits.length > 0 && (
            <CommandGroup heading="Mahsulotlar va e'lonlar">
              {hits.map((hit) => (
                <ResultItem
                  key={hit.listingId}
                  onSelect={() => goToListing(hit.listingId)}
                  className="gap-3"
                >
                  <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-muted">
                    {hit.thumbnailUrl ? (
                      <img src={hit.thumbnailUrl} alt="" className="size-full object-cover" />
                    ) : (
                      <Package className="size-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{hit.title}</div>
                    {hit.categoryPath && (
                      <div className="truncate text-xs text-muted-foreground">
                        {hit.categoryPath}
                      </div>
                    )}
                  </div>
                  {hit.price && (
                    <span className="shrink-0 text-xs font-semibold text-foreground/80">
                      {formatUzs(hit.price.amount)}
                    </span>
                  )}
                </ResultItem>
              ))}
            </CommandGroup>
          )}
          {matchedOrgs.length > 0 && (
            <CommandGroup heading="Tashkilotlar va brendlar">
              {matchedOrgs.map((org) => (
                <ResultItem
                  key={org.id}
                  onSelect={() => {
                    onOpenChange(false);
                    navigate({ to: "/companies/$slug", params: { slug: org.slug || org.id } });
                  }}
                  className="gap-3"
                >
                  <div className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-white">
                    <Building2 className="size-4 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1 truncate font-medium">
                      {companyName(org)}
                      {org.badge?.status === "VALID" && (
                        <ShieldCheck className="size-3.5 shrink-0 text-primary" />
                      )}
                    </div>
                  </div>
                </ResultItem>
              ))}
            </CommandGroup>
          )}
          {matchedCategories.length > 0 && (
            <CommandGroup heading="Kategoriyalar">
              {matchedCategories.map((cat) => (
                <ResultItem
                  key={cat.id}
                  onSelect={() => {
                    onOpenChange(false);
                    navigate({ to: `/categories/${cat.path.replace(/^\//, "")}` });
                  }}
                >
                  <LayoutGrid className="size-4 text-muted-foreground" />
                  <span>{categoryLabel(cat.name, "uz")}</span>
                  <ArrowRight className="ml-auto size-3.5 opacity-50" />
                </ResultItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
    </div>
  );
}

/** Shared item chrome for every row in the panel -- soft slate/blue hover+selected state
 * (`data-[selected=true]:bg-blue-50/70`) instead of `CommandItem`'s shared default
 * `bg-accent` (a cyan `oklch(.72 .16 200)`, jarring here and specifically what was reported).
 * Left local to this file rather than changed on the shared primitive -- `CommandItem` also
 * backs the dashboard's own `CommandPalette`, which should keep its existing look. */
function ResultItem({
  children,
  onSelect,
  icon,
  className = "",
}: {
  children: React.ReactNode;
  onSelect: () => void;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <CommandItem
      onSelect={onSelect}
      className={`cursor-pointer rounded-xl px-3 py-2.5 data-[selected=true]:bg-blue-50/70 data-[selected=true]:text-foreground ${className}`}
    >
      {icon}
      {children}
    </CommandItem>
  );
}
