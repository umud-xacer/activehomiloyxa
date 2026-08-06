import { createFileRoute, Link, notFound, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useSuspenseQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BedDouble,
  Bath,
  Maximize2,
  MapPin,
  ShieldCheck,
  Heart,
  Share2,
  Star,
  Phone,
  Mail,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PropertyCard } from "@/components/data/PropertyCard";
import { ErrorState } from "@/components/state/ErrorState";
import { YandexMapView } from "@/components/map/YandexMapView";
import {
  nearbyPropertiesOptions,
  propertyOptions,
} from "@/features/properties/queries";
import { formatArea, formatCurrency, formatPriceWithUnit } from "@/lib/format";
import { messagingApi } from "@/lib/messaging-api";
import { getSessionToken } from "@/lib/auth-session";

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
        meta: [
          { title: "Property — ActiveHome" },
          { name: "robots", content: "noindex" },
        ],
      };
    }
    const p = loaderData;
    const title = `${p.title} — ${p.city}, ${p.country} | ActiveHome`;
    const description = (p.description ?? "").slice(0, 155) || `${p.bedrooms} bed · ${p.bathrooms} bath · ${p.city}. Verified listing on ActiveHome.`;
    const image = p.media[0]?.url;
    return {
      meta: [
        { title },
        { name: "description", content: description },
        { property: "og:title", content: title },
        { property: "og:description", content: description },
        { property: "og:type", content: "product" },
        { property: "og:url", content: url },
        ...(image ? [{ property: "og:image", content: image }, { name: "twitter:image", content: image }] : []),
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
  const navigate = useNavigate();
  const { data: property } = useSuspenseQuery(propertyOptions(slug));
  if (!property) return null;
  const { data: nearby = [] } = useSuspenseQuery(nearbyPropertiesOptions(property.id, 4));
  const [sending, setSending] = useState(false);

  const cover = property.media[0]?.url;
  const gallery = property.media.slice(1, 5);

  const onSendMessage = async () => {
    if (!getSessionToken()) {
      navigate({ to: "/auth/sign-in" });
      return;
    }
    const message = window.prompt("Egasiga xabar yozing:", `Salom, "${property.title}" haqida so'ramoqchi edim.`);
    if (!message) return;
    setSending(true);
    try {
      await messagingApi.startConversation(property.id, message);
      navigate({ to: "/messages" });
    } finally {
      setSending(false);
    }
  };

  return (
    <AppShell>
      {/* Gallery */}
      <section className="relative pt-28">
        <div className="mx-auto max-w-7xl px-6">
          <nav className="mb-4 flex items-center gap-1 text-xs text-muted-foreground">
            <Link to="/" className="hover:text-foreground">Home</Link>
            <span>/</span>
            <Link to="/properties" className="hover:text-foreground">Properties</Link>
            <span>/</span>
            <span className="text-foreground">{property.city}</span>
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
        </div>
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
                </div>
                <h1 className="font-display mt-4 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
                  {property.title}
                </h1>
                <div className="mt-2 inline-flex items-center gap-1 text-sm text-muted-foreground">
                  <MapPin className="size-4" />
                  {property.address}, {property.city}, {property.country}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button className="inline-flex size-10 items-center justify-center rounded-full border border-border bg-card hover:bg-muted" aria-label="Save">
                  <Heart className="size-4" />
                </button>
                <button className="inline-flex size-10 items-center justify-center rounded-full border border-border bg-card hover:bg-muted" aria-label="Share">
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
                { icon: Star, label: "Year built", value: property.year_built },
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
              <h2 className="font-display text-2xl font-semibold text-foreground">About this property</h2>
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

            {/* Map */}
            <div>
              <h2 className="font-display text-2xl font-semibold text-foreground">Location</h2>
              <div className="mt-4">
                <YandexMapView
                  properties={[property]}
                  center={{ lat: property.location.lat, lng: property.location.lng }}
                  zoom={15}
                  height="420px"
                  showCountBadge={false}
                />
              </div>
            </div>
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
                  <button
                    onClick={onSendMessage}
                    disabled={sending}
                    className="inline-flex items-center justify-center gap-1.5 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-60"
                  >
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
          <div className="mx-auto max-w-7xl px-6">
            <h2 className="font-display text-2xl font-semibold text-foreground sm:text-3xl">
              Similar nearby
            </h2>
            <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {nearby.map((p, i) => (
                <PropertyCard key={p.id} property={p} index={i} />
              ))}
            </div>
          </div>
        </section>
      )}
    </AppShell>
  );
}
