/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Click-to-pin location picker for the listing-creation form, built on the same Yandex Maps JS
 * API v2.1 used by `YandexMapView`. Unlike that component (which only *displays* listings), this
 * one lets the user set a single coordinate: click anywhere on the map, drag the pin, or search
 * an address (Yandex geocoder) to jump to it. Reverse-geocodes the picked point so the user sees
 * a human-readable address, not just raw lat/lng.
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Search, AlertTriangle } from "lucide-react";
import { loadYandexMaps } from "@/lib/yandex-maps";

export interface LatLng {
  lat: number;
  lng: number;
}

interface Props {
  value: LatLng;
  onChange: (loc: LatLng) => void;
  height?: string;
  className?: string;
}

const DEFAULT_ZOOM = 14;

export function LocationPicker({ value, onChange, height = "320px", className = "" }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const placemarkRef = useRef<any>(null);
  const ymapsRef = useRef<any>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [address, setAddress] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const reverseGeocode = (ymaps: any, lat: number, lng: number) => {
    setResolving(true);
    ymaps
      .geocode([lat, lng], { results: 1 })
      .then((res: any) => {
        const obj = res.geoObjects.get(0);
        setAddress(obj ? obj.getAddressLine() : null);
      })
      .catch(() => setAddress(null))
      .finally(() => setResolving(false));
  };

  // Init once
  useEffect(() => {
    let cancelled = false;
    loadYandexMaps()
      .then((ymaps) => {
        if (cancelled || !containerRef.current) return;
        ymapsRef.current = ymaps;
        const map = new ymaps.Map(
          containerRef.current,
          { center: [value.lat, value.lng], zoom: DEFAULT_ZOOM, controls: ["zoomControl"] },
          { suppressMapOpenBlock: true },
        );
        const placemark = new ymaps.Placemark(
          [value.lat, value.lng],
          {},
          { preset: "islands#redDotIcon", draggable: true },
        );
        placemark.events.add("dragend", () => {
          const [lat, lng] = placemark.geometry.getCoordinates();
          onChangeRef.current({ lat, lng });
          reverseGeocode(ymaps, lat, lng);
        });
        map.events.add("click", (e: any) => {
          const [lat, lng] = e.get("coords");
          placemark.geometry.setCoordinates([lat, lng]);
          onChangeRef.current({ lat, lng });
          reverseGeocode(ymaps, lat, lng);
        });
        map.geoObjects.add(placemark);
        mapRef.current = map;
        placemarkRef.current = placemark;
        setReady(true);
        reverseGeocode(ymaps, value.lat, value.lng);
      })
      .catch((err) => {
        console.error("[LocationPicker] failed to load", err);
        setFailed(true);
      });
    return () => {
      cancelled = true;
      mapRef.current?.destroy?.();
      mapRef.current = null;
      placemarkRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const ymaps = ymapsRef.current;
    if (!ymaps || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await ymaps.geocode(query, { results: 1 });
      const obj = res.geoObjects.get(0);
      if (!obj) {
        setSearchError("Manzil topilmadi");
        return;
      }
      const [lat, lng] = obj.geometry.getCoordinates();
      placemarkRef.current?.geometry.setCoordinates([lat, lng]);
      mapRef.current?.setCenter([lat, lng], DEFAULT_ZOOM, { duration: 300 });
      onChangeRef.current({ lat, lng });
      setAddress(obj.getAddressLine());
    } catch {
      setSearchError("Qidirishda xatolik");
    } finally {
      setSearching(false);
    }
  };

  if (failed) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border bg-card/40 p-6 text-center ${className}`}
        style={{ height }}
      >
        <AlertTriangle className="size-5 text-muted-foreground" />
        <p className="text-xs text-muted-foreground">
          Xarita yuklanmadi. Internetni tekshiring yoki keyinroq qayta urinib ko'ring.
        </p>
      </div>
    );
  }

  return (
    <div className={className}>
      <form onSubmit={onSearch} className="mb-2.5 flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Manzilni qidirish..."
            className="w-full rounded-xl border border-border bg-background/50 py-2 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="shrink-0 rounded-xl border border-border px-3 py-2 text-xs font-semibold text-foreground transition hover:bg-muted disabled:opacity-50"
        >
          {searching ? <Loader2 className="size-3.5 animate-spin" /> : "Qidirish"}
        </button>
      </form>

      <div className="relative overflow-hidden rounded-2xl border border-border" style={{ height }}>
        <div ref={containerRef} className="absolute inset-0" />
        {!ready && (
          <div className="absolute inset-0 flex items-center justify-center bg-card/60 backdrop-blur-sm">
            <Loader2 className="size-5 animate-spin text-primary" />
          </div>
        )}
      </div>

      <div className="mt-2 flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <MapPin className="mt-0.5 size-3 shrink-0" />
        {searchError ? (
          <span className="text-destructive">{searchError}</span>
        ) : resolving ? (
          <span>Manzil aniqlanmoqda...</span>
        ) : (
          <span>{address ?? `${value.lat.toFixed(5)}, ${value.lng.toFixed(5)}`}</span>
        )}
      </div>
    </div>
  );
}
