/**
 * Shared "Joylashuvi" section for every Product Detail page (catalog listing, property,
 * investment opportunity, ...). Shows the mini map + an address line, and a "Marshrut" button
 * that hands the marker to `YandexMapView` via `navigateTarget` -- the map then expands itself to
 * a full-screen turn-by-turn navigation experience (see `YandexMapView`'s `startNavigation`,
 * which sets `fullscreen` as soon as a nav target arrives). One component so every detail page
 * gets the same "Marshrut" behavior instead of each re-wiring its own mini-map + button.
 */
import { useState } from "react";
import { MapPin, Navigation } from "lucide-react";
import { YandexMapView, type MapMarker } from "@/components/map/YandexMapView";

export function ListingLocationSection({
  marker,
  address,
  height = "360px",
}: {
  marker: MapMarker;
  address?: string | null;
  height?: string;
}) {
  const [navTarget, setNavTarget] = useState<MapMarker | null>(null);

  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold text-foreground">Joylashuvi</h2>
        <button
          type="button"
          onClick={() => setNavTarget({ ...marker })}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
        >
          <Navigation className="size-3.5" />
          Marshrut
        </button>
      </div>
      {address && (
        <p className="mb-3 flex items-center gap-1.5 text-sm text-muted-foreground">
          <MapPin className="size-3.5 shrink-0" /> {address}
        </p>
      )}
      <YandexMapView
        markers={[marker]}
        center={{ lat: marker.lat, lng: marker.lng }}
        zoom={13}
        height={height}
        enableDrawTools={false}
        enableSearch={false}
        showCountBadge={false}
        navigateTarget={navTarget}
        onNavigateHandled={() => setNavTarget(null)}
      />
    </section>
  );
}
