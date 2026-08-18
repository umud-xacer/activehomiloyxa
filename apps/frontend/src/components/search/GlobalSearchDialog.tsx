/**
 * Site-wide search: a ⌘K-style dialog (built on the same `cmdk`-based `Command` primitives as
 * the dashboard's `CommandPalette`) that live-queries the real backend as the user types --
 * `GET /search/suggest` for query/category completions and `GET /search` (small `limit`) for an
 * actual listing preview, so typing a product name shows both textual suggestions and the
 * matching (and cross-script/fuzzy "similar") products directly, not just a bare text list.
 * `shouldFilter={false}` on the dialog turns off cmdk's own client-side fuzzy filter -- the
 * results are already ranked server-side, and re-filtering them against the raw query client-side
 * would fight the backend's cross-script (Latin/Cyrillic) matching.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Search as SearchIcon, Loader2, Package, ArrowRight } from "lucide-react";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { searchApi, type Suggestion, type SearchHit } from "@/lib/search-client";
import { formatUzs } from "@/lib/catalog-client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Scopes the live preview (and the "barcha natijalar" full-search link) to one category's
   * subtree -- pass this from a category page's own search entry point. */
  categoryPathPrefix?: string;
}

export function GlobalSearchDialog({ open, onOpenChange, categoryPathPrefix }: Props) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSuggestions([]);
      setHits([]);
      setLoading(false);
    }
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

  function runFullSearch(q: string) {
    onOpenChange(false);
    navigate({ to: "/search", search: { q } });
  }

  function goToListing(listingId: string) {
    onOpenChange(false);
    navigate({ to: "/listing/$listingId", params: { listingId } });
  }

  const trimmed = query.trim();
  const showEmpty =
    !loading && trimmed.length >= 2 && hits.length === 0 && suggestions.length === 0;

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} shouldFilter={false}>
      <CommandInput
        value={query}
        onValueChange={setQuery}
        placeholder="Mahsulot, xizmat yoki kategoriya qidiring..."
        onKeyDown={(e) => {
          if (e.key === "Enter" && trimmed && suggestions.length === 0 && hits.length === 0) {
            runFullSearch(trimmed);
          }
        }}
      />
      <CommandList>
        {loading && (
          <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Qidirilmoqda…
          </div>
        )}
        {showEmpty && <CommandEmpty>Hech narsa topilmadi.</CommandEmpty>}
        {!loading && trimmed.length > 0 && (
          <CommandGroup heading="Qidiruv">
            <CommandItem value={`__all__${trimmed}`} onSelect={() => runFullSearch(trimmed)}>
              <SearchIcon />
              <span>&quot;{trimmed}&quot; uchun barcha natijalar</span>
              <ArrowRight className="ml-auto size-3.5 opacity-50" />
            </CommandItem>
          </CommandGroup>
        )}
        {!loading && suggestions.length > 0 && (
          <CommandGroup heading="Takliflar">
            {suggestions.map((s, i) => (
              <CommandItem
                key={`${s.type}-${s.text}-${i}`}
                value={`sugg-${i}-${s.text}`}
                onSelect={() =>
                  s.type === "LISTING" && s.refId ? goToListing(s.refId) : runFullSearch(s.text)
                }
              >
                <SearchIcon />
                <span>{s.text}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {!loading && hits.length > 0 && (
          <CommandGroup heading="Mahsulotlar">
            {hits.map((hit) => (
              <CommandItem
                key={hit.listingId}
                value={`hit-${hit.listingId}-${hit.title}`}
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
                    <div className="truncate text-xs text-muted-foreground">{hit.categoryPath}</div>
                  )}
                </div>
                {hit.price && (
                  <span className="shrink-0 text-xs font-semibold text-foreground/80">
                    {formatUzs(hit.price.amount)}
                  </span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
