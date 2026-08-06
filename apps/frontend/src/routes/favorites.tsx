import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Heart, Loader2, Trash2, Search } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { LifecycleBadge } from "@/components/dashboard/ListingsTable";
import { useMe } from "@/features/auth/useAuth";
import { favoritesApi } from "@/lib/favorites-client";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/favorites")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Saqlanganlar — ActiveHome" },
      { name: "description", content: "Siz saqlagan e'lonlar." },
    ],
  }),
  component: Page,
});

interface HydratedFavorite {
  listingId: string;
  createdAt: string;
  listing: CatalogListing | null;
}

function Page() {
  const { data: account } = useMe();
  const queryClient = useQueryClient();

  const { data: favorites = [], isLoading } = useQuery({
    queryKey: ["favorites"],
    queryFn: async (): Promise<HydratedFavorite[]> => {
      const page = await favoritesApi.list();
      return Promise.all(
        page.items.map(async (f) => {
          try {
            const listing = await catalogClient.getListing(f.listingId);
            return { listingId: f.listingId, createdAt: f.createdAt, listing };
          } catch {
            return { listingId: f.listingId, createdAt: f.createdAt, listing: null };
          }
        }),
      );
    },
  });

  const [error, setError] = useState<string | null>(null);

  const remove = async (listingId: string) => {
    setError(null);
    try {
      await favoritesApi.remove(listingId);
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Olib tashlab bo'lmadi.");
    }
  };

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 lg:px-8">
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive">
            {error}
          </div>
        )}
        <SectionCard title="Saqlanganlar" icon={Heart} noPadding={favorites.length > 0}>
          {isLoading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          ) : favorites.length === 0 ? (
            <EmptyState
              icon={Heart}
              title="Hali saqlangan e'lon yo'q"
              description="Yoqqan uy yoki xizmatni saqlash uchun yurak belgisini bosing."
              action={
                <Link
                  to="/properties"
                  className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
                >
                  <Search className="size-3.5" /> E'lonlarni ko'rish
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {favorites.map((f) => (
                <li key={f.listingId} className="flex items-center justify-between gap-4 px-6 py-4">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-foreground">
                      {f.listing?.title ?? "E'lon topilmadi"}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                      {f.listing && (
                        <>
                          <span>{formatUzs(f.listing.price?.amount)}</span>
                          <LifecycleBadge state={f.listing.lifecycleState} />
                        </>
                      )}
                      <span>Saqlangan: {new Date(f.createdAt).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(f.listingId)}
                    aria-label="Olib tashlash"
                    title="Olib tashlash"
                    className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
