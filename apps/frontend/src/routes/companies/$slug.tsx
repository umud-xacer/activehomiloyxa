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
    <motion.button
      type="button"
      onClick={onOpen}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className={`group relative mb-3 block w-full overflow-hidden rounded-2xl border border-border bg-muted shadow-soft transition-shadow duration-300 hover:shadow-elevated ${MASONRY_ASPECTS[index % MASONRY_ASPECTS.length]}`}
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
      <span className="absolute left-4 top-4 rounded-full bg-white/10 px-3 py-1.5 text-xs font-medium text-white/80">
        {index + 1} / {items.length}
      </span>
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
            autoPlay
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

function PromoVideoCard({ mediaAssetId }: { mediaAssetId: string }) {
  const asset = useMediaAsset(mediaAssetId);
  return (
    <div className="aspect-video w-full max-w-sm shrink-0 overflow-hidden rounded-2xl border border-border bg-muted shadow-soft transition-shadow duration-300 hover:shadow-elevated">
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

function SectionEyebrow({ children }: { children: string }) {
  return (
    <div className="mb-2 inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-primary">
      <span className="h-px w-5 bg-primary/50" /> {children}
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
      {/* --- Hero: cover photo + floating glass profile card -------------------------------- */}
      <section className="relative isolate">
        <div className="h-64 w-full overflow-hidden sm:h-80 lg:h-[26rem]">
          {banner?.url ? (
            <motion.img
              initial={{ scale: 1.08, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
              src={banner.url}
              alt=""
              className="size-full object-cover"
            />
          ) : (
            <div className="gradient-mesh size-full opacity-70" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/20 to-black/10" />
        </div>

        <div className="mx-auto max-w-6xl px-6">
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            className="-mt-20 rounded-[2rem] border border-border/70 bg-card/95 p-6 shadow-elevated backdrop-blur-xl sm:-mt-24 sm:p-8"
          >
            <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
              <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-end">
                <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-3xl border-4 border-card bg-card text-primary shadow-elevated sm:size-28 sm:-mt-16">
                  {logo?.url ? (
                    <img src={logo.url} alt="" className="size-full object-cover" />
                  ) : (
                    <Building2 className="size-9" />
                  )}
                </div>
                <div>
                  <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">
                    {name}
                  </h1>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-border bg-background/60 px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
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

              <div className="flex flex-wrap items-center gap-2">
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
                    className="inline-flex items-center gap-2 rounded-full border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground transition hover:border-primary/40 hover:text-primary"
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
            </div>

            {description && (
              <p className="mt-6 max-w-2xl border-t border-border/60 pt-5 text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}
          </motion.div>
        </div>
      </section>

      {/* --- Promo video ---------------------------------------------------------------------- */}
      {promoVideos.length > 0 && (
        <section className="relative mx-auto max-w-6xl px-6 py-14">
          <div className="gradient-mesh pointer-events-none absolute inset-x-0 top-0 -z-10 h-full opacity-10" />
          <SectionEyebrow>Tanishtiruv</SectionEyebrow>
          <h2 className="mb-6 flex items-center gap-2 font-display text-xl font-semibold text-foreground sm:text-2xl">
            <Film className="size-5 text-primary" /> Video taqdimot
          </h2>
          <div className="flex flex-wrap gap-5">
            {promoVideos.map((mediaAssetId) => (
              <PromoVideoCard key={mediaAssetId} mediaAssetId={mediaAssetId} />
            ))}
          </div>
        </section>
      )}

      {/* --- Portfolio masonry ---------------------------------------------------------------- */}
      {portfolio && portfolio.length > 0 && (
        <section className="border-t border-border bg-card/40 py-14">
          <div className="mx-auto max-w-6xl px-6">
            <SectionEyebrow>Portfolio</SectionEyebrow>
            <h2 className="mb-6 font-display text-xl font-semibold text-foreground sm:text-2xl">
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
                !profile.contacts?.phones?.length &&
                !profile.contacts?.emails?.length &&
                !website && (
                  <p className="px-2 py-2 text-sm text-muted-foreground">
                    Aloqa ma'lumotlari kiritilmagan.
                  </p>
                )}
            </div>
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
