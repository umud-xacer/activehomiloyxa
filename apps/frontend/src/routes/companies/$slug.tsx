import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Film,
  Globe,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Navigation,
  Phone,
  Play,
  ShieldCheck,
  Wrench,
  X,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type PortfolioItem,
} from "@/lib/business-profiles-client";
import { http } from "@/lib/http";
import { useMediaAsset } from "@/lib/use-media-asset";
import { formatDuration, useVideoDuration } from "@/lib/use-video-duration";
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
  const { data: services } = useQuery({
    queryKey: ["search", "owner-profile", profile?.id],
    queryFn: () =>
      http.get<{ items: SearchHitLite[] }>("/search", {
        params: { ownerProfileId: profile!.id, limit: 20 },
      }),
    enabled: !!profile,
  });

  const logo = useMediaAsset(profile?.logoMediaAssetId);
  const banner = useMediaAsset(profile?.bannerMediaAssetId);
  const [lightbox, setLightbox] = useState<{
    items: LightboxItem[];
    index: number;
    autoPlay?: boolean;
  } | null>(null);

  if (isLoading) {
    return (
      <AppShell>
        <div className="flex min-h-[60vh] items-center justify-center gap-2 pt-32 text-muted-foreground">
          <Loader2 className="size-5 animate-spin" /> Yuklanmoqda…
        </div>
      </AppShell>
    );
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

  const name = profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
  const description =
    profile.description?.uz_latn || profile.description?.ru || profile.description?.en;
  const primaryPhone = profile.contacts?.phones?.[0];
  const primaryEmail = profile.contacts?.emails?.[0];
  const website = profile.contacts?.website;
  const workingHours = profile.contacts?.workingHours;
  const socialLinks = profile.contacts?.socialLinks;
  const promoVideos = profile.promoVideoMediaAssetIds ?? [];
  const portfolioItems = portfolio ?? [];

  return (
    <AppShell>
      {/* --- Hero: rounded banner + overlapping logo card -------------------------------- */}
      <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6 sm:pt-28">
        <motion.div
          initial={{ scale: 1.03, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="relative h-48 w-full overflow-hidden rounded-2xl border border-border bg-muted shadow-soft md:h-64"
        >
          {banner?.url ? (
            <img src={banner.url} alt="" className="size-full object-cover" />
          ) : (
            <div className="gradient-mesh size-full opacity-70" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/25 via-transparent to-transparent" />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-5 px-1 pb-2 sm:flex-row sm:items-end sm:justify-between sm:px-2"
        >
          <div className="flex items-end gap-4">
            <div className="-mt-12 flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-2xl border-4 border-white bg-white text-primary shadow-md md:-mt-16 md:size-32">
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
              <p className="mt-1 text-sm text-muted-foreground">
                {PROFILE_TYPE_LABEL[profile.profileType]}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
            {primaryPhone && (
              <a
                href={`tel:${primaryPhone.replace(/\s+/g, "")}`}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:flex-none"
              >
                <Phone className="size-4" /> Qo'ng'iroq qilish
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
          </div>
        </motion.div>

        {description && (
          <p className="max-w-2xl px-1 pb-8 pt-2 text-sm leading-relaxed text-muted-foreground sm:px-2">
            {description}
          </p>
        )}
      </section>

      {/* --- Promo video ---------------------------------------------------------------------- */}
      {promoVideos.length > 0 && (
        <section className="relative mx-auto max-w-6xl px-6 py-10">
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
        </section>
      )}

      {/* --- Portfolio: mobile carousel / desktop 3-col grid ----------------------------------- */}
      {portfolioItems.length > 0 && (
        <section className="border-t border-border bg-card/40 py-10">
          <div className="mx-auto max-w-6xl px-6">
            <SectionEyebrow>Portfolio</SectionEyebrow>
            <h2 className="mb-6 font-display text-xl font-semibold text-foreground sm:text-2xl">
              Qilgan ishlarimiz
            </h2>
            <PortfolioGalleryLayout
              items={portfolioItems}
              onOpen={(index) => setLightbox({ items: portfolioItems, index })}
            />
          </div>
        </section>
      )}

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

      {/* --- Services + sticky contact sidebar ------------------------------------------------ */}
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-6 py-14 lg:grid-cols-3 lg:items-start">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-6 lg:col-span-2"
        >
          <div className="rounded-3xl border border-border bg-card p-6 shadow-soft sm:p-7">
            <h2 className="flex items-center gap-2.5 font-display text-lg font-semibold text-foreground">
              <span className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Wrench className="size-4" />
              </span>
              Xizmatlar va e'lonlar
            </h2>
            {!services || services.items.length === 0 ? (
              <p className="mt-4 text-sm text-muted-foreground">
                Hozircha e'lon joylashtirilmagan.
              </p>
            ) : (
              <ul className="mt-4 divide-y divide-border/70">
                {services.items.map((item) => (
                  <li key={item.listingId} className="flex items-center justify-between gap-4 py-3">
                    <span className="text-sm font-medium text-foreground">{item.title}</span>
                    {item.price && (
                      <span className="text-sm text-muted-foreground">
                        {Number(item.price.amount).toLocaleString("uz-UZ")} {item.price.currency}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.45, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-4 lg:sticky lg:top-24"
        >
          <div className="overflow-hidden rounded-3xl border border-border bg-card shadow-soft">
            <div className="border-b border-border/70 bg-gradient-to-br from-primary/5 to-transparent px-6 py-4">
              <h2 className="font-display text-base font-semibold text-foreground">Aloqa</h2>
            </div>
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
            {profile.address && (
              <div className="px-4 pb-4">
                <a
                  href={`https://yandex.com/maps/?text=${encodeURIComponent(profile.address)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex w-full items-center justify-center gap-2 rounded-full border border-border px-4 py-2.5 text-xs font-semibold text-foreground transition hover:border-primary/40 hover:text-primary"
                >
                  <Navigation className="size-3.5" /> Xaritada ko'rish
                </a>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </AppShell>
  );
}
