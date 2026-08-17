import { useEffect, useState } from "react";

/** Formats a seconds count as "0:30"/"1:05" for a video preview-card duration badge. */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

/** Reads a remote video's duration client-side (same `loadedmetadata` technique as
 * `PromoVideoUpload.tsx`'s pre-upload `readVideoDurationSeconds`, just against an already-hosted
 * URL instead of a local `File`) — no server-side duration metadata exists for media assets
 * (ADR-0008's video support does zero server-side processing), so this is the only source. */
export function useVideoDuration(url: string | null | undefined): number | null {
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    setSeconds(null);
    if (!url) return;
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    const onLoaded = () => {
      if (Number.isFinite(video.duration)) setSeconds(video.duration);
    };
    video.addEventListener("loadedmetadata", onLoaded);
    video.src = url;
    return () => {
      video.removeEventListener("loadedmetadata", onLoaded);
      video.src = "";
    };
  }, [url]);

  return seconds;
}
