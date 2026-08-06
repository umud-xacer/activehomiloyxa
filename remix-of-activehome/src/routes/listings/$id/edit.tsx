import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Loader2, ArrowRight, AlertCircle, CheckCircle2, ImagePlus, X, Archive, Trash2, RotateCcw, PauseCircle, RefreshCw } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { listingApi, type FormField } from "@/lib/listing-api";
import { mediaApi, mediaAssetUrl } from "@/lib/media-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/listings/$id/edit")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "E'lonni tahrirlash — ActiveHome" }] }),
  component: Page,
});

const LIFECYCLE_LABEL: Record<string, string> = {
  DRAFT: "Qoralama",
  PENDING_VERIFICATION: "Tekshiruvda",
  PUBLISHED: "Nashr qilingan",
  EDITED: "Tahrirlangan",
  SUSPENDED: "To'xtatilgan",
  ARCHIVED: "Arxivlangan",
  DELETED: "O'chirilgan",
};

function FieldInput({ field, value, onChange }: { field: FormField; value: unknown; onChange: (v: unknown) => void }) {
  const label = field.label.uz_latn ?? field.code;
  if (field.fieldType === "boolean") {
    return (
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} className="size-4 rounded border-border" />
        {label}
      </label>
    );
  }
  if (field.fieldType === "select" && field.options) {
    return (
      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">{label}</span>
        <select
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground"
        >
          <option value="" disabled>Tanlang...</option>
          {field.options.map((o) => (
            <option key={o.value} value={o.value}>{o.label.uz_latn ?? o.value}</option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="block">
      <span className="text-xs font-semibold text-foreground/80">{label}</span>
      <input
        type={field.fieldType === "number" ? "number" : "text"}
        value={(value as string | number) ?? ""}
        onChange={(e) => onChange(field.fieldType === "number" ? Number(e.target.value) : e.target.value)}
        className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground"
      />
    </label>
  );
}

function Page() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: listing, isLoading } = useQuery({
    queryKey: ["listings", "mine", "detail", id],
    queryFn: () => listingApi.getListing(id),
  });
  const { data: form } = useQuery({
    queryKey: ["categoryForm", listing?.categoryId],
    queryFn: () => listingApi.getCategoryForm(listing!.categoryId),
    enabled: !!listing,
  });

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priceAmount, setPriceAmount] = useState("");
  const [attributes, setAttributes] = useState<Record<string, unknown>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!listing) return;
    setTitle(listing.title);
    setDescription(listing.description ?? "");
    setPriceAmount(listing.price?.amount ?? "");
    setAttributes(listing.attributes ?? {});
  }, [listing]);

  const allFields = form?.sections.flatMap((s) => s.fields) ?? [];

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["listings", "mine", "detail", id] });

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!listing) return;
    setError(null);
    setSaving(true);
    try {
      await listingApi.updateListing(id, {
        lockVersion: listing.lockVersion ?? 0,
        title,
        description: description || undefined,
        attributes,
        price: priceAmount ? { amount: priceAmount, currency: listing.price?.currency ?? "UZS" } : undefined,
        location: listing.location ?? undefined,
      });
      setDone(true);
      refresh();
      setTimeout(() => setDone(false), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Saqlab bo'lmadi");
    } finally {
      setSaving(false);
    }
  };

  const runAction = async (action: "SUSPEND" | "ARCHIVE" | "RENEW" | "RESTORE" | "DELETE") => {
    setActionError(null);
    setActionPending(true);
    try {
      await listingApi.changeStatus(id, action);
      refresh();
      if (action === "DELETE") navigate({ to: "/dashboard/seller" });
    } catch (err) {
      setActionError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Amalni bajarib bo'lmadi");
    } finally {
      setActionPending(false);
    }
  };

  const onPickImage = async (files: FileList | null) => {
    if (!files || !files[0] || !listing) return;
    setUploading(true);
    try {
      const asset = await mediaApi.uploadImage(files[0]);
      await listingApi.attachImage(id, asset.id);
      refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Rasm yuklashda xatolik");
    } finally {
      setUploading(false);
    }
  };

  const removeImage = async (imageId: string) => {
    await listingApi.detachImage(id, imageId);
    refresh();
  };

  if (isLoading || !listing) {
    return (
      <AppShell>
        <PageHeader eyebrow="Seller" title="E'lonni tahrirlash" />
        <div className="mx-auto max-w-2xl px-6 py-12">
          <div className="h-64 animate-pulse rounded-2xl bg-muted" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Seller"
        title="E'lonni tahrirlash"
        description={`Holat: ${LIFECYCLE_LABEL[listing.lifecycleState] ?? listing.lifecycleState}`}
      />
      <div className="mx-auto max-w-2xl space-y-6 px-6 py-12">
        <div className="rounded-2xl border border-border bg-card/50 p-4">
          <span className="text-xs font-semibold text-foreground/80">Rasmlar</span>
          <div className="mt-1.5 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {(listing.images ?? []).map((img) => (
              <div key={img.id} className="group relative aspect-square overflow-hidden rounded-xl border border-border">
                <img src={mediaAssetUrl(img.mediaAssetId, "thumbnail")} alt="" className="size-full object-cover" />
                <button
                  type="button"
                  onClick={() => removeImage(img.id)}
                  className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
            <label className="flex aspect-square cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-border bg-card/50 text-muted-foreground hover:bg-muted">
              {uploading ? <Loader2 className="size-5 animate-spin" /> : <ImagePlus className="size-5" />}
              <span className="text-[10px]">Qo'shish</span>
              <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => onPickImage(e.target.files)} disabled={uploading} />
            </label>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-5">
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Sarlavha</span>
            <input required value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Tavsif</span>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Narx</span>
            <input type="number" value={priceAmount} onChange={(e) => setPriceAmount(e.target.value)} className="mt-1.5 w-full rounded-xl border border-border bg-card px-3 py-2.5 text-sm text-foreground" />
          </label>

          {allFields.length > 0 && (
            <div className="space-y-4 rounded-2xl border border-border bg-card/50 p-4">
              {allFields
                .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
                .map((field) => (
                  <FieldInput key={field.code} field={field} value={attributes[field.code]} onChange={(v) => setAttributes((prev) => ({ ...prev, [field.code]: v }))} />
                ))}
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="size-4 shrink-0" /> {error}
            </div>
          )}
          {done && (
            <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
              <CheckCircle2 className="size-4" /> Saqlandi
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {saving ? "Saqlanmoqda..." : "Saqlash"}
          </button>
        </form>

        <div className="rounded-2xl border border-border bg-card/50 p-4">
          <span className="text-xs font-semibold text-foreground/80">Holatni boshqarish</span>
          {actionError && <p className="mt-2 text-xs text-destructive">{actionError}</p>}
          <div className="mt-2 flex flex-wrap gap-2">
            {(listing.lifecycleState === "PUBLISHED" || listing.lifecycleState === "EDITED") && (
              <button onClick={() => runAction("SUSPEND")} disabled={actionPending} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50">
                <PauseCircle className="size-3.5" /> To'xtatish
              </button>
            )}
            {listing.lifecycleState === "SUSPENDED" && (
              <button onClick={() => runAction("RESTORE")} disabled={actionPending} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50">
                <RotateCcw className="size-3.5" /> Qayta tiklash
              </button>
            )}
            {listing.lifecycleState !== "ARCHIVED" && listing.lifecycleState !== "DELETED" && (
              <button onClick={() => runAction("ARCHIVE")} disabled={actionPending} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50">
                <Archive className="size-3.5" /> Arxivlash
              </button>
            )}
            {(listing.lifecycleState === "PUBLISHED" || listing.lifecycleState === "EDITED") && (
              <button onClick={() => runAction("RENEW")} disabled={actionPending} className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50">
                <RefreshCw className="size-3.5" /> Muddatini uzaytirish
              </button>
            )}
            {listing.lifecycleState !== "DELETED" && (
              <button onClick={() => runAction("DELETE")} disabled={actionPending} className="inline-flex items-center gap-1.5 rounded-full bg-destructive/15 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/25 disabled:opacity-50">
                <Trash2 className="size-3.5" /> O'chirish
              </button>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
