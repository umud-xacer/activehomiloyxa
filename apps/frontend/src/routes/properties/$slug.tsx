import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BedDouble,
  Bath,
  Maximize2,
  MapPin,
  ShieldCheck,
  Sparkles,
  Heart,
  Share2,
  Star,
  Phone,
  Mail,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Container } from "@/components/layout/Container";
import { PropertyCard } from "@/components/data/PropertyCard";
import { ErrorState } from "@/components/state/ErrorState";
import type { MapMarker } from "@/components/map/YandexMapView";
import { ListingLocationSection } from "@/components/listing/ListingLocationSection";
import { nearbyPropertiesOptions, propertyOptions } from "@/features/properties/queries";
import { formatArea, formatCurrency, formatPriceWithUnit } from "@/lib/format";

export const Route = createFileRoute("/properties/$slug")({
  loader: async ({ context, params }) => {
    const data = await context.queryClient.ensureQueryData(propertyOptions(params.slug));
    if (!data) throw notFound();
    context.queryClient.prefetchQuery(nearbyPropertiesOptions(data.id, 4));
    return data;
  },
  head: ({ params, loaderData }) => {
    const url = `https://active-home.lovable.app/properties/${params.slug}`;
    if (!loaderData) {
      return {
        meta: [{ title: "Property — ActiveHome" }, { name: "robots", content: "noindex" }],
      };
    }
    const p = loaderData;
    const place = [p.city, p.country].filter(Boolean).join(", ");
    const title = place ? `${p.title} — ${place} | ActiveHome` : `${p.title} | ActiveHome`;
    const description =
      (p.description ?? "").slice(0, 155) ||
      `${p.bedrooms} bed · ${p.bathrooms} bath${place ? ` · ${place}` : ""}. Verified listing on ActiveHome.`;
    const image = p.media[0]?.url;
    return {
      meta: [
        { title },
        { name: "description", content: description },
        { property: "og:title", content: title },
        { property: "og:description", content: description },
        { property: "og:type", content: "product" },
        { property: "og:url", content: url },
        ...(image
          ? [
              { property: "og:image", content: image },
              { name: "twitter:image", content: image },
            ]
          : []),
      ],
      links: [{ rel: "canonical", href: url }],
      scripts: [
        {
          type: "application/ld+json",
          children: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "Product",
            name: p.title,
            description,
            image: image ? [image] : undefined,
            offers: {
              "@type": "Offer",
              price: p.price,
              priceCurrency: p.currency,
              availability: "https://schema.org/InStock",
              url,
            },
            aggregateRating: p.rating
              ? {
                  "@type": "AggregateRating",
                  ratingValue: p.rating,
                  reviewCount: Math.max(1, p.agent?.reviews ?? 1),
                }
              : undefined,
          }),
        },
      ],
    };
  },
  component: PropertyDetail,
  errorComponent: ({ error, reset }) => <ErrorState error={error} reset={reset} />,
  notFoundComponent: () => (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-32 text-center">
        <h1 className="font-display text-3xl font-semibold">Property not found</h1>
        <p className="mt-2 text-muted-foreground">It may have been removed or relisted.</p>
        <Link
          to="/properties"
          className="mt-6 inline-flex rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          Browse properties
        </Link>
      </div>
    </AppShell>
  ),
});

function PropertyDetail() {
  const { slug } = Route.useParams();
  const { data: property } = useSuspenseQuery(propertyOptions(slug));
  const { data: nearby = [] } = useQuery({
    ...nearbyPropertiesOptions(property?.id ?? "", 4),
    enabled: Boolean(property?.id),
  });

  if (!property) return null;
  const cover = property.media[0]?.url;
  const gallery = property.media.slice(1, 5);

  return (
    <AppShell>
      {/* Gallery */}
      <section className="relative pt-28">
        <Container wide>
          <nav className="mb-4 flex items-center gap-1 text-xs text-muted-foreground">
            <Link to="/" className="hover:text-foreground">
              Home
            </Link>
            <span>/</span>
            <Link to="/properties" className="hover:text-foreground">
              Properties
            </Link>
            <span>/</span>
            <span className="text-foreground">{property.city || property.title}</span>
          </nav>

          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="grid gap-2 overflow-hidden rounded-3xl md:grid-cols-4 md:grid-rows-2"
          >
            {cover && (
              <img
                src={cover}
                alt={property.title}
                className="aspect-[4/3] size-full object-cover md:col-span-2 md:row-span-2 md:aspect-auto"
              />
            )}
            {gallery.map((m) => (
              <img
                key={m.id}
                src={m.url}
                alt={m.alt}
                className="hidden size-full object-cover md:block"
              />
            ))}
          </motion.div>
        </Container>
      </section>

      {/* Body */}
      <section className="py-12">
        <div className="mx-auto grid max-w-7xl gap-10 px-6 lg:grid-cols-[1fr_360px]">
          <div className="space-y-10">
            {/* Title block */}
            <header className="flex flex-wrap items-start justify-between gap-6">
              <div>
                <div className="flex items-center gap-2">
                  {property.verified && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
                      <ShieldCheck className="size-3" /> Verified
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                    <Sparkles className="size-3" /> AI {property.ai_score} · valuation{" "}
                    {formatCurrency(property.ai_valuation, property.currency)}
                  </span>
                </div>
                <h1 className="font-display mt-4 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                  {property.title}
                </h1>
                <div className="mt-2 inline-flex items-center gap-1 text-sm text-muted-foreground">
                  <MapPin className="size-4" />
                  {[property.address, property.city, property.country].filter(Boolean).join(", ")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="inline-flex size-10 items-center justify-center rounded-full border border-border bg-card hover:bg-muted"
                  aria-label="Save"
                >
                  <Heart className="size-4" />
                </button>
                <button
                  className="inline-flex size-10 items-center justify-center rounded-full border border-border bg-card hover:bg-muted"
                  aria-label="Share"
                >
                  <Share2 className="size-4" />
                </button>
              </div>
            </header>

            {/* Stat row */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { icon: BedDouble, label: "Bedrooms", value: property.bedrooms },
                { icon: Bath, label: "Bathrooms", value: property.bathrooms },
                { icon: Maximize2, label: "Area", value: formatArea(property.area_m2) },
                { icon: Star, label: "Rating", value: property.rating.toFixed(1) },
              ].map((s) => (
                <div
                  key={s.label}
                  className="rounded-2xl border border-border bg-card p-4 shadow-soft"
                >
                  <s.icon className="size-4 text-primary" />
                  <div className="mt-2 text-xs uppercase tracking-wider text-muted-foreground">
                    {s.label}
                  </div>
                  <div className="font-display mt-1 text-lg font-semibold text-foreground">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Description */}
            <article className="prose prose-sm max-w-none whitespace-pre-line text-foreground/80">
              <h2 className="font-display text-2xl font-semibold text-foreground">
                About this property
              </h2>
              <p>{property.description}</p>
            </article>

            {/* Amenities */}
            <div>
              <h2 className="font-display text-2xl font-semibold text-foreground">Amenities</h2>
              <div className="mt-4 flex flex-wrap gap-2">
                {property.amenities.map((a) => (
                  <span
                    key={a}
                    className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium capitalize text-foreground/80"
                  >
                    {a.replace("_", " ")}
                  </span>
                ))}
              </div>
            </div>

            <ListingLocationSection
              marker={
                {
                  id: property.id,
                  lat: property.location.lat,
                  lng: property.location.lng,
                  label: formatPriceWithUnit(
                    property.price,
                    property.currency,
                    property.listing_type,
                  ),
                  title: property.title,
                  subtitle: [property.city, property.country].filter(Boolean).join(", "),
                  image: property.media[0]?.url,
                } satisfies MapMarker
              }
              address={property.address}
              height="420px"
            />
          </div>

          {/* Sidebar */}
          <aside className="space-y-6">
            <div className="sticky top-28 space-y-6">
              <div className="rounded-3xl border border-border bg-card p-6 shadow-elevated">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  {property.listing_type === "sale"
                    ? "For sale"
                    : property.listing_type === "rent"
                      ? "For rent"
                      : "Per night"}
                </div>
                <div className="font-display mt-1 text-3xl font-semibold text-foreground">
                  {formatPriceWithUnit(property.price, property.currency, property.listing_type)}
                </div>
                {property.price_per_m2 && (
                  <div className="mt-1 text-xs text-muted-foreground">
                    {formatCurrency(property.price_per_m2, property.currency)} / m²
                  </div>
                )}

                <div className="mt-6 flex items-center gap-3">
                  <img
                    src={property.agent.avatar}
                    alt={property.agent.name}
                    className="size-12 rounded-full object-cover"
                  />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-foreground">
                      {property.agent.name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {property.agent.agency}
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid gap-2">
                  <button className="inline-flex items-center justify-center gap-1.5 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow">
                    <Phone className="size-4" /> Call agent
                  </button>
                  <button className="inline-flex items-center justify-center gap-1.5 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted">
                    <Mail className="size-4" /> Send message
                  </button>
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-4 text-center text-xs">
                  <div>
                    <div className="font-semibold text-foreground">{property.agent.rating}</div>
                    <div className="text-muted-foreground">Rating</div>
                  </div>
                  <div>
                    <div className="font-semibold text-foreground">{property.agent.reviews}</div>
                    <div className="text-muted-foreground">Reviews</div>
                  </div>
                  <div>
                    <div className="font-semibold text-foreground">
                      {property.agent.languages.length}
                    </div>
                    <div className="text-muted-foreground">Languages</div>
                  </div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </section>

      {/* Nearby */}
      {nearby.length > 0 && (
        <section className="border-t border-border bg-card/40 py-16">
          <Container wide>
            <h2 className="font-display text-2xl font-semibold text-foreground sm:text-3xl">
              Similar nearby
            </h2>
            <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {nearby.map((p, i) => (
                <PropertyCard key={p.id} property={p} index={i} />
              ))}
            </div>
          </Container>
        </section>
      )}
    </AppShell>
  );
}
