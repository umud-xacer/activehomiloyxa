import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Loader2,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  ImagePlus,
  X,
  LayoutGrid,
  Type,
  Coins,
  Images,
  SlidersHorizontal,
  Rocket,
  Eye,
  Building2,
  ShieldCheck,
  Lightbulb,
  MapPin,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { listingApi, type FormField } from "@/lib/listing-api";
import { categoriesOptions } from "@/features/properties/queries";
import { mediaApi } from "@/lib/media-api";
import { ApiError } from "@/lib/http";
import { LocationPicker, type LatLng } from "@/components/map/LocationPicker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Currency } from "@/features/properties/types";

const DEFAULT_LOCATION: LatLng = { lat: 41.2995, lng: 69.2401 }; // Tashkent -- initial pin, user repositions it

const CURRENCIES: { value: Currency; label: string }[] = [
  { value: "UZS", label: "UZS — so'm" },
  { value: "USD", label: "USD — dollar" },
  { value: "EUR", label: "EUR — evro" },
];

interface PendingImage {
  file: File;
  previewUrl: string;
  mediaAssetId: string | null;
  status: "uploading" | "done" | "error";
}

export const Route = createFileRoute("/list")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "E'lon joylash — ActiveHome" },
      { name: "description", content: "E'loningizni bir necha daqiqada butun dunyoga joylang." },
    ],
  }),
  component: Page,
});

const categoryFormOptions = (categoryId: string | null) => ({
  queryKey: ["categoryForm", categoryId],
  queryFn: () => listingApi.getCategoryForm(categoryId as string),
  enabled: !!categoryId,
});

const INPUT =
  "w-full rounded-xl border border-border bg-background/50 px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 transition focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20";

function Section({
  step,
  icon: Icon,
  title,
  description,
  children,
}: {
  step: number;
  icon: typeof LayoutGrid;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-card/60 p-5 shadow-soft backdrop-blur-sm sm:p-6">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon className="size-4.5" />
        </div>
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <span className="text-xs font-medium text-muted-foreground">{step}-qadam</span>
            <span className="text-muted-foreground/40">·</span>
            {title}
          </h2>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-foreground/80">
        {label} {required && <span className="text-destructive">*</span>}
      </span>
      {children}
    </label>
  );
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = field.label.uz_latn ?? field.code;

  if (field.fieldType === "boolean") {
    return (
      <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-border bg-background/40 px-3.5 py-2.5 text-sm text-foreground transition hover:border-primary/40">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="size-4 rounded border-border accent-primary"
        />
        {label}
      </label>
    );
  }

  if (field.fieldType === "select" && field.options) {
    return (
      <Field label={label} required={field.required}>
        <select
          required={field.required}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className={INPUT}
        >
          <option value="" disabled>
            Tanlang...
          </option>
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label.uz_latn ?? o.value}
            </option>
          ))}
        </select>
      </Field>
    );
  }

  return (
    <Field label={label} required={field.required}>
      <input
        type={field.fieldType === "number" ? "number" : "text"}
        required={field.required}
        value={(value as string | number) ?? ""}
        onChange={(e) => onChange(field.fieldType === "number" ? Number(e.target.value) : e.target.value)}
        className={INPUT}
      />
    </Field>
  );
}

function Page() {
  const navigate = useNavigate();
  const { data: categories } = useQuery(categoriesOptions());
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const { data: form } = useQuery(categoryFormOptions(categoryId));

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priceAmount, setPriceAmount] = useState("");
  const [currency, setCurrency] = useState<Currency>("UZS");
  const [attributes, setAttributes] = useState<Record<string, unknown>>({});
  const [location, setLocation] = useState<LatLng>(DEFAULT_LOCATION);
  const [publishNow, setPublishNow] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [images, setImages] = useState<PendingImage[]>([]);

  const onPickImages = (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) {
      const previewUrl = URL.createObjectURL(file);
      const entry: PendingImage = { file, previewUrl, mediaAssetId: null, status: "uploading" };
      setImages((prev) => [...prev, entry]);
      mediaApi
        .uploadImage(file)
        .then((asset) => {
          setImages((prev) =>
            prev.map((img) =>
              img.previewUrl === previewUrl ? { ...img, mediaAssetId: asset.id, status: "done" } : img,
            ),
          );
        })
        .catch(() => {
          setImages((prev) =>
            prev.map((img) => (img.previewUrl === previewUrl ? { ...img, status: "error" } : img)),
          );
        });
    }
  };

  const removeImage = (previewUrl: string) => {
    setImages((prev) => prev.filter((img) => img.previewUrl !== previewUrl));
  };

  const allFields = form?.sections.flatMap((s) => s.fields) ?? [];
  const selectedCategory = categories?.find((c) => c.id === categoryId);
  const listingType =
    selectedCategory && ["apartments", "houses", "cottages", "commercial", "land", "hotels"].includes(
      selectedCategory.path,
    )
      ? "ADVERTISEMENT"
      : "PRODUCT";

  const coverImage = images.find((i) => i.status !== "error")?.previewUrl ?? null;
  const priceLabel = priceAmount ? `${Number(priceAmount).toLocaleString("ru-RU")} ${currency}` : null;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!categoryId) return;
    setError(null);
    setLoading(true);
    try {
      const imageMediaAssetIds = images
        .filter((img) => img.status === "done" && img.mediaAssetId)
        .map((img) => img.mediaAssetId as string);
      const listing = await listingApi.createListing({
        listingType,
        categoryId,
        title,
        description: description || undefined,
        attributes,
        price: priceAmount ? { amount: priceAmount, currency } : undefined,
        location: { latitude: location.lat, longitude: location.lng },
        imageMediaAssetIds: imageMediaAssetIds.length > 0 ? imageMediaAssetIds : undefined,
        publish: publishNow,
      });
      setDone(true);
      setTimeout(() => navigate({ to: "/properties/$slug", params: { slug: listing.slug } }), 1000);
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "E'lon yaratib bo'lmadi");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <PageHeader
        eyebrow="Egalar va agentlar uchun"
        title="E'lon joylash"
        description="E'loningizni bir necha daqiqada minglab xaridorlarga yeting."
      />

      <div className="mx-auto max-w-6xl px-6 py-10">
        {done ? (
          <div className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-3xl border border-success/30 bg-success/10 p-8 text-center text-success">
            <CheckCircle2 className="size-10" />
            <div className="font-display text-lg font-semibold">E'lon yaratildi!</div>
            <p className="text-sm text-success/80">E'lon sahifasiga yo'naltirilmoqda...</p>
          </div>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
            {/* Form */}
            <form onSubmit={onSubmit} className="space-y-5">
              <Section step={1} icon={LayoutGrid} title="Kategoriya" description="E'loningiz qaysi bo'limga tegishli?">
                <Select
                  value={categoryId ?? ""}
                  onValueChange={(v) => {
                    setCategoryId(v || null);
                    setAttributes({});
                  }}
                >
                  <SelectTrigger className="w-full rounded-xl border-border bg-background/50 py-2.5 text-sm">
                    <SelectValue placeholder="Tanlang..." />
                  </SelectTrigger>
                  <SelectContent>
                    {categories?.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name.uz_latn ?? c.path}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Section>

              <Section step={2} icon={Type} title="Asosiy ma'lumot" description="Sarlavha va tavsif — xaridor birinchi ko'radigan narsa.">
                <div className="space-y-4">
                  <Field label="Sarlavha" required>
                    <input
                      required
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Masalan: Zamonaviy 3-xonali kvartira"
                      className={INPUT}
                    />
                  </Field>
                  <Field label="Tavsif">
                    <textarea
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={4}
                      placeholder="Joylashuv, holati, afzalliklari haqida yozing..."
                      className={INPUT}
                    />
                  </Field>
                </div>
              </Section>

              <Section step={3} icon={Coins} title="Narx" description="Narxni kiriting va valyutasini tanlang (ixtiyoriy).">
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={priceAmount}
                    onChange={(e) => setPriceAmount(e.target.value)}
                    placeholder="100 000"
                    className={`${INPUT} flex-1`}
                  />
                  <Select value={currency} onValueChange={(v) => setCurrency(v as Currency)}>
                    <SelectTrigger className="w-28 shrink-0 rounded-xl border-border bg-background/50 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CURRENCIES.map((c) => (
                        <SelectItem key={c.value} value={c.value}>
                          {c.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </Section>

              <Section step={4} icon={Images} title="Rasmlar" description="Sifatli rasmlar e'lonni 3 barobar ko'proq ko'rsatadi.">
                <div className="grid grid-cols-3 gap-2.5 sm:grid-cols-4">
                  {images.map((img) => (
                    <div key={img.previewUrl} className="group relative aspect-square overflow-hidden rounded-xl border border-border">
                      <img src={img.previewUrl} alt="" className="size-full object-cover" />
                      {img.status === "uploading" && (
                        <div className="absolute inset-0 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                          <Loader2 className="size-5 animate-spin text-white" />
                        </div>
                      )}
                      {img.status === "error" && (
                        <div className="absolute inset-0 flex items-center justify-center bg-destructive/70 text-[10px] font-semibold text-white">
                          Xatolik
                        </div>
                      )}
                      {img.status === "done" && (
                        <div className="absolute bottom-1 left-1 rounded-full bg-success/90 p-0.5 text-white">
                          <CheckCircle2 className="size-3" />
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => removeImage(img.previewUrl)}
                        className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100"
                      >
                        <X className="size-3" />
                      </button>
                    </div>
                  ))}
                  <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border bg-background/40 text-muted-foreground transition hover:border-primary/50 hover:bg-primary/5 hover:text-primary">
                    <ImagePlus className="size-5" />
                    <span className="text-[10px] font-medium">Qo'shish</span>
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      multiple
                      className="hidden"
                      onChange={(e) => onPickImages(e.target.files)}
                    />
                  </label>
                </div>
              </Section>

              <Section step={5} icon={MapPin} title="Joylashuv" description="Xaritada bosing yoki manzilni qidiring — e'lon shu nuqtada ko'rsatiladi.">
                <LocationPicker value={location} onChange={setLocation} />
              </Section>

              {allFields.length > 0 && (
                <Section step={6} icon={SlidersHorizontal} title="Xususiyatlar" description="Kategoriyaga oid qo'shimcha maydonlar.">
                  <div className="grid gap-4 sm:grid-cols-2">
                    {allFields
                      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
                      .map((field) => (
                        <FieldInput
                          key={field.code}
                          field={field}
                          value={attributes[field.code]}
                          onChange={(v) => setAttributes((prev) => ({ ...prev, [field.code]: v }))}
                        />
                      ))}
                  </div>
                </Section>
              )}

              <Section step={allFields.length > 0 ? 7 : 6} icon={Rocket} title="Nashr qilish" description="Tayyor bo'lsangiz, e'lonni joylang.">
                <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-border bg-background/40 px-4 py-3 transition hover:border-primary/40">
                  <input
                    type="checkbox"
                    checked={publishNow}
                    onChange={(e) => setPublishNow(e.target.checked)}
                    className="size-4 rounded border-border accent-primary"
                  />
                  <span className="text-sm text-foreground">
                    Darhol nashr qilish
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      Belgilamasangiz, qoralama sifatida saqlanadi.
                    </span>
                  </span>
                </label>

                {error && (
                  <div className="mt-4 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
                    <AlertCircle className="size-4 shrink-0" /> {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading || !categoryId}
                  className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
                  {loading ? "Yaratilmoqda..." : "E'lon joylash"}
                </button>
              </Section>
            </form>

            {/* Sidebar: live preview + tips */}
            <aside className="space-y-5 lg:sticky lg:top-24 lg:self-start">
              <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
                <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5 text-xs font-semibold text-muted-foreground">
                  <Eye className="size-3.5" /> Jonli ko'rinish
                </div>
                <div className="relative aspect-[4/3] bg-muted">
                  {coverImage ? (
                    <img src={coverImage} alt="" className="size-full object-cover" />
                  ) : (
                    <div className="flex size-full flex-col items-center justify-center gap-2 text-muted-foreground/50">
                      <Building2 className="size-8" />
                      <span className="text-xs">Rasm qo'shilmagan</span>
                    </div>
                  )}
                  {publishNow && (
                    <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-foreground backdrop-blur">
                      <ShieldCheck className="size-3 text-success" /> Nashr
                    </span>
                  )}
                </div>
                <div className="p-4">
                  {selectedCategory && (
                    <span className="text-[11px] font-medium uppercase tracking-wider text-primary">
                      {selectedCategory.name.uz_latn ?? selectedCategory.path}
                    </span>
                  )}
                  <h3 className="mt-1 line-clamp-2 text-sm font-semibold text-foreground">
                    {title || "E'lon sarlavhasi"}
                  </h3>
                  <div className="mt-2 font-display text-lg font-semibold text-foreground">
                    {priceLabel ?? "Narx ko'rsatilmagan"}
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-border bg-card/50 p-4">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <Lightbulb className="size-3.5 text-primary" /> Yaxshi e'lon uchun maslahatlar
                </div>
                <ul className="mt-3 space-y-2 text-xs text-muted-foreground">
                  {[
                    "Aniq va qisqa sarlavha yozing",
                    "Kamida 3-4 ta sifatli rasm qo'shing",
                    "Narxni realistik belgilang",
                    "Tavsifda afzalliklarni ta'kidlang",
                  ].map((tip) => (
                    <li key={tip} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-success/70" />
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            </aside>
          </div>
        )}
      </div>
    </AppShell>
  );
}
