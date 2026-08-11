/**
 * Shared media-upload client (ADR-0008: images AND video, 1.2 MB / 30 MB caps respectively).
 * Wraps the presigned-upload flow (`POST /media/uploads` -> PUT bytes -> poll `GET /media/{id}`
 * until the async scan/processing worker marks it CLEAN) behind one `uploadMedia()` call, so
 * every feature that needs to attach a photo or video (business-profile portfolio today,
 * listing images elsewhere) can share one implementation instead of re-deriving the polling
 * loop per call site.
 */
import { http } from "@/lib/http";

export const MAX_IMAGE_SIZE_BYTES = 1.2 * 1024 * 1024;
export const MAX_GIF_SIZE_BYTES = 5 * 1024 * 1024;
export const MAX_VIDEO_SIZE_BYTES = 30 * 1024 * 1024;

export type MediaOwnerContextType =
  "LISTING" | "PROFILE_PORTFOLIO" | "VERIFICATION_DOCUMENT" | "BANNER_CREATIVE";

const IMAGE_CONTENT_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const GIF_CONTENT_TYPE = "image/gif";
const VIDEO_CONTENT_TYPES = new Set(["video/mp4", "video/webm"]);

export function isVideoFile(file: File): boolean {
  return VIDEO_CONTENT_TYPES.has(file.type);
}

export function isGifFile(file: File): boolean {
  return file.type === GIF_CONTENT_TYPE;
}

export function isSupportedMediaFile(file: File): boolean {
  return (
    IMAGE_CONTENT_TYPES.has(file.type) || isGifFile(file) || VIDEO_CONTENT_TYPES.has(file.type)
  );
}

/** Client-side pre-check only -- the real cap is enforced server-side (`MediaAsset.initiate`);
 * this just avoids a wasted round trip and gives the user an immediate, specific message. */
export function mediaSizeError(file: File): string | null {
  if (!isSupportedMediaFile(file)) {
    return "Faqat JPEG, PNG, WEBP, GIF rasm yoki MP4, WEBM video fayllar qabul qilinadi.";
  }
  const max = isVideoFile(file)
    ? MAX_VIDEO_SIZE_BYTES
    : isGifFile(file)
      ? MAX_GIF_SIZE_BYTES
      : MAX_IMAGE_SIZE_BYTES;
  if (file.size > max) {
    const maxLabel = isVideoFile(file) ? "30 MB" : isGifFile(file) ? "5 MB" : "1.2 MB";
    return `Fayl juda katta (maksimal ${maxLabel}).`;
  }
  return null;
}

interface MediaUploadTicket {
  mediaAssetId: string;
  uploadUrl: string;
  method: string;
  headers?: Record<string, string>;
  expiresAt: string;
}

interface MediaAssetDto {
  id: string;
  contentType: string;
  url: string | null;
  scanStatus: "PENDING" | "CLEAN" | "QUARANTINED";
  processingStatus: "PENDING" | "COMPLETED" | "FAILED";
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Resolves one already-uploaded media asset's CDN url. `CatalogListing.images` (catalog-client.ts)
 * only carries `mediaAssetId` -- no url -- so any surface that needs to actually render a listing's
 * photos (the listing detail page) has to look each one up individually. Swallows a lookup failure
 * (asset still processing, deleted, etc.) into `null` rather than throwing, since a listing with N
 * images shouldn't have its whole gallery break because one image failed to resolve. */
export async function getMediaAssetUrl(mediaAssetId: string): Promise<string | null> {
  try {
    const asset = await http.get<MediaAssetDto>(`/media/${mediaAssetId}`);
    return asset.url;
  } catch {
    return null;
  }
}

export interface UploadedMedia {
  mediaAssetId: string;
  url: string | null;
  isVideo: boolean;
}

/** Uploads a file and waits (briefly) for the scan/processing worker so the caller can show the
 * real CDN URL immediately. If it's still pending after the timeout, the media asset id is still
 * returned -- the preview just won't be ready until a later refresh (the worker keeps running
 * either way, this call just stops waiting for it). */
export async function uploadMedia(
  file: File,
  ownerContextType: MediaOwnerContextType,
): Promise<UploadedMedia> {
  const sizeError = mediaSizeError(file);
  if (sizeError) throw new Error(sizeError);

  const ticket = await http.post<MediaUploadTicket>("/media/uploads", {
    contentType: file.type,
    sizeBytes: file.size,
    ownerContextType,
  });

  const response = await fetch(ticket.uploadUrl, {
    method: ticket.method || "PUT",
    headers: { "Content-Type": file.type, ...ticket.headers },
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Fayl yuklashda xatolik (status ${response.status})`);
  }

  const video = isVideoFile(file);
  const attempts = video ? 20 : 10;
  const delayMs = video ? 1000 : 700;
  for (let attempt = 0; attempt < attempts; attempt++) {
    await sleep(delayMs);
    const asset = await http.get<MediaAssetDto>(`/media/${ticket.mediaAssetId}`);
    if (asset.scanStatus === "CLEAN" && asset.processingStatus === "COMPLETED") {
      return { mediaAssetId: ticket.mediaAssetId, url: asset.url, isVideo: video };
    }
    if (asset.scanStatus === "QUARANTINED" || asset.processingStatus === "FAILED") {
      throw new Error("Fayl xavfsizlik tekshiruvidan o'tmadi va rad etildi.");
    }
  }
  return { mediaAssetId: ticket.mediaAssetId, url: null, isVideo: video };
}
