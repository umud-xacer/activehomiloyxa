import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Film, ImagePlus, Loader2, Plus, Trash2 } from "lucide-react";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { http } from "@/lib/http";
import {
  businessProfilesApi,
  type BusinessProfile,
  type PortfolioItem,
} from "@/lib/business-profiles-client";
import { uploadMedia, mediaSizeError } from "@/lib/media-client";

function PortfolioTile({ item, onRemove }: { item: PortfolioItem; onRemove: () => void }) {
  const [asset, setAsset] = useState<{ url: string | null; contentType: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    http
      .get<{ url: string | null; contentType: string }>(`/media/${item.mediaAssetId}`)
      .then((a) => {
        if (!cancelled) setAsset(a);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [item.mediaAssetId]);

  const video = asset?.contentType?.startsWith("video/");

  return (
    <div className="group relative aspect-square overflow-hidden rounded-2xl border border-border bg-muted">
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video src={asset.url} preload="metadata" className="size-full object-cover" muted />
      ) : (
        <img src={asset.url} alt="" className="size-full object-cover" />
      )}
      {video && (
        <div className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
          <Film className="size-3" /> Video
        </div>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition group-hover:opacity-100 hover:bg-destructive"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  );
}

/** The portfolio upload grid + logic, without any card chrome -- shared by the business-profile
 * edit form (via `PortfolioGallery` below) and the onboarding wizard
 * (`routes/organization/setup.tsx`, which supplies its own step chrome). ADR-0010. */
export function PortfolioFields({
  profile,
  action,
  onItemsChange,
}: {
  profile: BusinessProfile;
  /** Rendered above the grid, next to the upload button -- lets the wizard show its own step
   * label instead of `SectionCard`'s title slot. */
  action?: ReactNode;
  /** The wire `BusinessProfile.portfolio` field is never populated by `GET /business-profiles/
   * {id}` (only the dedicated `listPortfolio` endpoint returns items) -- callers that need to
   * know the live item count (onboarding wizard's "Davom etish" gate, the dashboard's live
   * landing-page preview) must read it from here instead of `profile.portfolio`. */
  onItemsChange?: (items: PortfolioItem[]) => void;
}) {
  const queryClient = useQueryClient();
  const [items, setItemsState] = useState<PortfolioItem[]>(profile.portfolio ?? []);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setItems = (next: PortfolioItem[]) => {
    setItemsState(next);
    onItemsChange?.(next);
  };

  useEffect(() => {
    businessProfilesApi
      .listPortfolio(profile.id)
      .then(setItems)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.id]);

  const refresh = async () => {
    const fresh = await businessProfilesApi.listPortfolio(profile.id);
    setItems(fresh);
    queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const sizeError = mediaSizeError(file);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const uploaded = await uploadMedia(file, "PROFILE_PORTFOLIO");
      await businessProfilesApi.addPortfolioItem(profile.id, {
        mediaAssetId: uploaded.mediaAssetId,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (itemId: string) => {
    setItems(items.filter((i) => i.id !== itemId));
    try {
      await businessProfilesApi.removePortfolioItem(profile.id, itemId);
    } finally {
      refresh();
    }
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        {action}
        <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:shadow-glow">
          {uploading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Plus className="size-3.5" />
          )}
          Fayl qo'shish
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,video/mp4,video/webm"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              handleFile(file);
            }}
          />
        </label>
      </div>
      {error && (
        <p className="mb-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      {items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Hali portfolio elementi yo'q.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((item) => (
            <PortfolioTile key={item.id} item={item} onRemove={() => remove(item.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

/** The edit-form's own card wrapper around `PortfolioFields`. */
export function PortfolioGallery({
  profile,
  onItemsChange,
}: {
  profile: BusinessProfile;
  onItemsChange?: (items: PortfolioItem[]) => void;
}) {
  return (
    <SectionCard
      title="Portfolio galereyasi"
      icon={ImagePlus}
      description="Rasm (JPEG/PNG/WEBP, maks. 1.2 MB) yoki video (MP4/WEBM, maks. 30 MB) qo'shing."
      index={2}
    >
      <PortfolioFields profile={profile} onItemsChange={onItemsChange} />
    </SectionCard>
  );
}
