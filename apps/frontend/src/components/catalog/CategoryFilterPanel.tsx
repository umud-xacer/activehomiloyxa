/**
 * Inline "Filtrlar" card -- one universal layout (title, a responsive grid of price/select
 * inputs, a bottom row of listing-type sub-tabs + a reset button) whose actual FIELDS change per
 * category. The dynamism comes entirely from `fields: FormField[]`, the real per-category
 * dynamic-form-field set an admin already defines in the owner-admin panel -- there is no
 * hardcoded per-category config here, so a category with different attributes (e.g. "Mebel
 * materiallari" vs "Ish o'rni") automatically renders a different field set with zero code
 * changes.
 *
 * Price and the seller-kind sub-tabs are NOT part of `fields` -- they're first-class listing
 * attributes present on every category (price) or derived from a real always-present listing
 * field (`ownerProfileId`), not admin-configured per-category data, so they're handled once here
 * rather than needing to be declared per category.
 */
import { useMemo } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { FormField } from "@/lib/catalog-client";
import { emptyFilterState, type ListingFilterState, type SellerKind } from "./CategoryFilters";

const FILTERABLE_TYPES = new Set(["select", "multiselect", "boolean"]);

const SELLER_KIND_TABS: { value: SellerKind; label: string }[] = [
  { value: "all", label: "Hamma e'lonlar" },
  { value: "business", label: "Biznes" },
  { value: "individual", label: "Jismoniy shaxs" },
];

export function CategoryFilterPanel({
  fields,
  state,
  onChange,
  showSellerKindTabs = true,
}: {
  /** Real per-category dynamic fields. Pass `[]` for a domain with no such system (e.g. real
   * estate today) -- the panel still renders correctly with just price + (optionally) the
   * seller-kind tabs. */
  fields: FormField[];
  state: ListingFilterState;
  onChange: (next: ListingFilterState) => void;
  /** Only meaningful where `ownerProfileId` is really present on each listing in the list
   * already fetched (true for the catalog/goods-service-venue direction). Omit it (pass `false`)
   * for a listing source where that would silently do nothing. */
  showSellerKindTabs?: boolean;
}) {
  const filterableFields = useMemo(
    () => fields.filter((f) => FILTERABLE_TYPES.has(f.fieldType) && (f.options?.length ?? 0) > 0),
    [fields],
  );

  const setAttr = (code: string, value: string) => {
    const attrs = { ...state.attrs };
    if (value) attrs[code] = [value];
    else delete attrs[code];
    onChange({ ...state, attrs });
  };

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-soft sm:p-6">
      <div className="flex items-center gap-2 text-base font-semibold text-foreground">
        <SlidersHorizontal className="size-4 text-primary" />
        Filtrlar
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground">Narx (so'm)</label>
          <div className="mt-1.5 flex items-center gap-2">
            <input
              value={state.priceMin}
              onChange={(e) => onChange({ ...state, priceMin: e.target.value })}
              placeholder="dan"
              inputMode="numeric"
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            />
            <span className="text-muted-foreground">—</span>
            <input
              value={state.priceMax}
              onChange={(e) => onChange({ ...state, priceMax: e.target.value })}
              placeholder="gacha"
              inputMode="numeric"
              className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
        </div>

        {filterableFields.map((field) => {
          const value = state.attrs[field.code]?.[0] ?? "";
          return (
            <div key={field.code}>
              <label className="text-xs font-medium text-muted-foreground">
                {field.label.uz_latn ?? field.code}
              </label>
              <select
                value={value}
                onChange={(e) => setAttr(field.code, e.target.value)}
                className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
              >
                <option value="">Hammasi</option>
                {(field.options ?? []).map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label.uz_latn ?? opt.value}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        {showSellerKindTabs ? (
          <div className="flex flex-wrap items-center gap-1.5">
            {SELLER_KIND_TABS.map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => onChange({ ...state, sellerKind: tab.value })}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                  state.sellerKind === tab.value
                    ? "bg-primary text-primary-foreground"
                    : "text-foreground/70 hover:bg-muted"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        ) : (
          <div />
        )}

        <button
          type="button"
          onClick={() => onChange(emptyFilterState())}
          className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          Filtrlarni o'chirish
        </button>
      </div>
    </div>
  );
}
