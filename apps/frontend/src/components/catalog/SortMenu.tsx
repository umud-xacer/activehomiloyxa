/**
 * Collapses a category page's sort options (and, for the PROPERTY direction, the
 * "Chegirmadagilar" discount toggle) behind a single hamburger-triggered dropdown instead of a
 * row of separate pill buttons -- same real DropdownMenu primitives `Navbar.tsx`'s account menu
 * already uses in production, so no new interaction pattern is introduced.
 */
import { Check, Menu } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface HubOption<T extends string> {
  value: T;
  label: string;
  icon: LucideIcon;
}

export function SortMenu<T extends string>({
  options,
  value,
  onChange,
  extra,
}: {
  options: HubOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** An additional standalone toggle rendered above the sort options (e.g. "Chegirmadagilar" on
   * the PROPERTY direction) -- kept in the same menu instead of its own separate button. */
  extra?: { label: string; icon: LucideIcon; active: boolean; onToggle: () => void };
}) {
  const activeOption = options.find((o) => o.value === value);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={`inline-flex shrink-0 items-center gap-2 rounded-2xl border px-4 py-2.5 text-sm font-medium shadow-soft transition ${
            extra?.active
              ? "border-warning bg-warning/10 text-warning"
              : "border-border bg-card text-foreground/80 hover:border-primary/40 hover:text-foreground"
          }`}
        >
          <Menu className="size-4" />
          {activeOption?.label ?? "Saralash"}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {extra && (
          <>
            <DropdownMenuItem onClick={extra.onToggle}>
              <extra.icon className="mr-2 size-4" />
              {extra.label}
              {extra.active && <Check className="ml-auto size-4 text-primary" />}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuLabel>Saralash</DropdownMenuLabel>
        {options.map((opt) => (
          <DropdownMenuItem key={opt.value} onClick={() => onChange(opt.value)}>
            <opt.icon className="mr-2 size-4" />
            {opt.label}
            {opt.value === value && <Check className="ml-auto size-4 text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
