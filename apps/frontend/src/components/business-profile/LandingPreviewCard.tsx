import { useState } from "react";
import { Link } from "@tanstack/react-router";
import {
  Building2,
  Check,
  Clock,
  Copy,
  ExternalLink,
  Film,
  Globe,
  Loader2,
  MapPin,
  Phone,
  ShieldCheck,
} from "lucide-react";
import {
  MAIN_CATEGORY_LABEL,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
  type MainCategory,
  type PortfolioItem,
} from "@/lib/business-profiles-client";
import { useMediaAsset } from "@/lib/use-media-asset";

export interface ProfileDraft {
  name: string;
  description: string;
  address: string;
  phones: string[];
  emails: string[];
  website: string;
  workingHours: string;
  mainCategory: MainCategory | "";
  socialTelegram: string;
  socialInstagram: string;
  socialFacebook: string;
}

function PreviewThumb({ item }: { item: PortfolioItem }) {
  const asset = useMediaAsset(item.mediaAssetId);
  const video = asset?.contentType?.startsWith("video/");

  return (
    <div className="relative size-12 shrink-0 overflow-hidden rounded-lg border border-border bg-muted">
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-3 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video src={asset.url} preload="metadata" className="size-full object-cover" muted />
      ) : (
        <img src={asset.url} alt="" className="size-full object-cover" />
      )}
      {video && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30">
          <Film className="size-3 text-white" />
        </div>
      )}
    </div>
  );
}

/** A live, self-updating mockup of `routes/companies/$slug.tsx` (the real public landing page)
 * rendered right next to the edit form — reflects unsaved text edits (`draft`) instantly and
 * saved media/portfolio state (`profile`, refetched after every upload) so the owner sees their
 * landing page "come together" as they fill the form in, not just after saving. */
export function LandingPreviewCard({
  profile,
  draft,
  portfolio,
}: {
  profile: BusinessProfile;
  draft: ProfileDraft;
  /** `BusinessProfile.portfolio` is never populated by the profile-read endpoint -- the caller
   * must supply the live list (e.g. from `PortfolioGallery`'s `onItemsChange`) instead of
   * `profile.portfolio`, or this always renders as empty. */
  portfolio: PortfolioItem[];
}) {
  const logo = useMediaAsset(profile.logoMediaAssetId);
  const banner = useMediaAsset(profile.bannerMediaAssetId);
  const publicSlug = profile.slug || profile.id;
  const [copied, setCopied] = useState(false);

  const name = draft.name.trim() || "Kompaniya nomi";
  const description = draft.description.trim();
  const primaryPhone = draft.phones.find((p) => p.trim());

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/companies/${publicSlug}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission denied — silently no-op, the "Nusxalash" button just won't confirm
    }
  };

  return (
    <div className="overflow-hidden rounded-3xl border border-border bg-card shadow-elevated">
      <div className="flex items-center gap-1.5 border-b border-border/70 bg-muted/50 px-4 py-2.5">
        <span className="size-2 rounded-full bg-destructive/30" />
        <span className="size-2 rounded-full bg-warning/30" />
        <span className="size-2 rounded-full bg-success/30" />
        <span className="ml-2 truncate rounded-full bg-background px-2.5 py-1 text-[10px] font-medium text-muted-foreground">
          activehome.uz/companies/{publicSlug}
        </span>
      </div>

      <div className="relative h-24 overflow-hidden">
        {banner?.url ? (
          <img src={banner.url} alt="" className="size-full object-cover" />
        ) : (
          <div className="gradient-mesh size-full opacity-70" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-card via-card/30 to-transparent" />
      </div>

      <div className="-mt-8 px-5">
        <div className="flex size-14 items-center justify-center overflow-hidden rounded-2xl border-4 border-card bg-card text-primary shadow-soft">
          {logo?.url ? (
            <img src={logo.url} alt="" className="size-full object-cover" />
          ) : (
            <Building2 className="size-6" />
          )}
        </div>
      </div>

      <div className="space-y-4 px-5 pb-5 pt-3">
        <div>
          <p className="truncate font-display text-base font-semibold leading-tight text-foreground">
            {name}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] text-muted-foreground">
              {PROFILE_TYPE_LABEL[profile.profileType]}
            </span>
            {draft.mainCategory && (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                {MAIN_CATEGORY_LABEL[draft.mainCategory]}
              </span>
            )}
            {profile.badge?.status === "VALID" && (
              <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success">
                <ShieldCheck className="size-3" /> Tasdiqlangan
              </span>
            )}
          </div>
        </div>

        {description && (
          <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}

        {portfolio.length > 0 ? (
          <div className="flex gap-1.5">
            {portfolio.slice(0, 4).map((item) => (
              <PreviewThumb key={item.id} item={item} />
            ))}
            {portfolio.length > 4 && (
              <div className="flex size-12 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-[10px] font-medium text-muted-foreground">
                +{portfolio.length - 4}
              </div>
            )}
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground/70">
            Portfolio bo'limiga rasm/video qo'shsangiz, shu yerda ko'rinadi.
          </p>
        )}

        <div className="space-y-1.5 text-[11px] text-muted-foreground">
          {draft.address.trim() && (
            <div className="flex items-center gap-1.5">
              <MapPin className="size-3 shrink-0" />
              <span className="truncate">{draft.address}</span>
            </div>
          )}
          {primaryPhone && (
            <div className="flex items-center gap-1.5">
              <Phone className="size-3 shrink-0" /> {primaryPhone}
            </div>
          )}
          {draft.website.trim() && (
            <div className="flex items-center gap-1.5">
              <Globe className="size-3 shrink-0" />
              <span className="truncate">{draft.website}</span>
            </div>
          )}
          {draft.workingHours.trim() && (
            <div className="flex items-center gap-1.5">
              <Clock className="size-3 shrink-0" />
              <span className="truncate">{draft.workingHours}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 border-t border-border/70 pt-4">
          <Link
            to="/companies/$slug"
            params={{ slug: publicSlug }}
            target="_blank"
            className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground transition hover:shadow-glow"
          >
            <ExternalLink className="size-3.5" /> Jonli ko'rish
          </Link>
          <button
            type="button"
            onClick={copyLink}
            title="Havolani nusxalash"
            className="inline-flex items-center justify-center gap-1.5 rounded-full border border-border px-3 py-2 text-xs font-medium text-foreground transition hover:bg-muted"
          >
            {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
