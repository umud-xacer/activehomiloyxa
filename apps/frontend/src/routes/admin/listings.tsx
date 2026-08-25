import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Loader2,
  Home,
  Search,
  Trash2,
  Archive,
  RotateCcw,
  Play,
  Sparkles,
  BadgeCheck,
  X,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  adminCatalogApi,
  formatUzs,
  type CatalogListing,
  type ListingStatusAction,
} from "@/lib/catalog-client";
import { billingApi, type Product } from "@/lib/billing-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/listings")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "E'lonlar boshqaruvi — ActiveHome Admin" }] }),
  component: Page,
});

const STATE_LABEL: Record<string, string> = {
  DRAFT: "Qoralama",
  PENDING_VERIFICATION: "Tekshiruvda",
  PUBLISHED: "E'lon qilingan",
  EDITED: "Tahrirlangan",
  SUSPENDED: "To'xtatilgan",
  ARCHIVED: "Arxivlangan",
  DELETED: "O'chirilgan",
  SOLD: "Sotildi",
};

const STATE_CLASS: Record<string, string> = {
  DRAFT: "bg-muted text-muted-foreground",
  PENDING_VERIFICATION: "bg-amber-500/10 text-amber-600",
  PUBLISHED: "bg-success/10 text-success",
  EDITED: "bg-success/10 text-success",
  SUSPENDED: "bg-destructive/10 text-destructive",
  ARCHIVED: "bg-muted text-muted-foreground",
  DELETED: "bg-destructive/10 text-destructive",
  SOLD: "bg-blue-500/10 text-blue-600",
};

const STATES = [
  "DRAFT",
  "PENDING_VERIFICATION",
  "PUBLISHED",
  "EDITED",
  "SUSPENDED",
  "ARCHIVED",
  "DELETED",
  "SOLD",
];

function promotionLabel(product: Product): string {
  return product.name.uz_latn || product.name.ru || product.name.en || product.code;
}

/** `/admin/listings`'s VIP/TOP grant panel (2026-08-24) -- only rendered when the listing has an
 * `ownerProfileId`: `Order.purchaser_profile_id` is a required, non-nullable field (every v1
 * purchase, including an admin-comped one, is business-profile-scoped), so an individually-owned
 * listing has no profile to attribute the grant to -- a real, structural limitation, not a bug,
 * flagged inline rather than silently offering a button that would 500. */
function PromotionGrantPanel({ listing }: { listing: CatalogListing }) {
  const queryClient = useQueryClient();
  const [granting, setGranting] = useState(false);
  const [productId, setProductId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: products } = useQuery({
    queryKey: ["admin", "promotion-products"],
    queryFn: async () => {
      const [premium, featured, top] = await Promise.all([
        billingApi.listProducts("PREMIUM"),
        billingApi.listProducts("FEATURED"),
        billingApi.listProducts("TOP_PLACEMENT"),
      ]);
      return [...premium, ...featured, ...top];
    },
    enabled: granting,
  });

  const grant = async () => {
    if (!productId || !listing.ownerProfileId) return;
    setBusy(true);
    setError(null);
    try {
      await billingApi.adminGrantCredits(listing.ownerProfileId, {
        productId,
        targetType: "LISTING",
        targetId: listing.id,
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "listings"] });
      setGranting(false);
      setProductId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "VIP/TOP berib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  if (!listing.ownerProfileId) {
    return (
      <p className="mt-2 text-[11px] text-muted-foreground">
        VIP/TOP faqat biznes profil egasidagi e'lonlarga berilishi mumkin (jismoniy shaxs e'lonida
        biriktiriladigan profil yo'q).
      </p>
    );
  }

  return (
    <div className="mt-2">
      {!granting ? (
        <button
          type="button"
          onClick={() => setGranting(true)}
          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary transition hover:bg-primary/20"
        >
          <Sparkles className="size-3" /> VIP/TOP berish
        </button>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {!products ? (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
          ) : (
            <select
              value={productId}
              onChange={(e) => setProductId(e.target.value)}
              className="min-w-[200px] flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none focus:border-primary"
            >
              <option value="" disabled>
                Mahsulotni tanlang
              </option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {promotionLabel(p)} — {Number(p.price.amount).toLocaleString("uz-UZ")} so'm
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            disabled={busy || !productId}
            onClick={grant}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            {busy && <Loader2 className="size-3.5 animate-spin" />}
            Bepul berish
          </button>
          <button
            type="button"
            onClick={() => setGranting(false)}
            className="rounded-full bg-muted px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground transition hover:bg-muted/70"
          >
            Bekor qilish
          </button>
        </div>
      )}
      {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
    </div>
  );
}

function ListingRow({ listing, index }: { listing: CatalogListing; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<ListingStatusAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const state = listing.lifecycleState ?? "DRAFT";

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "listings"] });

  const apply = async (action: ListingStatusAction) => {
    setBusy(action);
    setError(null);
    try {
      await adminCatalogApi.changeStatus(listing.id, action, "Admin panel orqali");
      await invalidate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.03, duration: 0.3 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-4 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATE_CLASS[state] ?? "bg-muted text-muted-foreground"}`}
            >
              {STATE_LABEL[state] ?? state}
            </span>
            {listing.awaitingPayment && (
              <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-amber-600">
                To'lov kutilmoqda
              </span>
            )}
            {listing.promotion && (
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
                <Sparkles className="size-3" /> {listing.promotion.kind}
              </span>
            )}
          </div>
          <p className="mt-1 truncate text-sm font-semibold text-foreground">{listing.title}</p>
          <p className="truncate text-xs text-muted-foreground">
            {listing.categoryPath ?? "—"} · {formatUzs(listing.price?.amount) || "narxsiz"} ·{" "}
            {listing.id}
          </p>
          <PromotionGrantPanel listing={listing} />
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
          {state !== "PUBLISHED" && state !== "DELETED" && state !== "SOLD" && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => apply("PUBLISH")}
              className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-success/20 disabled:opacity-50"
            >
              {busy === "PUBLISH" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Play className="size-3.5" />
              )}
              Chop etish
            </button>
          )}
          {(state === "PUBLISHED" || state === "EDITED") && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => apply("SUSPEND")}
              className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
            >
              {busy === "SUSPEND" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <ShieldAlert className="size-3.5" />
              )}
              To'xtatish
            </button>
          )}
          {(state === "SUSPENDED" || state === "ARCHIVED" || state === "SOLD") && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => apply("RESTORE")}
              className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/70 disabled:opacity-50"
            >
              {busy === "RESTORE" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <RotateCcw className="size-3.5" />
              )}
              Qayta tiklash
            </button>
          )}
          {(state === "PUBLISHED" || state === "EDITED") && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => apply("SOLD")}
              className="inline-flex items-center gap-1.5 rounded-full bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-600 transition hover:bg-blue-500/20 disabled:opacity-50"
            >
              {busy === "SOLD" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <BadgeCheck className="size-3.5" />
              )}
              Sotildi deb belgilash
            </button>
          )}
          {(state === "PUBLISHED" || state === "EDITED") && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => apply("ARCHIVE")}
              className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/70 disabled:opacity-50"
            >
              {busy === "ARCHIVE" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Archive className="size-3.5" />
              )}
              Arxivlash
            </button>
          )}
          {state !== "DELETED" && (
            <ConfirmDialog
              trigger={
                <button
                  type="button"
                  disabled={busy !== null}
                  title="O'chirish — qaytarib bo'lmaydi"
                  className="inline-flex items-center gap-1.5 rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground transition hover:opacity-90 disabled:opacity-50"
                >
                  {busy === "DELETE" ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="size-3.5" />
                  )}
                  O'chirish
                </button>
              }
              title="E'lonni o'chirish"
              description={`"${listing.title}" e'lonini o'chirmoqchimisiz? Bu amalni ortga qaytarib bo'lmaydi.`}
              confirmLabel="O'chirish"
              onConfirm={() => apply("DELETE")}
            />
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const [stateFilter, setStateFilter] = useState("");
  const [query, setQuery] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "listings", stateFilter, query],
    queryFn: () =>
      adminCatalogApi.listListings({
        state: stateFilter || undefined,
        query: query || undefined,
        limit: 50,
      }),
    retry: false,
  });

  const items = data?.items ?? [];

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            E'lonlar boshqaruvi
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Platformadagi barcha e'lonlar — istalgan holat, istalgan egasi. Holatini o'zgartiring
            yoki VIP/TOP maqomini bering.
          </p>
        </motion.div>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={Home}
            label="Ko'rsatilmoqda"
            value={data?.page.limit ? items.length : items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Play}
            label="Chop etilgan (shu sahifada)"
            value={items.filter((i) => i.lifecycleState === "PUBLISHED").length}
            accent="success"
            index={1}
          />
          <StatCard
            icon={ShieldAlert}
            label="To'lov kutilmoqda (shu sahifada)"
            value={items.filter((i) => i.awaitingPayment).length}
            accent="warning"
            index={2}
          />
        </section>

        <SectionCard
          title="Qidiruv va filtr"
          icon={Search}
          index={0}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setStateFilter("")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                  stateFilter === ""
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                }`}
              >
                Barchasi
              </button>
              {STATES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStateFilter(s)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    stateFilter === s
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                  }`}
                >
                  {STATE_LABEL[s]}
                </button>
              ))}
            </div>
          }
        >
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Sarlavha bo'yicha qidirish…"
              className="w-full rounded-xl border border-border bg-background py-2.5 pl-10 pr-9 text-sm outline-none focus:border-primary"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </SectionCard>

        <SectionCard title="E'lonlar ro'yxati" icon={Home} index={1}>
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}

          {error instanceof ApiError && error.status === 403 && (
            <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <ShieldAlert className="mt-0.5 size-5 shrink-0" />
              Bu sahifa faqat "catalog:listing:moderate" ruxsatiga ega adminlar uchun.
            </div>
          )}

          {data && items.length === 0 && (
            <EmptyState
              icon={Home}
              title="E'lon topilmadi"
              description="Qidiruv yoki filtrni o'zgartirib ko'ring."
            />
          )}

          <div className="space-y-3">
            {items.map((listing, i) => (
              <ListingRow key={listing.id} listing={listing} index={i} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
