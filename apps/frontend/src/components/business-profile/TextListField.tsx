import { Plus, X } from "lucide-react";

/** Shared by the business-profile edit form (`dashboard/business-profile.tsx`) and the
 * onboarding wizard (`routes/organization/setup.tsx`) -- extracted rather than duplicated
 * (ADR-0010). */
export function TextListField({
  icon: Icon,
  label,
  placeholder,
  values,
  onChange,
}: {
  icon: typeof Plus;
  label: string;
  placeholder: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Icon className="size-3.5" /> {label}
        </label>
        <button
          type="button"
          onClick={() => onChange([...values, ""])}
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
        >
          <Plus className="size-3.5" /> Qo'shish
        </button>
      </div>
      <div className="mt-1.5 space-y-2">
        {values.length === 0 && (
          <p className="text-xs text-muted-foreground/70">Hali qo'shilmagan.</p>
        )}
        {values.map((value, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={value}
              onChange={(e) => onChange(values.map((v, idx) => (idx === i ? e.target.value : v)))}
              placeholder={placeholder}
              className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={() => onChange(values.filter((_, idx) => idx !== i))}
              className="rounded-lg p-2 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
