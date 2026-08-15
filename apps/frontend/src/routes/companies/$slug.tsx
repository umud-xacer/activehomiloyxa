import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Film,
  Globe,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Navigation,
  Phone,
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

export const Route = createFileRoute("/companies/$slug")({
  head: () => ({ meta: [{ title: "Tashkilot — ActiveHome" }] }),
  component: Page,
});

interface SearchHitLite {
  listingId: string;
  title: string;
  price?: { amount: string; currency: string } | null;
}

/** A few preset ratios cycled by index -- gives the portfolio grid a real masonry look without
 * depending on each image's actual (network-dependent, layout-shifting) intrinsic dimensions. */
const MASONRY_ASPECTS = ["aspect-[4/5]", "aspect-square", "aspect-[4/3]", "aspect-[3/4]"];

function MasonryTile({
  item,
  index,
  onOpen,
}: {
  item: PortfolioItem;
  index: number;
  onOpen: () => void;
}) {
  const asset = useMediaAsset(item.mediaAssetId);
  const video = asset?.contentType?.startsWith("video/");

  return (
    <button
      type="button"
      onClick={onOpen}
      className={`group relative mb-3 block w-full overflow-hidden rounded-2xl border border-border bg-muted ${MASONRY_ASPECTS[index % MASONRY_ASPECTS.length]}`}
      style={{ breakInside: "avoid" }}
    >
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video src={asset.url} preload="metadata" muted className="size-full object-cover" />
      ) : (
        <img
          src={asset.url}
          alt=""
          loading="lazy"
          className="size-full object-cover transition duration-300 group-hover:scale-105"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent opacity-0 transition group-hover:opacity-100" />
      {video && (
        <div className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
          <Film className="size-3" /> Video
        </div>
      )}
    </button>
  );
}

function PortfolioLightbox({
  items,
  index,
  onClose,
  onNavigate,
}: {
  items: PortfolioItem[];
  index: number;
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
      <div
        className="mx-4 flex max-h-[85vh] max-w-4xl items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {!asset?.url ? (
          <Loader2 className="size-8 animate-spin text-white/70" />
        ) : video ? (
          <video src={asset.url} controls autoPlay className="max-h-[85vh] rounded-lg" />
        ) : (
          <img src={asset.url} alt="" className="max-h-[85vh] rounded-lg object-contain" />
        )}
      </div>
    </motion.div>
  );
}

function PromoVideoCard({ mediaAssetId }: { mediaAssetId: string }) {
  const asset = useMediaAsset(mediaAssetId);
  return (
    <div className="aspect-video w-full max-w-sm shrink-0 overflow-hidden rounded-2xl border border-border bg-muted shadow-soft">
      {asset?.url ? (
        <video src={asset.url} preload="metadata" controls className="size-full object-cover" />
      ) : (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      )}
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
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

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
          <Link to="/companies" className="mt-2 text-sm text-primary hover:underline">
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
  const promoVideos = profile.promoVideoMediaAssetIds ?? [];

  return (
    <AppShell>
      {/* --- Hero: banner + overlapping logo card ------------------------------------------ */}
      <section className="relative isolate">
        <div className="h-56 w-full overflow-hidden sm:h-72 lg:h-80">
          {banner?.url ? (
            <img src={banner.url} alt="" className="size-full object-cover" />
          ) : (
            <div className="gradient-mesh size-full opacity-70" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/10 to-transparent" />
        </div>

        <div className="mx-auto max-w-6xl px-6">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="-mt-14 flex flex-col gap-5 sm:-mt-16 sm:flex-row sm:items-end sm:justify-between"
          >
            <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-end">
              <div className="flex size-28 shrink-0 items-center justify-center overflow-hidden rounded-3xl border-4 border-background bg-card text-primary shadow-elevated sm:size-32">
                {logo?.url ? (
                  <img src={logo.url} alt="" className="size-full object-cover" />
                ) : (
                  <Building2 className="size-10" />
                )}
              </div>
              <div className="pb-1">
                <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
                  {name}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-border bg-card px-2.5 py-0.5 text-xs text-muted-foreground">
                    {PROFILE_TYPE_LABEL[profile.profileType]}
                  </span>
                  {profile.badge?.status === "VALID" && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-semibold text-success">
                      <ShieldCheck className="size-3.5" /> Tasdiqlangan
                    </span>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 pb-1">
              {primaryPhone && (
                <a
                  href={`tel:${primaryPhone.replace(/\s+/g, "")}`}
                  className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
                >
                  <Phone className="size-4" /> Qo'ng'iroq qilish
                </a>
              )}
              {primaryEmail && (
                <a
                  href={`mailto:${primaryEmail}`}
                  className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground transition hover:border-primary/40"
                >
                  <MessageCircle className="size-4" /> Xabar yuborish
                </a>
              )}
              {website && (
                <a
                  href={website}
                  target="_blank"
                  rel="noreferrer"
                  className="flex size-11 shrink-0 items-center justify-center rounded-full border border-border bg-card text-foreground transition hover:border-primary/40 hover:text-primary"
                  title="Veb-sayt"
                >
                  <Globe className="size-4" />
                </a>
              )}
            </div>
          </motion.div>
        </div>
      </section>

      {/* --- About + promo video ------------------------------------------------------------ */}
      {(description || promoVideos.length > 0) && (
        <section className="mx-auto max-w-6xl px-6 py-10">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
            {description && (
              <div className={promoVideos.length > 0 ? "lg:col-span-1" : "lg:col-span-3"}>
                <h2 className="font-display text-lg font-semibold text-foreground">
                  Tashkilot haqida
                </h2>
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                  {description}
                </p>
              </div>
            )}
            {promoVideos.length > 0 && (
              <div className={description ? "lg:col-span-2" : "lg:col-span-3"}>
                <h2 className="mb-3 flex items-center gap-2 font-display text-lg font-semibold text-foreground">
                  <Film className="size-4 text-primary" /> Video taqdimot
                </h2>
                <div className="flex flex-wrap gap-4">
                  {promoVideos.map((mediaAssetId) => (
                    <PromoVideoCard key={mediaAssetId} mediaAssetId={mediaAssetId} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* --- Portfolio masonry ---------------------------------------------------------------- */}
      {portfolio && portfolio.length > 0 && (
        <section className="border-t border-border bg-card/30 py-10">
          <div className="mx-auto max-w-6xl px-6">
            <h2 className="mb-4 font-display text-lg font-semibold text-foreground">
              Qilgan ishlarimiz
            </h2>
            <div className="columns-2 gap-3 sm:columns-3 lg:columns-4">
              {portfolio.map((item, i) => (
                <MasonryTile
                  key={item.id}
                  item={item}
                  index={i}
                  onOpen={() => setLightboxIndex(i)}
                />
              ))}
            </div>
          </div>
        </section>
      )}

      <AnimatePresence>
        {lightboxIndex !== null && portfolio && portfolio.length > 0 && (
          <PortfolioLightbox
            items={portfolio}
            index={lightboxIndex}
            onClose={() => setLightboxIndex(null)}
            onNavigate={setLightboxIndex}
          />
        )}
      </AnimatePresence>

      {/* --- Services + sticky contact sidebar ------------------------------------------------ */}
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 px-6 py-12 lg:grid-cols-3 lg:items-start">
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-3xl border border-border bg-card p-6 shadow-soft">
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-foreground">
              <Wrench className="size-4 text-primary" /> Xizmatlar va e'lonlar
            </h2>
            {!services || services.items.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
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
        </div>

        <div className="space-y-4 lg:sticky lg:top-24">
          <div className="rounded-3xl border border-border bg-card p-6 shadow-soft">
            <h2 className="font-display text-base font-semibold text-foreground">Aloqa</h2>
            <div className="mt-4 space-y-3 text-sm text-muted-foreground">
              {profile.address && (
                <div className="flex items-start gap-2">
                  <MapPin className="mt-0.5 size-4 shrink-0" /> {profile.address}
                </div>
              )}
              {profile.contacts?.phones?.map((phone) => (
                <a
                  key={phone}
                  href={`tel:${phone.replace(/\s+/g, "")}`}
                  className="flex items-center gap-2 hover:text-primary"
                >
                  <Phone className="size-4 shrink-0" /> {phone}
                </a>
              ))}
              {profile.contacts?.emails?.map((email) => (
                <a
                  key={email}
                  href={`mailto:${email}`}
                  className="flex items-center gap-2 hover:text-primary"
                >
                  <Mail className="size-4 shrink-0" /> {email}
                </a>
              ))}
              {website && (
                <a
                  href={website}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-2 hover:text-primary"
                >
                  <Globe className="size-4 shrink-0" />
                  <span className="truncate">{website}</span>
                </a>
              )}
              {!profile.address &&
                !profile.contacts?.phones?.length &&
                !profile.contacts?.emails?.length &&
                !website && <p>Aloqa ma'lumotlari kiritilmagan.</p>}
            </div>
            {profile.address && (
              <a
                href={`https://yandex.com/maps/?text=${encodeURIComponent(profile.address)}`}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full border border-border px-4 py-2.5 text-xs font-semibold text-foreground transition hover:border-primary/40 hover:text-primary"
              >
                <Navigation className="size-3.5" /> Xaritada ko'rish
              </a>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
