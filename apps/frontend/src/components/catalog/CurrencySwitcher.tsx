/** so'm / y.e. display-currency toggle. Placed next to `SortMenu` on catalog/search pages
 * (`categories/$.tsx`'s two direction views, `properties/index.tsx`). Purely a display/filter
 * preference -- see `lib/currency.ts` for the conversion logic this drives. */
import { cn } from "@/lib/utils";
import { useDisplayCurrency, type DisplayCurrency } from "@/lib/currency";

const OPTIONS: { value: DisplayCurrency; label: string }[] = [
  { value: "UZS", label: "so'm" },
  { value: "USD", label: "y.e." },
];

export function CurrencySwitcher({ className }: { className?: string }) {
  const [currency, setCurrency] = useDisplayCurrency();

  return (
    <div
      role="group"
      aria-label="Valyuta"
      className={cn(
        "inline-flex shrink-0 items-center rounded-full border border-input bg-muted/40 p-0.5",
        className,
      )}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => setCurrency(option.value)}
          aria-pressed={currency === option.value}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            currency === option.value
              ? "bg-background text-foreground shadow-soft"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
