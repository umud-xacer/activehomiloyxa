import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Image as ImageIcon, Loader2 } from "lucide-react";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { ApiError, http } from "@/lib/http";
import { businessProfilesApi, type BusinessProfile } from "@/lib/business-profiles-client";
import { uploadMedia, mediaSizeError } from "@/lib/media-client";

function BrandingTile({
  label,
  mediaAssetId,
  uploading,
  onUpload,
  onRemove,
}: {
  label: string;
  mediaAssetId?: string | null;
  uploading: boolean;
  onUpload: (file: File | undefined) => void;
  onRemove: () => void;
}) {
  const [asset, setAsset] = useState<{ url: string | null } | null>(null);

  useEffect(() => {
    if (!mediaAssetId) {
      setAsset(null);
      return;
    }
    let cancelled = false;
    http
      .get<{ url: string | null }>(`/media/${mediaAssetId}`)
      .then((a) => {
        if (!cancelled) setAsset(a);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mediaAssetId]);

  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-1.5 flex items-center gap-3">
        <div className="flex h-20 w-32 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border bg-muted">
          {uploading ? (
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          ) : asset?.url ? (
            <img src={asset.url} alt="" className="size-full object-cover" />
          ) : (
            <ImageIcon className="size-5 text-muted-foreground" />
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted">
            Rasm tanlash
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                onUpload(file);
              }}
            />
          </label>
          {mediaAssetId && (
            <button
              type="button"
              onClick={onRemove}
              className="text-left text-xs text-muted-foreground hover:text-destructive"
            >
              O'chirish
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** The logo/banner upload grid, without any card chrome -- shared by the business-profile edit
 * form (via `BrandingSection` below) and the onboarding wizard (`routes/organization/setup.tsx`,
 * which supplies its own step chrome). ADR-0010. */
export function BrandingFields({
  profile,
  onSaved,
}: {
  profile: BusinessProfile;
  onSaved?: () => void;
}) {
  const queryClient = useQueryClient();
  const [uploadingField, setUploadingField] = useState<"logo" | "banner" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set = async (field: "logo" | "banner", mediaAssetId: string | null) => {
    try {
      await businessProfilesApi.updateBranding(profile.id, {
        logoMediaAssetId: field === "logo" ? mediaAssetId : profile.logoMediaAssetId,
        bannerMediaAssetId: field === "banner" ? mediaAssetId : profile.bannerMediaAssetId,
      });
      await queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
      onSaved?.();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi.");
    }
  };

  const handleUpload = async (field: "logo" | "banner", file: File | undefined) => {
    if (!file) return;
    const sizeError = mediaSizeError(file);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setError(null);
    setUploadingField(field);
    try {
      const uploaded = await uploadMedia(file, "PROFILE_PORTFOLIO");
      await set(field, uploaded.mediaAssetId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklab bo'lmadi.");
    } finally {
      setUploadingField(null);
    }
  };

  return (
    <>
      {error && (
        <p className="mb-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <BrandingTile
          label="Logotip"
          mediaAssetId={profile.logoMediaAssetId}
          uploading={uploadingField === "logo"}
          onUpload={(f) => handleUpload("logo", f)}
          onRemove={() => set("logo", null)}
        />
        <BrandingTile
          label="Muqova rasmi (banner)"
          mediaAssetId={profile.bannerMediaAssetId}
          uploading={uploadingField === "banner"}
          onUpload={(f) => handleUpload("banner", f)}
          onRemove={() => set("banner", null)}
        />
      </div>
    </>
  );
}

/** The edit-form's own card wrapper around `BrandingFields`. */
export function BrandingSection({ profile }: { profile: BusinessProfile }) {
  return (
    <SectionCard
      title="Logotip va muqova rasmi"
      icon={ImageIcon}
      description="Landing page sarlavhasida shu rasmlar ko'rsatiladi."
      index={1}
    >
      <BrandingFields profile={profile} />
    </SectionCard>
  );
}
