import { useState } from "react";
import { Loader2, Paperclip, X } from "lucide-react";
import type { FormField, FormSection } from "@/lib/catalog-client";
import { uploadMedia } from "@/lib/media-client";

/** Renders a category's published `FormDefinition` (Configuration module) as controlled inputs.
 * Purely presentational -- the caller owns `values` and gets notified via `onChange`; the
 * resulting record is passed straight through as `Listing.attributes` on create/update. */

function fieldLabel(field: FormField | FormSection): string {
  return (
    field.label.uz_latn || field.label.en || field.label.ru || Object.values(field.label)[0] || ""
  );
}

interface FieldProps {
  field: FormField;
  value: unknown;
  onChange: (value: unknown) => void;
}

function TextField({ field, value, onChange }: FieldProps) {
  return (
    <input
      type="text"
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value)}
      required={field.required}
      className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
    />
  );
}

function NumberField({ field, value, onChange }: FieldProps) {
  return (
    <input
      type="number"
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      required={field.required}
      className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
    />
  );
}

function DateField({ field, value, onChange }: FieldProps) {
  return (
    <input
      type="date"
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value)}
      required={field.required}
      className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
    />
  );
}

function BooleanField({ value, onChange }: FieldProps) {
  return (
    <div className="flex gap-2">
      {[
        { key: "true", label: "Ha" },
        { key: "false", label: "Yo'q" },
      ].map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key === "true")}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            String(value) === opt.key
              ? "bg-primary text-primary-foreground shadow-soft"
              : "border border-border bg-background text-foreground/70 hover:text-foreground"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function SelectField({ field, value, onChange }: FieldProps) {
  return (
    <select
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value || undefined)}
      required={field.required}
      className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
    >
      <option value="">Tanlang…</option>
      {field.options?.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label.uz_latn || opt.label.en || Object.values(opt.label)[0] || opt.value}
        </option>
      ))}
    </select>
  );
}

function MultiSelectField({ field, value, onChange }: FieldProps) {
  const selected = Array.isArray(value) ? (value as string[]) : [];
  const toggle = (optValue: string) => {
    onChange(
      selected.includes(optValue)
        ? selected.filter((v) => v !== optValue)
        : [...selected, optValue],
    );
  };
  return (
    <div className="flex flex-wrap gap-2">
      {field.options?.map((opt) => {
        const active = selected.includes(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => toggle(opt.value)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              active
                ? "bg-primary text-primary-foreground shadow-soft"
                : "border border-border bg-background text-foreground/70 hover:text-foreground"
            }`}
          >
            {opt.label.uz_latn || opt.label.en || Object.values(opt.label)[0] || opt.value}
          </button>
        );
      })}
    </div>
  );
}

function RangeField({ field, value, onChange }: FieldProps) {
  const range = (value as { min?: number; max?: number }) ?? {};
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        placeholder="Dan"
        value={range.min ?? ""}
        onChange={(e) =>
          onChange({ ...range, min: e.target.value === "" ? undefined : Number(e.target.value) })
        }
        required={field.required}
        className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
      />
      <span className="text-muted-foreground">—</span>
      <input
        type="number"
        placeholder="Gacha"
        value={range.max ?? ""}
        onChange={(e) =>
          onChange({ ...range, max: e.target.value === "" ? undefined : Number(e.target.value) })
        }
        className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
      />
    </div>
  );
}

function LocationField({ value, onChange }: FieldProps) {
  const loc = (value as { lat?: number; lng?: number }) ?? {};
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        placeholder="Kenglik (lat)"
        value={loc.lat ?? ""}
        onChange={(e) =>
          onChange({ ...loc, lat: e.target.value === "" ? undefined : Number(e.target.value) })
        }
        className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
      />
      <input
        type="number"
        placeholder="Uzunlik (lng)"
        value={loc.lng ?? ""}
        onChange={(e) =>
          onChange({ ...loc, lng: e.target.value === "" ? undefined : Number(e.target.value) })
        }
        className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
      />
    </div>
  );
}

function FileField({ field, value, onChange }: FieldProps) {
  const mediaAssetId = (value as string) ?? "";
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadMedia(file, "LISTING");
      onChange(uploaded.mediaAssetId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  if (mediaAssetId) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm">
        <Paperclip className="size-4 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate text-foreground/80">Fayl biriktirildi</span>
        <button
          type="button"
          onClick={() => onChange(undefined)}
          className="shrink-0 rounded-full p-1 text-muted-foreground transition hover:bg-muted"
        >
          <X className="size-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div>
      <label className="inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-background px-3.5 py-2.5 text-sm text-muted-foreground transition hover:bg-muted">
        {uploading ? <Loader2 className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
        {uploading ? "Yuklanmoqda…" : "Fayl tanlash"}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          disabled={uploading}
          required={field.required}
          onChange={(e) => handleChange(e.target.files?.[0])}
        />
      </label>
      {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
    </div>
  );
}

function FieldInput(props: FieldProps) {
  switch (props.field.fieldType) {
    case "number":
      return <NumberField {...props} />;
    case "date":
      return <DateField {...props} />;
    case "boolean":
      return <BooleanField {...props} />;
    case "select":
      return <SelectField {...props} />;
    case "multiselect":
      return <MultiSelectField {...props} />;
    case "range":
      return <RangeField {...props} />;
    case "location":
      return <LocationField {...props} />;
    case "file":
      return <FileField {...props} />;
    case "text":
    default:
      return <TextField {...props} />;
  }
}

interface Props {
  sections: FormSection[];
  values: Record<string, unknown>;
  onChange: (code: string, value: unknown) => void;
}

export function DynamicCategoryForm({ sections, values, onChange }: Props) {
  const sorted = [...sections].sort((a, b) => a.order - b.order);
  return (
    <div className="space-y-8">
      {sorted.map((section) => {
        const fields = [...section.fields].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        if (fields.length === 0) return null;
        return (
          <div key={section.code}>
            <h3 className="font-display text-sm font-semibold text-foreground">
              {fieldLabel(section)}
            </h3>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {fields.map((field) => (
                <div
                  key={field.code}
                  className={field.fieldType === "multiselect" ? "sm:col-span-2" : ""}
                >
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                    {fieldLabel(field)}
                    {field.required && <span className="text-destructive"> *</span>}
                  </label>
                  <FieldInput
                    field={field}
                    value={values[field.code]}
                    onChange={(value) => onChange(field.code, value)}
                  />
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
