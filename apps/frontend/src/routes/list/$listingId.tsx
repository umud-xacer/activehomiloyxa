import { useMemo, useState, type FormEvent } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, ImagePlus, X } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorState } from "@/components/state/ErrorState";
import { catalogClient, uploadMediaFile } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { DynamicCategoryForm } from "@/features/listings/DynamicCategoryForm";
import { ApiError } from "@/lib/http";
import type { Currency } from "@/features/properties/types";

export const Route = createFileRoute("/list/$listingId")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "E'lonni tahrirlash — ActiveHome" }] }),
  component: Page,
});

const CURRENCIES: Currency[] = ["UZS", "USD", "EUR", "RUB"];

function Page() {
  const { listingId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    data: listing,
    isLoading: listingLoading,
    error: listingError,
  } = useQuery({
    queryKey: ["catalog", "listing", listingId],
    queryFn: () => catalogClient.getListing(listingId),
  });

  const { data: categories = [] } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });
  const category = useMemo(
    () => categories.find((c) => c.id === listing?.categoryId),
    [categories, listing?.categoryId],
  );

  const { data: form, isLoading: formLoading } = useQuery({
    queryKey: ["catalog", "category-form", listing?.categoryId],
    queryFn: () => catalogClient.getCategoryForm(listing!.categoryId),
    enabled: !!listing,
  });

  const [title, setTitle] = useState<string | null>(null);
  const [description, setDescription] = useState<string | null>(null);
  const [priceAmount, setPriceAmount] = useState<string | null>(null);
  const [currency, setCurrency] = useState<Currency | null>(null);
  const [attributes, setAttributes] = useState<Record<string, unknown> | null>(null);
  const [existingImageIds, setExistingImageIds] = useState<string[] | null>(null);
  const [newFiles, setNewFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (listing && title === null) {
    setTitle(listing.title);
    setDescription(listing.description ?? "");
    setPriceAmount(listing.price?.amount ?? "");
    setCurrency((listing.price?.currency as Currency) ?? "UZS");
    setAttributes(listing.attributes ?? {});
    setExistingImageIds((listing.images ?? []).map((img) => img.mediaAssetId));
  }

  const onFilesChange = (list: FileList | null) => {
    if (!list) return;
    setNewFiles((prev) => [...prev, ...Array.from(list)].slice(0, 8));
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!listing) return;
    setError(null);
    setSubmitting(true);
    try {
      const updated = await catalogClient.updateListing(listing.id, {
        lockVersion: listing.lockVersion,
        title: title ?? undefined,
        description: description || undefined,
        attributes: attributes ?? undefined,
        price: priceAmount ? { amount: priceAmount, currency: currency ?? "UZS" } : undefined,
      });

      for (const file of newFiles) {
        const ticket = await catalogClient.initMediaUpload(file);
        await uploadMediaFile(ticket, file);
        await catalogClient.attachListingImage(listing.id, ticket.mediaAssetId);
      }

      await queryClient.invalidateQueries({ queryKey: ["catalog", "my-listings"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog", "listing", listingId] });
      navigate({ to: "/properties/$slug", params: { slug: updated.id } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "E'lonni saqlashda xatolik yuz berdi.");
      setSubmitting(false);
    }
  };

  if (listingError) {
    return <ErrorState error={listingError} reset={() => window.location.reload()} />;
  }

  if (listingLoading || !listing || title === null) {
    return (
      <AppShell>
        <PageHeader eyebrow="E'lonni tahrirlash" title="Yuklanmoqda..." />
        <div className="mx-auto max-w-4xl px-6 py-16 text-sm text-muted-foreground">
          <Loader2 className="mr-2 inline size-4 animate-spin" /> Yuklanmoqda…
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="E'lonni tahrirlash"
        title={category ? categoryLabel(category.name, "uz") : listing.title}
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "Tahrirlash" }]}
      />

      <div className="mx-auto max-w-4xl px-6 py-10">
        <form onSubmit={onSubmit} className="space-y-8">
          <div>
            <h3 className="font-display text-sm font-semibold text-foreground">Asosiy ma'lumot</h3>
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Sarlavha <span className="text-destructive">*</span>
                </label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  maxLength={200}
                  className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Tavsif
                </label>
                <textarea
                  value={description ?? ""}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Narxi
                </label>
                <input
                  type="number"
                  value={priceAmount ?? ""}
                  onChange={(e) => setPriceAmount(e.target.value)}
                  min={0}
                  className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Valyuta
                </label>
                <select
                  value={currency ?? "UZS"}
                  onChange={(e) => setCurrency(e.target.value as Currency)}
                  className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div>
            <h3 className="font-display text-sm font-semibold text-foreground">Rasmlar</h3>
            <div className="mt-3 flex flex-wrap gap-3">
              {(listing.images ?? [])
                .filter((img) => (existingImageIds ?? []).includes(img.mediaAssetId))
                .map((img) => (
                  <div
                    key={img.id}
                    className="relative size-20 overflow-hidden rounded-xl border border-border bg-muted"
                  />
                ))}
              {newFiles.map((file, i) => (
                <div
                  key={i}
                  className="relative size-20 overflow-hidden rounded-xl border border-border"
                >
                  <img src={URL.createObjectURL(file)} alt="" className="size-full object-cover" />
                  <button
                    type="button"
                    onClick={() => setNewFiles((prev) => prev.filter((_, idx) => idx !== i))}
                    className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white"
                  >
                    <X className="size-3" />
                  </button>
                </div>
              ))}
              {(existingImageIds?.length ?? 0) + newFiles.length < 8 && (
                <label className="flex size-20 cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
                  <ImagePlus className="size-5" />
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    className="hidden"
                    onChange={(e) => onFilesChange(e.target.files)}
                  />
                </label>
              )}
            </div>
          </div>

          {formLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Kategoriya maydonlari yuklanmoqda…
            </div>
          ) : form && form.sections.length > 0 ? (
            <DynamicCategoryForm
              sections={form.sections}
              values={attributes ?? {}}
              onChange={(code, value) =>
                setAttributes((prev) => ({ ...(prev ?? {}), [code]: value }))
              }
            />
          ) : null}

          {error && <p className="text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={submitting || !title?.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50"
          >
            {submitting && <Loader2 className="size-4 animate-spin" />}
            O'zgarishlarni saqlash
          </button>
        </form>
      </div>
    </AppShell>
  );
}
