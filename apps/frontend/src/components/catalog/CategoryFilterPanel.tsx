/**
 * "Filtrlar" -- one universal layout (title, a subcategory select, a responsive grid of
 * price/select/text/number inputs, a bottom row of listing-type sub-tabs + a reset button)
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
 *
 * OLX-style responsive split (2026-08-26): desktop shows only the primary handful of fields
 * (subcategory + price always, plus up to a few more by `order`) with the rest tucked behind a
 * "Boshqa filtrlar" accordion; below `md:` the whole inline panel is replaced by one compact
 * "Filtrlar" trigger that opens the exact same field set in a bottom sheet (`components/ui/
 * sheet.tsx`), with its own local draft so filters only actually apply when "Natijalarni
 * ko'rsatish" is tapped (clearing/discarding without touching results is `Filtrlarni tozalash`/
 * closing the sheet). `renderPanelBody` below is the one render path both containers use -- no
 * duplicated field-rendering logic between them.
 */
import { useEffect, useMemo, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { FormField } from "@/lib/catalog-client";
import {
  emptyFilterState,
  activeFilterCount,
  type ListingFilterState,
  type SellerKind,
} from "./CategoryFilters";
import { useDisplayCurrency } from "@/lib/currency";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";

/** `date`/`range`/`location`/`file` fields have no simple, honest single-control UI here (a real
 * range needs its own dan/gacha pair like price already gets, a location needs a map picker,
 * etc.) -- skipped rather than faked. */
const SUPPORTED_FIELD_TYPES = new Set(["select", "multiselect", "boolean", "text", "number"]);

/** Price isn't a `FormField` (it's a first-class listing attribute, not admin-configured per
 * category -- see the module docstring), so it can't carry a real `order`. It used to render
 * unconditionally right after the subcategory select, ahead of every field regardless of that
 * field's own `order` -- confirmed wrong live (2026-08-23, Kotejlar UX ask): with `district` at
 * `order: 1`, the requested grid was subcategory/district/price/rooms, not subcategory/price/
 * district/rooms. Giving price a fixed virtual order and merging it into the same sort lets a
 * category push exactly one field ahead of price (by giving that field `order: 1`, as the
 * real-estate form's `district` now does) while every other field still falls in after it. */
const PRICE_ORDER = 1.5;

/** Desktop's "asosiy 3-4 ta filtr" budget -- subcategory (if present) + price always count
 * against it, whatever's left goes to fields sorted by `order`; anything beyond that moves to the
 * "Boshqa filtrlar" accordion. */
const PRIMARY_FIELD_BUDGET = 4;

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
  const [displayCurrency] = useDisplayCurrency();
  const priceLabel = displayCurrency === "USD" ? "Narx ($)" : "Narx (so'm)";

  const [mobileOpen, setMobileOpen] = useState(false);
  const [mobileDraft, setMobileDraft] = useState<ListingFilterState>(state);
  // Re-sync the sheet's own draft from the committed state every time it's (re)opened -- so a
  // reset triggered elsewhere (e.g. desktop's own reset button, on a resize) is reflected instead
  // of the sheet reviving stale, already-discarded values.
  useEffect(() => {
    if (mobileOpen) setMobileDraft(state);
  }, [mobileOpen, state]);

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

  const fieldInputClass =
    "mt-1.5 w-full rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20";

  function renderField(
    field: FormField,
    fieldState: ListingFilterState,
    setAttr: (code: string, value: string) => void,
  ) {
    const value = fieldState.attrs[field.code]?.[0] ?? "";
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

    // select / multiselect (real admin-defined options) / boolean (always exactly two states, so
    // a fixed Ha/Yo'q pair is honest even though the field itself has no `options` list of its
    // own).
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
  }

  const fieldsBeforePrice = filterableFields.filter((f) => (f.order ?? 0) < PRICE_ORDER);
  const fieldsAfterPrice = filterableFields.filter((f) => (f.order ?? 0) >= PRICE_ORDER);
  const hasSubcategorySlot = Boolean(subcategory && subcategory.options.length > 0);
  const usedPrimarySlots = (hasSubcategorySlot ? 1 : 0) + fieldsBeforePrice.length + 1; // +1 = price
  const remainingPrimarySlots = Math.max(0, PRIMARY_FIELD_BUDGET - usedPrimarySlots);
  const primaryFieldsAfterPrice = fieldsAfterPrice.slice(0, remainingPrimarySlots);
  const accordionFields = fieldsAfterPrice.slice(remainingPrimarySlots);

  // A plain function returning JSX, deliberately NOT a nested component (`<PanelBody />`) --
  // defining a component inside another component's render body gives it a brand-new identity on
  // every re-render, which makes React treat the returned tree as a different element type and
  // remount it wholesale, including every `<input>` inside -- confirmed live as the ROOT CAUSE of
  // a real bug: typing into the mobile sheet's price field only ever kept the first 1-2
  // characters (each keystroke's `setMobileDraft` re-render remounted the input, dropping focus
  // immediately after). Calling this as a plain function (`{renderPanelBody({...})}`) instead of
  // JSX (`<PanelBody ... />`) makes React reconcile the returned elements directly against the
  // previous render's, exactly like any other conditional JSX in this component -- no remount.
  function renderPanelBody({
    fieldState,
    fieldOnChange,
    showInlineReset,
  }: {
    fieldState: ListingFilterState;
    fieldOnChange: (next: ListingFilterState) => void;
    showInlineReset: boolean;
  }) {
    const setAttr = (code: string, value: string) => {
      const attrs = { ...fieldState.attrs };
      if (value) attrs[code] = [value];
      else delete attrs[code];
      fieldOnChange({ ...fieldState, attrs });
    };

    return (
      <>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {hasSubcategorySlot && subcategory && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                {subcategory.label}
              </label>
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

          {fieldsBeforePrice.map((f) => renderField(f, fieldState, setAttr))}

          <div>
            <label className="text-xs font-medium text-muted-foreground">{priceLabel}</label>
            <div className="mt-1.5 flex items-center gap-2">
              <input
                value={fieldState.priceMin}
                onChange={(e) => fieldOnChange({ ...fieldState, priceMin: e.target.value })}
                placeholder="dan"
                inputMode="numeric"
                className="w-full rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
              <span className="text-muted-foreground">—</span>
              <input
                value={fieldState.priceMax}
                onChange={(e) => fieldOnChange({ ...fieldState, priceMax: e.target.value })}
                placeholder="gacha"
                inputMode="numeric"
                className="w-full rounded-xl border border-input bg-background px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
              />
            </div>
          </div>

          {primaryFieldsAfterPrice.map((f) => renderField(f, fieldState, setAttr))}
        </div>

        {accordionFields.length > 0 && (
          <Accordion type="single" collapsible className="mt-3">
            <AccordionItem value="more" className="border-border/60">
              <AccordionTrigger className="text-sm font-medium text-foreground">
                Boshqa filtrlar
              </AccordionTrigger>
              <AccordionContent>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {accordionFields.map((f) => renderField(f, fieldState, setAttr))}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        )}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          {showSellerKindTabs ? (
            <div className="flex flex-wrap items-center gap-1.5">
              {SELLER_KIND_TABS.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  onClick={() => fieldOnChange({ ...fieldState, sellerKind: tab.value })}
                  className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                    fieldState.sellerKind === tab.value
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

          {showInlineReset && (
            <button
              type="button"
              onClick={() => fieldOnChange(emptyFilterState())}
              className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
            >
              Filtrlarni o'chirish
            </button>
          )}
        </div>
      </>
    );
  }

  const activeCount = activeFilterCount(state);

  return (
    <>
      {/* Desktop / tablet: full inline panel. */}
      <div className="hidden rounded-3xl border border-border bg-card p-5 shadow-soft sm:p-6 md:block">
        <div className="flex items-center gap-2 text-base font-semibold text-foreground">
          <SlidersHorizontal className="size-4 text-primary" />
          Filtrlar
        </div>
        <div className="mt-5">
          {renderPanelBody({ fieldState: state, fieldOnChange: onChange, showInlineReset: true })}
        </div>
      </div>

      {/* Mobile: one compact trigger, sticky just under the fixed navbar, opening the same
       * fields in a bottom sheet. `top-[68px]` clears the floating pill navbar's real height
       * (confirmed live) without the sticky bar itself ever sitting under it. */}
      <div className="sticky top-[68px] z-30 -mx-4 border-b border-border/60 bg-background/95 px-4 py-2.5 backdrop-blur md:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground shadow-soft"
        >
          <SlidersHorizontal className="size-4 text-primary" />
          Filtrlar
          {activeCount > 0 && (
            <span className="inline-flex size-5 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">
              {activeCount}
            </span>
          )}
        </button>
      </div>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="bottom"
          className="z-50 flex max-h-[85vh] flex-col overflow-y-auto rounded-t-3xl px-5 pb-5 pt-5"
        >
          <SheetHeader className="mb-2 text-left">
            <SheetTitle>Filtrlar</SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto pb-2">
            {renderPanelBody({
              fieldState: mobileDraft,
              fieldOnChange: setMobileDraft,
              showInlineReset: false,
            })}
          </div>
          <div className="sticky bottom-0 mt-4 flex gap-3 border-t border-border bg-background pt-4">
            <button
              type="button"
              onClick={() => {
                setMobileDraft(emptyFilterState());
                onChange(emptyFilterState());
              }}
              className="flex-1 rounded-xl border border-border px-4 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
            >
              Filtrlarni tozalash
            </button>
            <button
              type="button"
              onClick={() => {
                onChange(mobileDraft);
                setMobileOpen(false);
              }}
              className="flex-1 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
            >
              Natijalarni ko'rsatish
            </button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
