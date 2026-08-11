import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { YandexMapView, type MapMarker } from "@/components/map/YandexMapView";
import { useQuery } from "@tanstack/react-query";
import { featuredPropertiesOptions } from "@/features/properties/queries";
import { formatPriceWithUnit } from "@/lib/format";

export function MapPreview() {
  const { t } = useTranslation();
  const { data: properties = [] } = useQuery(featuredPropertiesOptions(40));
  const markers = useMemo<MapMarker[]>(
    () =>
      properties.map((p) => ({
        id: p.id,
        lat: p.location.lat,
        lng: p.location.lng,
        label: formatPriceWithUnit(p.price, p.currency, p.listing_type),
        title: p.title,
        subtitle: `${p.city}, ${p.country}`,
        image: p.media[0]?.url,
        href: `/properties/${p.slug}`,
      })),
    [properties],
  );

  return (
    <section className="py-24">
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-end">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
              <span className="size-1.5 rounded-full bg-success" />
              {t("map.eyebrow", { defaultValue: "Live world map" })}
            </div>
            <h2 className="font-display mt-3 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              {t("map.title")}
            </h2>
            <p className="mt-3 text-base text-muted-foreground">{t("map.subtitle")}</p>
          </div>
          <Link
            to="/map"
            className="group inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            {t("map.cta")}
            <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          className="mt-10"
        >
          <YandexMapView
            markers={markers}
            center={{ lat: 41.3111, lng: 69.2797 }}
            zoom={6}
            height="540px"
            enableDrawTools={false}
          />
        </motion.div>
      </div>
    </section>
  );
}
