import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { MapPin, Phone, Sparkles, Loader2, TreePine, Navigation } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { LeafletMapView, type MapMarker } from "@/components/map/LeafletMapView";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";

const CATEGORY_PATH = "/dam-olish-maskanlari";

export const Route = createFileRoute("/recreation")({
  head: () => ({
    meta: [
      { title: "Dam olish maskanlari — ActiveHome" },
      {
        name: "description",
        content: "O'zbekiston bo'ylab dam olish maskanlarini toping va bron qiling.",
      },
    ],
  }),
  component: Page,
});

function VenueCard({ listing }: { listing: CatalogListing }) {
  const phone = listing.attributes.phone != null ? String(listing.attributes.phone) : undefined;
  const address =
    listing.attributes.address != null ? String(listing.attributes.address) : undefined;
  const amenities =
    listing.attributes.amenities != null ? String(listing.attributes.amenities) : undefined;
  const location = listing.location;

  const marker: MapMarker | null = location
    ? {
        id: listing.id,
        lat: location.latitude,
        lng: location.longitude,
        label: formatUzs(listing.price?.amount),
        title: listing.title,
        subtitle: address,
      }
    : null;

  return (
    <div className="group overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      <div className="flex h-40 items-center justify-center bg-gradient-to-br from-emerald-500/15 to-teal-500/15 text-emerald-600">
        <TreePine className="size-12" />
      </div>
      <div className="p-5">
        <h3 className="font-display text-lg font-semibold text-foreground">{listing.title}</h3>
        <p className="mt-1.5 text-sm text-muted-foreground">{listing.description}</p>

        {address && (
          <div className="mt-3 flex items-start gap-1.5 text-xs text-muted-foreground">
            <MapPin className="mt-0.5 size-3.5 shrink-0" /> {address}
          </div>
        )}
        {amenities && (
          <div className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
            <Sparkles className="mt-0.5 size-3.5 shrink-0" /> {amenities}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
          <div>
            <div className="font-display text-lg font-semibold text-foreground">
              {formatUzs(listing.price?.amount)}
            </div>
            <div className="text-[11px] text-muted-foreground">/ kecha</div>
          </div>
          <div className="flex items-center gap-2">
            {marker && (
              <Dialog>
                <DialogTrigger asChild>
                  <button
                    type="button"
                    aria-label="Xaritada ko'rish"
                    title="Xaritada ko'rish"
                    className="inline-flex size-9 items-center justify-center rounded-full border border-border text-foreground/70 transition hover:border-primary/40 hover:text-primary"
                  >
                    <Navigation className="size-4" />
                  </button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl gap-4 p-4 sm:p-5">
                  <DialogHeader>
                    <DialogTitle className="font-display">{listing.title}</DialogTitle>
                  </DialogHeader>
                  <LeafletMapView
                    markers={[marker]}
                    center={{ lat: marker.lat, lng: marker.lng }}
                    focus={{ id: marker.id, lat: marker.lat, lng: marker.lng, zoom: 14 }}
                    zoom={14}
                    height="420px"
                    showCountBadge={false}
                    enableDrawTools={false}
                    enableSearch={false}
                  />
                </DialogContent>
              </Dialog>
            )}
            {phone && (
              <a
                href={`tel:${phone}`}
                className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
              >
                <Phone className="size-3.5" /> Bron qilish
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Page() {
  const { data: listings, isLoading } = useQuery({
    queryKey: ["catalog", "listings", CATEGORY_PATH],
    queryFn: () => catalogClient.listingsByCategoryPath(CATEGORY_PATH, 40),
  });

  return (
    <AppShell>
      <PageHeader
        eyebrow="Dam olish"
        title="Dam olish maskanlari"
        description="Tog', ko'l va issiq buloq bo'yidagi turbazalar — telefon orqali to'g'ridan-to'g'ri bron qiling."
      />
      <div className="mx-auto max-w-7xl px-4 pb-24 lg:px-8">
        {isLoading && (
          <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {!isLoading && listings?.length === 0 && (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Hozircha dam olish maskani qo'shilmagan.
          </p>
        )}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {listings?.map((listing) => (
            <VenueCard key={listing.id} listing={listing} />
          ))}
        </div>
      </div>
    </AppShell>
  );
}
