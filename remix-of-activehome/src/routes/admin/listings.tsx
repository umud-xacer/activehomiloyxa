import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Building2, ExternalLink, Search } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { listingApi, type BackendListing } from "@/lib/listing-api";
import { categoriesOptions } from "@/features/properties/queries";
import { formatRelativeDate } from "@/lib/format";

export const Route = createFileRoute("/admin/listings")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "E'lonlar — Admin" }] }),
  component: Page,
});

const LIFECYCLE: Record<BackendListing["lifecycleState"], { label: string; cls: string }> = {
  DRAFT: { label: "Qoralama", cls: "bg-muted text-muted-foreground" },
  PENDING_VERIFICATION: { label: "Tekshiruvda", cls: "bg-warning/15 text-warning" },
  PUBLISHED: { label: "Nashr qilingan", cls: "bg-success/15 text-success" },
  EDITED: { label: "Tahrirlangan", cls: "bg-success/15 text-success" },
  SUSPENDED: { label: "To'xtatilgan", cls: "bg-warning/15 text-warning" },
  ARCHIVED: { label: "Arxivlangan", cls: "bg-muted text-muted-foreground" },
  DELETED: { label: "O'chirilgan", cls: "bg-destructive/15 text-destructive" },
};

function Page() {
  const [q, setQ] = useState("");
  const [categoryId, setCategoryId] = useState("");

  const { data: categories = [] } = useQuery(categoriesOptions());
  const { data: listings = [], isLoading } = useQuery({
    queryKey: ["admin", "listings", categoryId],
    queryFn: () => listingApi.listListings({ categoryId: categoryId || undefined, limit: 200 }),
    staleTime: 15_000,
  });

  const filtered = q
    ? listings.filter((l) => l.title.toLowerCase().includes(q.toLowerCase()))
    : listings;

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">E'lonlar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platformadagi barcha e'lonlar — ko'rish, qidirish va kategoriya bo'yicha filtrlash.
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Sarlavha bo'yicha qidirish..."
            className="w-full rounded-full border border-border bg-card py-2 pl-9 pr-3 text-sm"
          />
        </div>
        <select
          value={categoryId}
          onChange={(e) => setCategoryId(e.target.value)}
          className="rounded-full border border-border bg-card px-4 py-2 text-sm"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name.uz_latn ?? c.path}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted-foreground">{filtered.length} ta</span>
      </div>

      {isLoading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-muted" />
      ) : filtered.length === 0 ? (
        <EmptyState icon={Building2} title="E'lon topilmadi" description="Filtrlarni o'zgartiring." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/30 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 font-semibold">Sarlavha</th>
                <th className="px-4 py-2.5 font-semibold">Holat</th>
                <th className="hidden px-4 py-2.5 font-semibold sm:table-cell">Narx</th>
                <th className="hidden px-4 py-2.5 font-semibold md:table-cell">Sana</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((l) => {
                const lc = LIFECYCLE[l.lifecycleState];
                return (
                  <tr key={l.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <div className="max-w-xs truncate font-medium text-foreground">{l.title}</div>
                      <div className="font-mono text-[11px] text-muted-foreground">{l.categoryPath ?? "—"}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${lc.cls}`}>{lc.label}</span>
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground sm:table-cell">
                      {l.price ? `${Number(l.price.amount).toLocaleString("ru-RU")} ${l.price.currency}` : "—"}
                    </td>
                    <td className="hidden px-4 py-3 text-xs text-muted-foreground md:table-cell">
                      {formatRelativeDate(l.createdAt)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to="/properties/$slug"
                        params={{ slug: l.slug }}
                        className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-muted"
                      >
                        Ko'rish <ExternalLink className="size-3" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </AdminShell>
  );
}
