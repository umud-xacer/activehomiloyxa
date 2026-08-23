/**
 * Inline "Filtrlar" card -- one universal layout (title, a subcategory select, a responsive grid
 * of price/select/text/number inputs, a bottom row of listing-type sub-tabs + a reset button)
 * whose actual FIELDS change per category. The dynamism comes entirely from `fields: FormField[]`,
 * the real per-category dynamic-form-field set an admin already defines in the owner-admin panel
 * -- there is no hardcoded per-category config here, so a category with different attributes
 * (e.g. "Mebel materiallari" vs "Ish o'rni" vs "Ko'p qavatli binolar") automatically renders a
 * different field set with zero code changes. `fields` is trusted as-is here -- any restriction
 * to only the fields a given filtering mechanism can actually honor (e.g. the real-estate
 * direction's server-side search facets) is the caller's job, done before `fields` is ever passed
 * in (see `PropertyDirectionView` in `routes/categories/$.tsx`), not this component's.
 *
 * The subcategory select is NOT a `fields` entry -- picking one navigates to a different category
 * page entirely (a different real taxonomy node, with its own real `fields`), which is what makes
 * "cascading" filters work here: no nested per-subcategory config to maintain, the next page's own
 * `fields` fetch does that for free.
 *
 * Price and the seller-kind sub-tabs are NOT part of `fields` either -- they're first-class
 * listing attributes present on every category (price) or derived from a real always-present
 * listing field (`ownerProfileId`), not admin-configured per-category data, so they're handled
 * once here rather than needing to be declared per category.
 */
import { useMemo } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { FormField } from "@/lib/catalog-client";
import { emptyFilterState, type ListingFilterState, type SellerKind } from "./CategoryFilters";

/** `date`/`range`/`location`/`file` fields have no simple, honest single-control UI here (a real
 * range needs its own dan/gacha pair like price already gets, a location needs a map picker,
 * etc.) -- skipped rather than faked. */
const SUPPORTED_FIELD_TYPES = new Set(["select", "multiselect", "boolean", "text", "number"]);

const SELLER_KIND_TABS: { value: SellerKind; label: string }[] = [
  { value: "all", label: "Hamma e'lonlar" },
  { value: "business", label: "Biznes" },
  { value: "individual", label: "Jismoniy shaxs" },
];

export interface SubcategoryOption {
  value: string;
  label: string;
}

export function CategoryFilterPanel({
  fields,
  state,
  onChange,
  showSellerKindTabs = true,
  subcategory,
}: {
  /** Real per-category dynamic fields. Pass `[]` for a category whose form has none. */
  fields: FormField[];
  state: ListingFilterState;
  onChange: (next: ListingFilterState) => void;
  /** Only meaningful where `ownerProfileId` is really present on each listing in the list
   * already fetched (true for the catalog/goods-service-venue direction). Omit it (pass `false`)
   * for a listing source where that would silently do nothing. */
  showSellerKindTabs?: boolean;
  /** Renders as the panel's first field when the current category has real children or siblings
   * to switch between. Selecting one is a real navigation (a different category page), not a
   * client-side filter -- the caller owns `onChange`/what "selecting" means. */
  subcategory?: {
    label: string;
    value: string;
    options: SubcategoryOption[];
    onChange: (value: string) => void;
  };
}) {
  // `facetEligible` is deliberately NOT checked here -- it only matters for a filter that goes
  // through the backend's search-facet whitelist (the real-estate/property direction, which
  // pre-filters `fields` against `GET /search/facets` itself before ever passing them in here).
  // For the catalog/goods-service-venue direction `fields` come from, filtering happens
  // client-side against attributes already fetched with the listing, so it works regardless of
  // facetEligible -- gating on it here too was a real bug: most categories' fields are marked
  // facetEligible: false (that flag tracks search-facet config, not "can a human filter by this
  // at all"), so it silently emptied the panel for every category except the one whose fields
  // happened to be facetEligible (confirmed live: "Mebel salonlari"'s all-3-fields were
  // facetEligible: false, "Hostel"'s price_unit was too).
  const filterableFields = useMemo(
    () =>
      fields
        .filter((f) => {
          if (!SUPPORTED_FIELD_TYPES.has(f.fieldType)) return false;
          if ((f.fieldType === "select" || f.fieldType === "multiselect") && !f.options?.length) {
            return false;
          }
          return true;
        })
        .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    [fields],
  );

  const setAttr = (code: string, value: string) => {
    const attrs = { ...state.attrs };
    if (value) attrs[code] = [value];
    else delete attrs[code];
    onChange({ ...state, attrs });
  };

  const fieldInputClass =
    "mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30";

  return (
    <div className="rounded-3xl border border-border bg-card p-5 shadow-soft sm:p-6">
      <div className="flex items-center gap-2 text-base font-semibold text-foreground">
        <SlidersHorizontal className="size-4 text-primary" />
        Filtrlar
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {subcategory && subcategory.options.length > 0 && (
          <div>
            <label className="text-xs font-medium text-muted-foreground">{subcategory.label}</label>
            <select
              value={subcategory.value}
              onChange={(e) => subcategory.onChange(e.target.value)}
              className={fieldInputClass}
            >
              {!subcategory.value && <option value="">Hammasi</option>}
              {subcategory.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
        )}

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
          const label = field.label.uz_latn ?? field.code;

          if (field.fieldType === "text") {
            return (
              <div key={field.code}>
                <label className="text-xs font-medium text-muted-foreground">{label}</label>
                <input
                  value={value}
                  onChange={(e) => setAttr(field.code, e.target.value)}
                  className={fieldInputClass}
                />
              </div>
            );
          }

          if (field.fieldType === "number") {
            return (
              <div key={field.code}>
                <label className="text-xs font-medium text-muted-foreground">{label}</label>
                <input
                  value={value}
                  onChange={(e) => setAttr(field.code, e.target.value)}
                  inputMode="numeric"
                  className={fieldInputClass}
                />
              </div>
            );
          }

          // select / multiselect (real admin-defined options) / boolean (always exactly two
          // states, so a fixed Ha/Yo'q pair is honest even though the field itself has no
          // `options` list of its own).
          const options =
            field.fieldType === "boolean"
              ? [
                  { value: "true", label: "Ha" },
                  { value: "false", label: "Yo'q" },
                ]
              : (field.options ?? []).map((opt) => ({
                  value: opt.value,
                  label: opt.label.uz_latn ?? opt.value,
                }));

          return (
            <div key={field.code}>
              <label className="text-xs font-medium text-muted-foreground">{label}</label>
              <select
                value={value}
                onChange={(e) => setAttr(field.code, e.target.value)}
                className={fieldInputClass}
              >
                <option value="">Hammasi</option>
                {options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
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
