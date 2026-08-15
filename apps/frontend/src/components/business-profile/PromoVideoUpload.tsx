import { useState } from "react";
import { Film, Loader2, Plus, Trash2 } from "lucide-react";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { businessProfilesApi, type BusinessProfile } from "@/lib/business-profiles-client";
import { uploadMedia, mediaSizeError } from "@/lib/media-client";
import { useMediaAsset } from "@/lib/use-media-asset";

/** Mirrors the backend's own hard cap (`profiles.domain.business_profile.MAX_PROMO_VIDEOS` /
 * `profiles.application.profile_use_cases.MAX_PROMO_VIDEO_DURATION_SECONDS`) -- this is the
 * fast, specific, pre-upload UX gate; the server re-validates both independently (never merely
 * trusts the client), see `business-profiles-client.ts::addPromoVideo`'s own docstring. */
const MAX_PROMO_VIDEOS = 2;
const MAX_PROMO_VIDEO_DURATION_SECONDS = 30;
const PROMO_VIDEO_CONTENT_TYPES = new Set(["video/mp4", "video/webm"]);

function readVideoDurationSeconds(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Video faylni o'qib bo'lmadi."));
    };
    video.src = url;
  });
}

function PromoVideoTile({
  profileId,
  mediaAssetId,
  onRemoved,
}: {
  profileId: string;
  mediaAssetId: string;
  onRemoved: () => void;
}) {
  const asset = useMediaAsset(mediaAssetId);
  const [removing, setRemoving] = useState(false);

  const remove = async () => {
    setRemoving(true);
    try {
      await businessProfilesApi.removePromoVideo(profileId, mediaAssetId);
      onRemoved();
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="group relative aspect-video overflow-hidden rounded-2xl border border-border bg-muted">
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <video src={asset.url} preload="metadata" controls className="size-full object-cover" />
      )}
      <button
        type="button"
        onClick={remove}
        disabled={removing}
        className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition group-hover:opacity-100 hover:bg-destructive disabled:opacity-100"
      >
        {removing ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Trash2 className="size-3.5" />
        )}
      </button>
    </div>
  );
}

/** The promo-video upload grid + logic, without any card chrome -- shared by the business-profile
 * edit form (via `PromoVideoSection` below) and the onboarding wizard's Portfolio step
 * (`routes/organization/setup.tsx`, which supplies its own step chrome). Landing-page
 * promo-video business rule (additive, site-owner spec): at most 2 videos, each 30 seconds or
 * shorter -- checked client-side before upload (fast, specific error) and re-checked server-side
 * on attach (authoritative; see `ProfileUseCases.add_promo_video`'s own docstring for why an
 * unreadable duration fails closed there). */
export function PromoVideoFields({
  profile,
  onIdsChange,
}: {
  profile: BusinessProfile;
  onIdsChange?: (ids: string[]) => void;
}) {
  const [ids, setIdsState] = useState<string[]>(profile.promoVideoMediaAssetIds ?? []);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setIds = (next: string[]) => {
    setIdsState(next);
    onIdsChange?.(next);
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (ids.length >= MAX_PROMO_VIDEOS) {
      setError(`Ko'pi bilan ${MAX_PROMO_VIDEOS} ta promo video yuklash mumkin.`);
      return;
    }
    if (!PROMO_VIDEO_CONTENT_TYPES.has(file.type)) {
      setError("Faqat MP4 yoki WEBM formatidagi video qabul qilinadi.");
      return;
    }
    const sizeError = mediaSizeError(file);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setUploading(true);
    try {
      const duration = await readVideoDurationSeconds(file);
      if (duration > MAX_PROMO_VIDEO_DURATION_SECONDS) {
        setError(
          `Video davomiyligi ${MAX_PROMO_VIDEO_DURATION_SECONDS} soniyadan oshmasligi kerak ` +
            `(bu video: ${Math.round(duration)} soniya).`,
        );
        return;
      }
      const uploaded = await uploadMedia(file, "PROFILE_PORTFOLIO");
      const updated = await businessProfilesApi.addPromoVideo(profile.id, uploaded.mediaAssetId);
      setIds(updated.promoVideoMediaAssetIds ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Video yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          Ko'pi bilan {MAX_PROMO_VIDEOS} ta, har biri {MAX_PROMO_VIDEO_DURATION_SECONDS}{" "}
          soniyagacha.
        </p>
        {ids.length < MAX_PROMO_VIDEOS && (
          <label className="ml-auto inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:shadow-glow">
            {uploading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Plus className="size-3.5" />
            )}
            Video qo'shish
            <input
              type="file"
              accept="video/mp4,video/webm"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                handleFile(file);
              }}
            />
          </label>
        )}
      </div>
      {error && (
        <p className="mb-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      {ids.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Hali promo video yo'q.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {ids.map((id) => (
            <PromoVideoTile
              key={id}
              profileId={profile.id}
              mediaAssetId={id}
              onRemoved={() => setIds(ids.filter((existing) => existing !== id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** The edit-form's own card wrapper around `PromoVideoFields`. */
export function PromoVideoSection({
  profile,
  onIdsChange,
}: {
  profile: BusinessProfile;
  onIdsChange?: (ids: string[]) => void;
}) {
  return (
    <SectionCard
      title="Promo videolar"
      icon={Film}
      description="Kompaniyangiz haqida qisqa (maks. 30 soniya) tanishtiruv videolar."
      index={3}
    >
      <PromoVideoFields profile={profile} onIdsChange={onIdsChange} />
    </SectionCard>
  );
}
