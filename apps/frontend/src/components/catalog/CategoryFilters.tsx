/**
 * Client-side filtering for a category's catalog listings (goods/service/venue directions).
 *
 * There's no faceted-search endpoint for these listing kinds yet -- `catalogClient.listingsByCategoryPath`
 * takes only `categoryId`/`limit` (see `catalog-client.ts`). Rather than block the whole "kategoriya
 * bo'yicha filtrlash" requirement on that backend work, this filters the already-fetched page
 * client-side against the category's own dynamic form fields, which is exactly the attribute set an
 * admin defined for that category in the owner-admin panel -- zero hardcoding, same as everything
 * else in this direction. Once a real faceted `/listings` query exists, `applyListingFilters` is the
 * one place to swap for a server round trip; the Sheet UI itself doesn't need to change.
 */
import { useMemo, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Checkbox } from "@/components/ui/checkbox";
import type { CatalogListing, FormField } from "@/lib/catalog-client";

export interface ListingFilterState {
  attrs: Record<string, string[]>;
  priceMin: string;
  priceMax: string;
}

export function emptyFilterState(): ListingFilterState {
  return { attrs: {}, priceMin: "", priceMax: "" };
}

function toNumber(v: unknown): number | null {
  const n = typeof v === "string" ? Number(v) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

export function applyListingFilters(
  listings: CatalogListing[],
  state: ListingFilterState,
): CatalogListing[] {
  const min = state.priceMin ? Number(state.priceMin) : null;
  const max = state.priceMax ? Number(state.priceMax) : null;
  const activeAttrEntries = Object.entries(state.attrs).filter(([, v]) => v.length > 0);

  return listings.filter((listing) => {
    if (min != null || max != null) {
      const price = toNumber(listing.price?.amount);
      if (price == null) return false;
      if (min != null && price < min) return false;
      if (max != null && price > max) return false;
    }
    for (const [code, selected] of activeAttrEntries) {
      const raw = listing.attributes[code];
      const values = Array.isArray(raw) ? raw.map(String) : raw != null ? [String(raw)] : [];
      if (!values.some((v) => selected.includes(v))) return false;
    }
    return true;
  });
}

export function activeFilterCount(state: ListingFilterState): number {
  const attrCount = Object.values(state.attrs).filter((v) => v.length > 0).length;
  return attrCount + (state.priceMin ? 1 : 0) + (state.priceMax ? 1 : 0);
}

const FILTERABLE_TYPES = new Set(["select", "multiselect", "boolean"]);

export function CategoryFiltersSheet({
  fields,
  state,
  onChange,
  resultCount,
}: {
  fields: FormField[];
  state: ListingFilterState;
  onChange: (next: ListingFilterState) => void;
  resultCount: number;
}) {
  const [open, setOpen] = useState(false);
  const filterableFields = useMemo(
    () => fields.filter((f) => FILTERABLE_TYPES.has(f.fieldType) && (f.options?.length ?? 0) > 0),
    [fields],
  );
  const count = activeFilterCount(state);

  const toggleOption = (code: string, value: string) => {
    const current = state.attrs[code] ?? [];
    const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    onChange({ ...state, attrs: { ...state.attrs, [code]: next } });
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/80 transition hover:border-primary/40 hover:text-foreground"
        >
          <SlidersHorizontal className="size-4" />
          Filtrlar
          {count > 0 && (
            <span className="inline-flex size-5 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
              {count}
            </span>
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-sm">
        <SheetHeader>
          <SheetTitle>Filtrlar</SheetTitle>
        </SheetHeader>

        <div className="mt-6 space-y-6">
          <div>
            <label className="text-xs font-medium text-muted-foreground">
              Narx oralig'i (so'm)
            </label>
            <div className="mt-2 flex items-center gap-2">
              <input
                value={state.priceMin}
                onChange={(e) => onChange({ ...state, priceMin: e.target.value })}
                placeholder="Dan"
                inputMode="numeric"
                className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              />
              <span className="text-muted-foreground">—</span>
              <input
                value={state.priceMax}
                onChange={(e) => onChange({ ...state, priceMax: e.target.value })}
                placeholder="Gacha"
                inputMode="numeric"
                className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          {filterableFields.map((field) => (
            <div key={field.code}>
              <label className="text-xs font-medium text-muted-foreground">
                {field.label.uz_latn ?? field.code}
              </label>
              <div className="mt-2 space-y-1">
                {(field.options ?? []).map((opt) => {
                  const checked = (state.attrs[field.code] ?? []).includes(opt.value);
                  return (
                    <label
                      key={opt.value}
                      className="flex cursor-pointer items-center gap-2.5 rounded-lg px-1.5 py-1 text-sm text-foreground/80 hover:bg-muted"
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() => toggleOption(field.code, opt.value)}
                      />
                      {opt.label.uz_latn ?? opt.value}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}

          {filterableFields.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Bu kategoriyada qo'shimcha filtr mavjud emas.
            </p>
          )}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3 border-t border-border pt-4">
          <button
            type="button"
            onClick={() => onChange(emptyFilterState())}
            className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
          >
            Tozalash
          </button>
          <SheetClose asChild>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            >
              {resultCount} ta natijani ko'rish
            </button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  );
}
