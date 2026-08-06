import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AppShell } from "@/components/layout/AppShell";
import { YandexMapView, type AreaSearch } from "@/components/map/YandexMapView";
import { PropertyCard } from "@/components/data/PropertyCard";
import { propertyListOptions } from "@/features/properties/queries";
import type { Property } from "@/features/properties/types";

export const Route = createFileRoute("/map")({
  head: () => ({
    meta: [
      { title: "Map search — ActiveHome" },
      {
        name: "description",
        content:
          "Real-time interactive map search. Satellite, terrain, traffic, polygon and radius search across global listings.",
      },
    ],
  }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(propertyListOptions({ page_size: 120 })),
  component: MapPage,
});

function MapPage() {
  const { t } = useTranslation();
  const { data } = useSuspenseQuery(propertyListOptions({ page_size: 120 }));
  const [selected, setSelected] = useState<Property | null>(null);
  const [filtered, setFiltered] = useState<Property[] | null>(null);

  const properties = filtered ?? data.items;

  const onAreaSearch = (area: AreaSearch) => {
    const inside = data.items.filter((p) => {
      const { lat, lng } = p.location;
      return (
        lng >= area.bbox.west &&
        lng <= area.bbox.east &&
        lat >= area.bbox.south &&
        lat <= area.bbox.north
      );
    });
    setFiltered(inside);
  };

  return (
    <AppShell>
      <div className="grid min-h-screen pt-20 lg:grid-cols-[420px_1fr]">
        {/* Sidebar list */}
        <aside className="border-r border-border bg-background">
          <div className="sticky top-20 border-b border-border bg-background/95 px-6 py-5 backdrop-blur">
            <div className="text-xs uppercase tracking-widest text-muted-foreground">
              {t("mapPage.eyebrow", "Xarita bo'yicha qidiruv")}
            </div>
            <h1 className="font-display mt-1 text-2xl font-semibold text-foreground">
              {properties.length.toLocaleString()} {t("mapPage.listings", "e'lon")}
              {filtered && (
                <button
                  onClick={() => setFiltered(null)}
                  className="ml-3 rounded-full border border-border bg-card px-2.5 py-0.5 align-middle text-[11px] font-medium text-foreground/70 hover:bg-muted"
                >
                  {t("mapPage.clearArea", "Hududni tozalash")}
                </button>
              )}
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("mapPage.hint", "Ko'rinadigan e'lonlarni filtrlash uchun xaritadagi ko'pburchak yoki radius asbobidan foydalaning.")}
            </p>
          </div>


          <div className="grid grid-cols-1 gap-4 p-6 sm:grid-cols-2 lg:grid-cols-1">
            {properties.slice(0, 30).map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        </aside>

        {/* Map column */}
        <div className="relative">
          <div className="sticky top-20 p-4">
            <YandexMapView
              properties={properties}
              center={
                selected
                  ? { lat: selected.location.lat, lng: selected.location.lng }
                  : { lat: 41.3111, lng: 69.2797 }
              }
              zoom={selected ? 14 : 5}
              height="calc(100vh - 7rem)"
              onSelect={setSelected}
              onAreaSearch={onAreaSearch}
            />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
