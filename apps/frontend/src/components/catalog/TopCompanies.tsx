/**
 * "Top kompaniyalar" -- the premium brands/organizations rail every category in the enterprise
 * spec asks for (`active-home.pdf`). Built entirely from data that already exists on the public
 * API rather than a new bounded context: `CatalogListing.ownerProfileId` (public listing DTO) +
 * `businessProfilesApi.get()` (public `GET /business-profiles/{id}`, already used by the
 * legal-entity dashboard). Ranking is a client-side count over the listings already fetched for
 * this category -- there's no cross-owner aggregate query on the backend yet (`list_by_owner*` in
 * `catalog/infrastructure/persistence/repository.py` is scoped to one known owner), so this reads
 * "top among what's currently loaded", not a true global ranking. Good enough for a category page
 * rail; a real ranking would need a backend aggregate query later.
 */
import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, ShieldCheck } from "lucide-react";
import { businessProfilesApi, type BusinessProfile } from "@/lib/business-profiles-client";
import type { CatalogListing } from "@/lib/catalog-client";

function profileName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Kompaniya";
}

export function useTopCompanies(listings: CatalogListing[], limit = 6) {
  const counts = useMemo(() => {
    const byProfile = new Map<string, number>();
    for (const listing of listings) {
      if (!listing.ownerProfileId) continue;
      byProfile.set(listing.ownerProfileId, (byProfile.get(listing.ownerProfileId) ?? 0) + 1);
    }
    return [...byProfile.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([profileId, count]) => ({ profileId, count }));
  }, [listings, limit]);

  const results = useQueries({
    queries: counts.map(({ profileId }) => ({
      queryKey: ["business-profile", profileId],
      queryFn: () => businessProfilesApi.get(profileId),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  return counts
    .map(({ profileId, count }, i) => ({ profileId, count, profile: results[i]?.data }))
    .filter((c) => !!c.profile) as { profileId: string; count: number; profile: BusinessProfile }[];
}

export function TopCompanies({
  companies,
  selectedId,
  onSelect,
}: {
  companies: { profileId: string; count: number; profile: BusinessProfile }[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  if (companies.length === 0) return null;

  return (
    <section className="mt-14">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold text-foreground">Top kompaniyalar</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Shu kategoriyada eng ko'p e'lon joylagan tashkilotlar.
          </p>
        </div>
        {selectedId && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="shrink-0 text-xs font-medium text-primary hover:underline"
          >
            Barchasini ko'rsatish
          </button>
        )}
      </div>

      <div className="scrollbar-none flex gap-3 overflow-x-auto pb-2">
        {companies.map(({ profileId, count, profile }, i) => {
          const active = selectedId === profileId;
          const verified = profile.badge?.status === "VALID";
          return (
            <motion.button
              key={profileId}
              type="button"
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.04 }}
              onClick={() => onSelect(active ? null : profileId)}
              className={`flex w-56 shrink-0 flex-col items-start gap-3 rounded-2xl border p-4 text-left shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated ${
                active ? "border-primary bg-primary/5" : "border-border bg-card"
              }`}
            >
              <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Building2 className="size-5" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-semibold text-foreground">
                    {profileName(profile)}
                  </span>
                  {verified && (
                    <ShieldCheck
                      className="size-3.5 shrink-0 text-primary"
                      aria-label="Tasdiqlangan"
                    />
                  )}
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">{count} ta e'lon</p>
              </div>
            </motion.button>
          );
        })}
      </div>
    </section>
  );
}
