import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Building2,
  Film,
  Globe,
  Loader2,
  Mail,
  MapPin,
  Phone,
  ShieldCheck,
  Wrench,
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

function PortfolioSlide({ item }: { item: PortfolioItem }) {
  const asset = useMediaAsset(item.mediaAssetId);
  const video = asset?.contentType?.startsWith("video/");

  return (
    <div className="relative aspect-square w-40 shrink-0 snap-start overflow-hidden rounded-2xl border border-border bg-muted sm:w-56">
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video src={asset.url} preload="metadata" className="size-full object-cover" muted />
      ) : (
        <img src={asset.url} alt="" className="size-full object-cover" loading="lazy" />
      )}
      {video && (
        <div className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
          <Film className="size-3" /> Video
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

  return (
    <AppShell>
      <section className="relative isolate overflow-hidden border-b border-border pt-24 pb-16">
        <div className="absolute inset-0 -z-10">
          {banner?.url ? (
            <img src={banner.url} alt="" className="size-full object-cover" />
          ) : (
            <div className="gradient-mesh size-full opacity-60" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/85 to-background/40" />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto max-w-5xl px-6"
        >
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border bg-card text-primary shadow-soft">
              {logo?.url ? (
                <img src={logo.url} alt="" className="size-full object-cover" />
              ) : (
                <Building2 className="size-7" />
              )}
            </div>
            <div>
              <h1 className="font-display text-3xl font-semibold tracking-tight">{name}</h1>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-border bg-background/60 px-2.5 py-0.5 text-xs text-muted-foreground">
                  {PROFILE_TYPE_LABEL[profile.profileType]}
                </span>
                {profile.badge?.status === "VALID" && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-semibold text-success">
                    <ShieldCheck className="size-3.5" /> Tasdiqlangan
                  </span>
                )}
              </div>
            </div>
            {primaryPhone && (
              <a
                href={`tel:${primaryPhone.replace(/\s+/g, "")}`}
                className="ml-auto inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
              >
                <Phone className="size-4" /> Qo'ng'iroq qilish
              </a>
            )}
          </div>
          {description && (
            <p className="mt-6 max-w-2xl text-sm text-muted-foreground">{description}</p>
          )}
        </motion.div>
      </section>

      {portfolio && portfolio.length > 0 && (
        <section className="border-b border-border bg-card/30 py-8">
          <div className="mx-auto max-w-5xl px-6">
            <h2 className="mb-4 font-display text-base font-semibold text-foreground">
              Qilgan ishlarimiz
            </h2>
            <div className="flex snap-x gap-3 overflow-x-auto pb-2">
              {portfolio.map((item) => (
                <PortfolioSlide key={item.id} item={item} />
              ))}
            </div>
          </div>
        </section>
      )}

      <div className="mx-auto grid max-w-5xl grid-cols-1 gap-8 px-6 py-12 lg:grid-cols-3">
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

        <div className="space-y-4">
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
                <div key={email} className="flex items-center gap-2">
                  <Mail className="size-4 shrink-0" /> {email}
                </div>
              ))}
              {profile.contacts?.website && (
                <div className="flex items-center gap-2">
                  <Globe className="size-4 shrink-0" />
                  <a
                    href={profile.contacts.website}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:text-primary"
                  >
                    {profile.contacts.website}
                  </a>
                </div>
              )}
              {!profile.address &&
                !profile.contacts?.phones?.length &&
                !profile.contacts?.emails?.length &&
                !profile.contacts?.website && <p>Aloqa ma'lumotlari kiritilmagan.</p>}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
