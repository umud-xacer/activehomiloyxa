import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { featuredPropertiesOptions } from "@/features/properties/queries";

export function FeaturedProperties() {
  const { t } = useTranslation();
  const { data: featured, isLoading } = useQuery(featuredPropertiesOptions(6));

  return (
    <section className="py-24">
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-xl">
            <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              {t("featured.title")}
            </h2>
            <p className="mt-3 text-base text-muted-foreground">{t("featured.subtitle")}</p>
          </div>
          <Link
            to="/properties"
            className="group inline-flex items-center gap-1 text-sm font-semibold text-primary"
          >
            {t("featured.view_all")}
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

        {isLoading || !featured ? (
          <div className="mt-12">
            <PropertyGridSkeleton count={3} />
          </div>
        ) : (
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {featured.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
