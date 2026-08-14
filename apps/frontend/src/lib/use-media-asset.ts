import { useEffect, useState } from "react";
import { http } from "@/lib/http";

interface MediaAssetLite {
  url: string | null;
  contentType?: string;
}

/** Resolves a bare `mediaAssetId` reference (the wire shape every module stores — never a
 * resolved URL, see `BusinessProfile.logoMediaAssetId`'s own backend docstring) to its CDN URL
 * via `GET /media/{id}`. Shared by every surface that renders a business-profile logo/banner/
 * portfolio image outside the dashboard edit form's own inline fetches. */
export function useMediaAsset(mediaAssetId: string | null | undefined): MediaAssetLite | null {
  const [asset, setAsset] = useState<MediaAssetLite | null>(null);

  useEffect(() => {
    if (!mediaAssetId) {
      setAsset(null);
      return;
    }
    let cancelled = false;
    http
      .get<MediaAssetLite>(`/media/${mediaAssetId}`)
      .then((a) => {
        if (!cancelled) setAsset(a);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mediaAssetId]);

  return asset;
}
