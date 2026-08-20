import { useMemo, useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2,
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Film,
  Globe,
  Layers,
  Link2,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Package,
  Phone,
  Play,
  ShieldCheck,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_SLUG,
  MAIN_CATEGORY_ACCENT,
  SUB_CATEGORY_LABEL,
  SUB_CATEGORY_SLUG,
  type PortfolioItem,
} from "@/lib/business-profiles-client";
import { http } from "@/lib/http";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";
import { useMediaAsset } from "@/lib/use-media-asset";
import { formatDuration, useVideoDuration } from "@/lib/use-video-duration";
import { searchPlaces } from "@/lib/geocoding";
import { ListingLocationSection } from "@/components/listing/ListingLocationSection";
import type { MapMarker } from "@/components/map/YandexMapView";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { TelegramIcon, InstagramIcon, FacebookIcon } from "@/components/site/SocialIcons";

export const Route = createFileRoute("/companies/$slug")({
  head: () => ({ meta: [{ title: "Tashkilot — ActiveHome" }] }),
  component: Page,
});

interface SearchHitLite {
  listingId: string;
  title: string;
  price?: { amount: string; currency: string } | null;
}

interface MediaAssetLite {
  id: string;
  url?: string | null;
  variants?: Array<{ kind: string; url: string }>;
}

/** Shared by the portfolio grid/carousel AND the promo-video preview cards -- both open the same
 * lightbox, keyed by `mediaAssetId` alone (a promo video has no `PortfolioItem` id). */
interface LightboxItem {
  mediaAssetId: string;
}

function SectionEyebrow({ children }: { children: string }) {
  return (
    <div className="mb-2 inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-primary">
      <span className="h-px w-5 bg-primary/50" /> {children}
    </div>
  );
}

/** Derives an honest "N yil/oy platformada" tenure string from the profile's real `createdAt` --
 * the only time-based field that actually exists on `BusinessProfile` (there is no "years of
 * experience" or founding-date field anywhere in the backend, see the Organizations landing-page
 * redesign research). Never fabricated -- returns `null` (renders nothing) if `createdAt` is
 * missing or unparseable rather than guessing. */
function tenureLabel(createdAt: string | undefined): string | null {
  if (!createdAt) return null;
  const created = new Date(createdAt);
  if (Number.isNaN(created.getTime())) return null;
  const now = new Date();
  const months =
    (now.getFullYear() - created.getFullYear()) * 12 + (now.getMonth() - created.getMonth());
  if (months < 1) return "Yangi hamkor";
  if (months < 12) return `${months} oy`;
  const years = Math.floor(months / 12);
  return `${years} yil`;
}

/** One tile in the "About & metrics" band. Every value here is a real, derivable number (tenure
 * from `createdAt`, portfolio/listing counts from their actual arrays, sector from
 * `mainCategory`/`subCategory`) -- deliberately NOT a rating, review count, or staff count, since
 * none of those fields exist anywhere in the backend (confirmed by research before building this
 * page) and fabricating them would violate this project's own no-fake-data convention. */
function StatTile({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 shadow-soft">
      <span
        className={`mb-2.5 flex size-9 items-center justify-center rounded-lg ${accent ? "" : "bg-primary/10 text-primary"}`}
        style={accent ? { background: `${accent}1a`, color: accent } : undefined}
      >
        <Icon className="size-4" />
      </span>
      <div className="font-display truncate text-base font-semibold leading-tight text-foreground">
        {value}
      </div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

/** One tile in the portfolio gallery -- rendered identically inside the mobile horizontal
 * carousel and the desktop 3-column grid, only the wrapping layout differs between the two. */
function GalleryTile({
  item,
  index,
  onOpen,
  className = "",
}: {
  item: PortfolioItem;
  index: number;
  onOpen: () => void;
  className?: string;
}) {
  const asset = useMediaAsset(item.mediaAssetId);
  const video = asset?.contentType?.startsWith("video/");

  return (
    <motion.button
      type="button"
      onClick={onOpen}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className={`group relative aspect-square overflow-hidden rounded-2xl border border-border bg-muted shadow-soft transition-shadow duration-300 hover:shadow-elevated ${className}`}
    >
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video
          src={asset.url}
          preload="metadata"
          muted
          playsInline
          className="size-full object-cover"
        />
      ) : (
        <img
          src={asset.url}
          alt=""
          loading="lazy"
          className="size-full object-cover transition duration-500 group-hover:scale-110"
        />
      )}
      <div className="absolute inset-0 flex items-end bg-gradient-to-t from-black/70 via-black/0 to-transparent p-4 opacity-0 transition duration-300 group-hover:opacity-100">
        <span className="text-sm font-semibold text-white">Loyiha #{index + 1}</span>
      </div>
      {video && (
        <div className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
          <Film className="size-3" /> Video
        </div>
      )}
    </motion.button>
  );
}

/** Mobile: swipeable horizontal carousel (`overflow-x-auto` + scroll-snap). Desktop (`lg:`): a
 * clean 3-column grid, per spec. Two layout wrappers around the same `GalleryTile`. */
function PortfolioGalleryLayout({
  items,
  onOpen,
}: {
  items: PortfolioItem[];
  onOpen: (index: number) => void;
}) {
  return (
    <>
      <div className="-mx-6 flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-px-6 px-6 pb-2 scrollbar-none lg:hidden">
        {items.map((item, i) => (
          <GalleryTile
            key={item.id}
            item={item}
            index={i}
            onOpen={() => onOpen(i)}
            className="w-[64%] shrink-0 snap-center sm:w-[38%]"
          />
        ))}
      </div>
      <div className="hidden lg:grid lg:grid-cols-3 lg:gap-4">
        {items.map((item, i) => (
          <GalleryTile key={item.id} item={item} index={i} onOpen={() => onOpen(i)} />
        ))}
      </div>
    </>
  );
}

function MediaLightbox({
  items,
  index,
  autoPlay,
  onClose,
  onNavigate,
}: {
  items: LightboxItem[];
  index: number;
  autoPlay?: boolean;
  onClose: () => void;
  onNavigate: (next: number) => void;
}) {
  const item = items[index];
  const asset = useMediaAsset(item?.mediaAssetId);
  const video = asset?.contentType?.startsWith("video/");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onNavigate((index + 1) % items.length);
      if (e.key === "ArrowLeft") onNavigate((index - 1 + items.length) % items.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, items.length, onClose, onNavigate]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute right-4 top-4 flex size-10 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
      >
        <X className="size-5" />
      </button>
      {items.length > 1 && (
        <>
          <span className="absolute left-4 top-4 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium text-white/80">
            {index + 1} / {items.length}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onNavigate((index - 1 + items.length) % items.length);
            }}
            className="absolute left-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:left-6"
          >
            <ChevronLeft className="size-6" />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onNavigate((index + 1) % items.length);
            }}
            className="absolute right-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20 sm:right-6"
          >
            <ChevronRight className="size-6" />
          </button>
        </>
      )}
      <motion.div
        key={index}
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2 }}
        className="mx-4 flex max-h-[85vh] max-w-4xl items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {!asset?.url ? (
          <Loader2 className="size-8 animate-spin text-white/70" />
        ) : video ? (
          <video
            src={asset.url}
            controls
            autoPlay={autoPlay}
            className="max-h-[85vh] rounded-xl shadow-2xl"
          />
        ) : (
          <img
            src={asset.url}
            alt=""
            className="max-h-[85vh] rounded-xl object-contain shadow-2xl"
          />
        )}
      </motion.div>
    </motion.div>
  );
}

/** Promo video preview card -- a YouTube-style thumbnail (native browser-rendered first frame
 * via `<video preload="metadata">`, no server-side poster since ADR-0008 does zero video
 * processing) with a centered Play button and a "0:30"-style duration badge, per spec. Clicking
 * opens the shared lightbox with `autoPlay` instead of playing inline. */
function PromoVideoCard({ mediaAssetId, onOpen }: { mediaAssetId: string; onOpen: () => void }) {
  const asset = useMediaAsset(mediaAssetId);
  const durationSeconds = useVideoDuration(asset?.url);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group relative aspect-video w-full max-w-sm shrink-0 overflow-hidden rounded-2xl border border-border bg-muted shadow-soft transition-shadow duration-300 hover:shadow-elevated"
    >
      {asset?.url ? (
        <video
          src={asset.url}
          preload="metadata"
          muted
          playsInline
          className="size-full object-cover"
        />
      ) : (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      )}
      <div className="absolute inset-0 bg-black/20 transition-colors duration-300 group-hover:bg-black/35" />
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-white/90 text-primary shadow-elevated transition-transform duration-300 group-hover:scale-110">
          <Play className="ml-0.5 size-6 fill-current" />
        </span>
      </div>
      {durationSeconds !== null && (
        <span className="absolute bottom-2 right-2 rounded-full bg-black/70 px-2 py-0.5 text-[11px] font-semibold text-white">
          {formatDuration(durationSeconds)}
        </span>
      )}
    </button>
  );
}

function CompanySocialLinks({
  links,
}: {
  links: { telegram?: string; instagram?: string; facebook?: string };
}) {
  const items = [
    { key: "telegram", href: links.telegram, Icon: TelegramIcon, bg: "#24A1DE" },
    {
      key: "instagram",
      href: links.instagram,
      Icon: InstagramIcon,
      bg: "radial-gradient(circle at 30% 110%, #feda75 0%, #fa7e1e 20%, #d62976 45%, #962fbf 65%, #4f5bd5 90%)",
    },
    { key: "facebook", href: links.facebook, Icon: FacebookIcon, bg: "#1877F2" },
  ].filter((i) => i.href);

  if (items.length === 0) return null;

  return (
    <div className="flex items-center gap-2 px-2 py-2">
      {items.map(({ key, href, Icon, bg }) => (
        <a
          key={key}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="flex size-9 items-center justify-center rounded-full text-white shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated"
          style={{ background: bg }}
        >
          <Icon />
        </a>
      ))}
    </div>
  );
}

/** Resolves a catalog listing's first CLEAN image to a real delivery URL -- same fetch pattern as
 * `ListingCards.tsx`'s own (private, unexported) `useListingThumbnail`, duplicated here rather
 * than imported since that helper isn't exported from its module. */
function useListingThumbnail(listing: CatalogListing): string | undefined {
  const image = listing.images?.find((img) => img.status === "CLEAN");
  const { data } = useQuery({
    queryKey: ["media-asset", image?.mediaAssetId],
    queryFn: () => http.get<MediaAssetLite>(`/media/${image!.mediaAssetId}`),
    enabled: image != null,
    staleTime: 5 * 60_000,
  });
  if (!data) return undefined;
  const thumbnail = data.variants?.find((v) => v.kind === "THUMBNAIL");
  return thumbnail?.url ?? data.url ?? undefined;
}

/** One card in the "Xizmatlar va mahsulotlar" grid -- a real `catalog` listing this business
 * posted under its own profile (`Listing.ownerProfileId`), not a fabricated services list (no
 * such entity exists in the backend). Links straight to the listing's real detail page, where the
 * actual "contact seller" / request flow already lives, instead of duplicating an inert inquiry
 * button here. */
function ServiceListingCard({ listing, index }: { listing: CatalogListing; index: number }) {
  const thumbnailUrl = useListingThumbnail(listing);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.05, 0.3), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/listing/$listingId"
        params={{ listingId: listing.id }}
        className="group flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
      >
        <div className="h-36 overflow-hidden bg-muted">
          {thumbnailUrl ? (
            <img
              src={thumbnailUrl}
              alt={listing.title}
              loading="lazy"
              className="size-full object-cover transition duration-500 group-hover:scale-105"
            />
          ) : (
            <div className="flex size-full items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
              <Package className="size-8" />
            </div>
          )}
        </div>
        <div className="flex flex-1 flex-col p-4">
          <h3 className="font-display line-clamp-1 text-sm font-semibold text-foreground">
            {listing.title}
          </h3>
          {listing.description && (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
          )}
          <div className="mt-3 flex items-center justify-between gap-2 border-t border-border/60 pt-3">
            <span className="text-sm font-semibold text-foreground">
              {formatUzs(listing.price?.amount) || "Narx kelishiladi"}
            </span>
            <span className="text-xs font-medium text-primary transition group-hover:underline">
              So'rov yuborish →
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

/** Loading-state layout, shaped like the real hero + metrics band so the page never pops/jumps
 * once real data lands (spec: "chiroyli Skeleton Loading" rather than a bare spinner). */
function PageSkeleton() {
  return (
    <AppShell>
      <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6 sm:pt-28">
        <Skeleton className="h-48 w-full rounded-2xl md:h-72" />
        <div className="flex flex-col gap-5 px-1 pb-2 pt-4 sm:flex-row sm:items-end sm:px-2">
          <div className="-mt-12 flex items-end gap-4 md:-mt-16">
            <Skeleton className="size-24 shrink-0 rounded-2xl border-4 border-background md:size-32" />
            <div className="space-y-2 pb-2">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-4 w-28" />
            </div>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 rounded-2xl" />
          ))}
        </div>
      </section>
    </AppShell>
  );
}

function Page() {
  const { slug } = Route.useParams();
  const {
    data: profile,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["business-profiles", "slug", slug],
    queryFn: () => businessProfilesApi.getBySlug(slug),
    retry: false,
  });
  const { data: portfolio } = useQuery({
    queryKey: ["business-profiles", "portfolio", profile?.id],
    queryFn: () => businessProfilesApi.listPortfolio(profile!.id),
    enabled: !!profile,
  });
  const { data: searchResult } = useQuery({
    queryKey: ["search", "owner-profile", profile?.id],
    queryFn: () =>
      http.get<{ items: SearchHitLite[] }>("/search", {
        params: { ownerProfileId: profile!.id, limit: 20 },
      }),
    enabled: !!profile,
  });
  const serviceHits = searchResult?.items ?? [];
  const listingQueries = useQueries({
    queries: serviceHits.map((hit) => ({
      queryKey: ["listing", hit.listingId],
      queryFn: () => catalogClient.getListing(hit.listingId),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });
  const services = listingQueries.map((q) => q.data).filter((l): l is CatalogListing => !!l);

  const { data: geocodeResults } = useQuery({
    queryKey: ["geocode", profile?.address],
    queryFn: () => searchPlaces(profile!.address!, 1),
    enabled: !!profile?.address,
    staleTime: 30 * 60_000,
    retry: false,
  });

  const logo = useMediaAsset(profile?.logoMediaAssetId);
  const banner = useMediaAsset(profile?.bannerMediaAssetId);
  const [lightbox, setLightbox] = useState<{
    items: LightboxItem[];
    index: number;
    autoPlay?: boolean;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const name = profile
    ? profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot"
    : "";

  const marker: MapMarker | null = useMemo(() => {
    const g = geocodeResults?.[0];
    if (!g || !profile) return null;
    return { id: profile.id, lat: g.lat, lng: g.lng, label: name, title: name };
  }, [geocodeResults, profile, name]);

  async function handleShare() {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: name, url });
      } catch {
        // user cancelled the native share sheet -- not an error
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission blocked -- silently give up, nothing else we can do
    }
  }

  if (isLoading) {
    return <PageSkeleton />;
  }

  if (isError || !profile) {
    return (
      <AppShell>
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-2 pt-32 text-center">
          <p className="font-display text-xl font-semibold">Tashkilot topilmadi</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Bu sahifa mavjud emas yoki tashkilotning obuna muddati tugagan bo'lishi mumkin.
          </p>
          <Link to="/organizations" className="mt-2 text-sm text-primary hover:underline">
            Tashkilotlar ro'yxatiga qaytish
          </Link>
        </div>
      </AppShell>
    );
  }

  const description =
    profile.description?.uz_latn || profile.description?.ru || profile.description?.en;
  const primaryPhone = profile.contacts?.phones?.[0];
  const primaryEmail = profile.contacts?.emails?.[0];
  const website = profile.contacts?.website;
  const workingHours = profile.contacts?.workingHours;
  const socialLinks = profile.contacts?.socialLinks;
  const promoVideos = profile.promoVideoMediaAssetIds ?? [];
  const portfolioItems = portfolio ?? [];

  const sectorLabel = profile.subCategory
    ? SUB_CATEGORY_LABEL[profile.subCategory]
    : profile.mainCategory
      ? MAIN_CATEGORY_LABEL[profile.mainCategory]
      : null;
  const sectorAccent = profile.mainCategory
    ? MAIN_CATEGORY_ACCENT[profile.mainCategory]
    : undefined;
  const tagline = [PROFILE_TYPE_LABEL[profile.profileType], sectorLabel]
    .filter(Boolean)
    .join(" · ");

  const backTarget =
    profile.mainCategory && profile.subCategory
      ? {
          to: "/organizations/$categorySlug/$subCategorySlug" as const,
          params: {
            categorySlug: MAIN_CATEGORY_SLUG[profile.mainCategory],
            subCategorySlug: SUB_CATEGORY_SLUG[profile.subCategory],
          },
        }
      : profile.mainCategory
        ? {
            to: "/organizations/$categorySlug" as const,
            params: { categorySlug: MAIN_CATEGORY_SLUG[profile.mainCategory] },
          }
        : { to: "/organizations" as const, params: undefined };

  const tenure = tenureLabel(profile.createdAt);
  const stats: { icon: LucideIcon; label: string; value: string; accent?: string }[] = [];
  if (tenure) stats.push({ icon: Calendar, label: "Platformada faoliyat", value: tenure });
  if (portfolioItems.length > 0)
    stats.push({ icon: Layers, label: "Portfolio ishlari", value: String(portfolioItems.length) });
  if (serviceHits.length > 0)
    stats.push({ icon: Package, label: "Faol xizmatlar", value: String(serviceHits.length) });
  if (sectorLabel)
    stats.push({ icon: Sparkles, label: "Yo'nalish", value: sectorLabel, accent: sectorAccent });

  return (
    <AppShell>
      {/* --- Hero: full-bleed banner + overlapping logo card ------------------------------------ */}
      <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6 sm:pt-28">
        <Link
          {...backTarget}
          className="mb-3 inline-flex items-center gap-1 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          <ChevronLeft className="size-4" /> Orqaga
        </Link>

        <motion.div
          initial={{ scale: 1.03, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="relative h-56 w-full overflow-hidden rounded-2xl border border-border bg-muted shadow-soft md:h-80"
        >
          {banner?.url ? (
            <img src={banner.url} alt="" className="size-full object-cover" />
          ) : (
            <div className="gradient-mesh size-full opacity-70" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/35 via-black/0 to-transparent" />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-5 px-1 pb-2 sm:flex-row sm:items-end sm:justify-between sm:px-2"
        >
          <div className="flex items-end gap-4">
            <div className="-mt-12 flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-2xl border-4 border-background bg-white text-primary shadow-md md:-mt-16 md:size-32">
              {logo?.url ? (
                <img src={logo.url} alt="" className="size-full object-cover" />
              ) : (
                <Building2 className="size-9 md:size-11" />
              )}
            </div>
            <div className="pb-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="font-display text-xl font-semibold tracking-tight text-foreground sm:text-2xl lg:text-3xl">
                  {name}
                </h1>
                {profile.badge?.status === "VALID" && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                    <ShieldCheck className="size-3.5" /> Tasdiqlangan
                  </span>
                )}
              </div>
              {tagline && <p className="mt-1 text-sm text-muted-foreground">{tagline}</p>}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
            {primaryPhone && (
              <a
                href={`tel:${primaryPhone.replace(/\s+/g, "")}`}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:flex-none"
              >
                <Phone className="size-4" /> Bog'lanish
              </a>
            )}
            {primaryEmail && (
              <a
                href={`mailto:${primaryEmail}`}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground transition hover:border-primary/40 hover:text-primary sm:flex-none"
              >
                <MessageCircle className="size-4" /> Xabar yuborish
              </a>
            )}
            {website && (
              <a
                href={website}
                target="_blank"
                rel="noreferrer"
                className="flex size-11 shrink-0 items-center justify-center rounded-full border border-border bg-background text-foreground transition hover:border-primary/40 hover:text-primary"
                title="Veb-sayt"
              >
                <Globe className="size-4" />
              </a>
            )}
            <div className="relative">
              <button
                type="button"
                onClick={handleShare}
                className="flex size-11 shrink-0 items-center justify-center rounded-full border border-border bg-background text-foreground transition hover:border-primary/40 hover:text-primary"
                title="Ulashish"
              >
                {copied ? <Check className="size-4" /> : <Link2 className="size-4" />}
              </button>
              <AnimatePresence>
                {copied && (
                  <motion.span
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="absolute -bottom-9 right-0 whitespace-nowrap rounded-full bg-foreground px-2.5 py-1 text-[11px] font-medium text-background shadow-md"
                  >
                    Havola nusxalandi
                  </motion.span>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>
      </section>

      {/* --- About + real metrics band ---------------------------------------------------------- */}
      <section className="border-t border-border py-12">
        <div className="mx-auto max-w-6xl px-6">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <SectionEyebrow>Kompaniya haqida</SectionEyebrow>
              <h2 className="mb-4 font-display text-xl font-semibold text-foreground sm:text-2xl">
                Biz haqimizda
              </h2>
              <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                {description || "Tashkilot haqida ma'lumot hali kiritilmagan."}
              </p>
            </div>
            {stats.length > 0 && (
              <div className="grid grid-cols-2 content-start gap-3">
                {stats.map((s) => (
                  <StatTile key={s.label} {...s} />
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* --- Promo video ---------------------------------------------------------------------- */}
      {promoVideos.length > 0 && (
        <section className="relative border-t border-border bg-card/40 py-10">
          <div className="mx-auto max-w-6xl px-6">
            <SectionEyebrow>Tanishtiruv</SectionEyebrow>
            <h2 className="mb-6 flex items-center gap-2 font-display text-xl font-semibold text-foreground sm:text-2xl">
              <Film className="size-5 text-primary" /> Video taqdimot
            </h2>
            <div className="flex flex-wrap gap-5">
              {promoVideos.map((mediaAssetId, i) => (
                <PromoVideoCard
                  key={mediaAssetId}
                  mediaAssetId={mediaAssetId}
                  onOpen={() =>
                    setLightbox({
                      items: promoVideos.map((id) => ({ mediaAssetId: id })),
                      index: i,
                      autoPlay: true,
                    })
                  }
                />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* --- Services / products grid ---------------------------------------------------------- */}
      <section className="border-t border-border py-14">
        <div className="mx-auto max-w-6xl px-6">
          <SectionEyebrow>Takliflar</SectionEyebrow>
          <h2 className="mb-6 flex items-center gap-2 font-display text-xl font-semibold text-foreground sm:text-2xl">
            <Package className="size-5 text-primary" /> Xizmatlar va mahsulotlar
          </h2>
          {serviceHits.length === 0 ? (
            <EmptyState
              icon={Package}
              title="Hozircha xizmat yoki mahsulot joylashtirilmagan"
              description="Tashkilot yaqin orada o'z xizmat va mahsulotlarini shu yerda e'lon qiladi."
            />
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {services.length > 0
                ? services.map((listing, i) => (
                    <ServiceListingCard key={listing.id} listing={listing} index={i} />
                  ))
                : serviceHits.map((hit, i) => (
                    <motion.div
                      key={hit.listingId}
                      initial={{ opacity: 0, y: 16 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: Math.min(i * 0.05, 0.3) }}
                    >
                      <Skeleton className="h-36 rounded-t-2xl" />
                      <div className="space-y-2 rounded-b-2xl border border-t-0 border-border bg-card p-4">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-3 w-1/2" />
                      </div>
                    </motion.div>
                  ))}
            </div>
          )}
        </div>
      </section>

      {/* --- Portfolio: mobile carousel / desktop 3-col grid ----------------------------------- */}
      <section className="border-t border-border bg-card/40 py-10">
        <div className="mx-auto max-w-6xl px-6">
          <SectionEyebrow>Portfolio</SectionEyebrow>
          <h2 className="mb-6 font-display text-xl font-semibold text-foreground sm:text-2xl">
            Qilgan ishlarimiz
          </h2>
          {portfolioItems.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="Hozircha portfolio qo'shilmagan"
              description="Tashkilot bajargan ishlarining suratlari yaqin orada shu yerda ko'rinadi."
            />
          ) : (
            <PortfolioGalleryLayout
              items={portfolioItems}
              onOpen={(index) => setLightbox({ items: portfolioItems, index })}
            />
          )}
        </div>
      </section>

      <AnimatePresence>
        {lightbox && (
          <MediaLightbox
            items={lightbox.items}
            index={lightbox.index}
            autoPlay={lightbox.autoPlay}
            onClose={() => setLightbox(null)}
            onNavigate={(next) => setLightbox({ ...lightbox, index: next })}
          />
        )}
      </AnimatePresence>

      {/* --- Contact + real interactive map ----------------------------------------------------- */}
      <section className="border-t border-border py-14">
        <div className="mx-auto max-w-6xl px-6">
          <SectionEyebrow>Aloqa</SectionEyebrow>
          <h2 className="mb-6 font-display text-xl font-semibold text-foreground sm:text-2xl">
            Kontaktlar va manzil
          </h2>
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-5 lg:items-start">
            <div className="overflow-hidden rounded-3xl border border-border bg-card shadow-soft lg:col-span-2">
              <div className="space-y-1 p-4">
                {profile.address && (
                  <div className="flex items-start gap-3 rounded-xl px-2 py-2 text-sm text-muted-foreground">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
                      <MapPin className="size-4" />
                    </span>
                    <span className="pt-1">{profile.address}</span>
                  </div>
                )}
                {workingHours && (
                  <div className="flex items-start gap-3 rounded-xl px-2 py-2 text-sm text-muted-foreground">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
                      <Clock className="size-4" />
                    </span>
                    <span className="whitespace-pre-line pt-1">{workingHours}</span>
                  </div>
                )}
                {profile.contacts?.phones?.map((phone) => (
                  <a
                    key={phone}
                    href={`tel:${phone.replace(/\s+/g, "")}`}
                    className="flex items-center gap-3 rounded-xl px-2 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-primary"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
                      <Phone className="size-4" />
                    </span>
                    {phone}
                  </a>
                ))}
                {profile.contacts?.emails?.map((email) => (
                  <a
                    key={email}
                    href={`mailto:${email}`}
                    className="flex items-center gap-3 rounded-xl px-2 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-primary"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
                      <Mail className="size-4" />
                    </span>
                    {email}
                  </a>
                ))}
                {website && (
                  <a
                    href={website}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-3 rounded-xl px-2 py-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-primary"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
                      <Globe className="size-4" />
                    </span>
                    <span className="truncate">{website}</span>
                  </a>
                )}
                {!profile.address &&
                  !workingHours &&
                  !profile.contacts?.phones?.length &&
                  !profile.contacts?.emails?.length &&
                  !website && (
                    <p className="px-2 py-2 text-sm text-muted-foreground">
                      Aloqa ma'lumotlari kiritilmagan.
                    </p>
                  )}
              </div>
              {socialLinks && <CompanySocialLinks links={socialLinks} />}
            </div>

            <div className="lg:col-span-3">
              {marker ? (
                <ListingLocationSection marker={marker} address={profile.address} height="340px" />
              ) : profile.address ? (
                <div className="flex h-[340px] flex-col items-center justify-center gap-2 rounded-3xl border border-dashed border-border bg-card/40 text-center">
                  <MapPin className="size-6 text-muted-foreground" />
                  <p className="max-w-xs text-sm text-muted-foreground">
                    Xarita hozircha yuklanmoqda yoki manzil aniqlanmadi.
                  </p>
                  <a
                    href={`https://yandex.com/maps/?text=${encodeURIComponent(profile.address)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    Yandex xaritalarda ochish
                  </a>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>
    </AppShell>
  );
}
