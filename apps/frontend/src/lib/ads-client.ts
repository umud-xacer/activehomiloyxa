/**
 * API client for banner campaign management (BC-09 Ads, `/admin/campaigns*`). A campaign
 * references its placement slot, creative, and billing entitlement by identifier only (the
 * contract's own `createCampaign` description) — this client does not resolve or validate those
 * identifiers, it just carries them through to the backend, which enforces I-20/I-21 itself.
 */
import { http, ApiError } from "@/lib/http";

export type CampaignStatus = "DRAFT" | "SCHEDULED" | "RUNNING" | "PAUSED" | "ENDED";

export interface BannerTargeting {
  categoryIds?: string[];
  geo?: string | null;
  languages?: Array<"uz_latn" | "uz_cyrl" | "ru" | "en">;
}

export interface BannerCampaign {
  id: string;
  slotKey: string;
  creativeMediaAssetId: string;
  entitlementId: string;
  scheduleStart: string;
  scheduleEnd: string;
  priority: number;
  targeting: BannerTargeting;
  status: CampaignStatus;
  createdAt?: string;
  updatedAt?: string;
  targetUrl?: string | null;
}

export interface BannerCampaignCreateInput {
  slotKey: string;
  creativeMediaAssetId: string;
  /** Omitted/null auto-provisions an owner-direct-placement entitlement server-side -- only
   * needed when binding to a real billing `BANNER_SLOT_BOOKING` order. */
  entitlementId?: string | null;
  scheduleStart: string;
  scheduleEnd: string;
  priority: number;
  targeting?: BannerTargeting;
  targetUrl?: string | null;
}

export type BannerCampaignUpdateInput = Partial<Omit<BannerCampaignCreateInput, "slotKey">>;

export async function listCampaigns(params?: {
  status?: CampaignStatus;
  slotKey?: string;
}): Promise<BannerCampaign[]> {
  const { items } = await http.get<{ items: BannerCampaign[] }>("/admin/campaigns", {
    params: { ...params, limit: 100 },
  });
  return items;
}

export async function getCampaign(campaignId: string): Promise<BannerCampaign> {
  return http.get<BannerCampaign>(`/admin/campaigns/${campaignId}`);
}

export async function createCampaign(input: BannerCampaignCreateInput): Promise<BannerCampaign> {
  return http.post<BannerCampaign>("/admin/campaigns", input, { idempotent: true });
}

export async function updateCampaign(
  campaignId: string,
  input: BannerCampaignUpdateInput,
): Promise<BannerCampaign> {
  return http.patch<BannerCampaign>(`/admin/campaigns/${campaignId}`, input);
}

export async function scheduleCampaign(campaignId: string): Promise<BannerCampaign> {
  return http.post<BannerCampaign>(`/admin/campaigns/${campaignId}/schedule`, undefined, {
    idempotent: true,
  });
}

export async function pauseCampaign(campaignId: string): Promise<BannerCampaign> {
  return http.post<BannerCampaign>(`/admin/campaigns/${campaignId}/pause`, undefined, {
    idempotent: true,
  });
}

export async function resumeCampaign(campaignId: string): Promise<BannerCampaign> {
  return http.post<BannerCampaign>(`/admin/campaigns/${campaignId}/resume`, undefined, {
    idempotent: true,
  });
}

export async function endCampaign(campaignId: string): Promise<BannerCampaign> {
  return http.post<BannerCampaign>(`/admin/campaigns/${campaignId}/end`, undefined, {
    idempotent: true,
  });
}

// -- /banners/* (public serving/engagement, anonymous-safe) --------------------------------------

export interface BannerServeView {
  campaignId: string;
  slotKey: string;
  creativeMediaAssetId: string;
  targetUrl?: string | null;
}

const RETRY_DELAYS_MS = [400, 1000, 2000, 4000];

/** `GET /banners/serve` -- 204 (no eligible campaign for this slot right now) surfaces as `null`,
 * never an error, so a caller can render nothing rather than an error state for the ordinary
 * "no active campaign" case.
 *
 * Retries with backoff on 503 specifically: live production testing traced this to something
 * edge-layer (Cloudflare) 503ing this exact call from a real page load with total reliability --
 * confirmed the origin answers every one of these with a clean 204 every single time (direct
 * uvicorn access-log correlation during a live repro), and confirmed the identical request
 * (same path, same query, same headers, same credentials) always succeeds when re-issued a
 * moment later. Neither request staggering nor waiting for the page to go fully idle changed the
 * outcome, so rather than chase the exact edge-side trigger further, retry with backoff until
 * one attempt lands outside whatever window it is. A 503 is transient by definition, so retrying
 * is the correct response regardless of the precise cause. */
export async function serveBanner(slotKey: string): Promise<BannerServeView | null> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await http.get<BannerServeView | null>("/banners/serve", { params: { slotKey } });
    } catch (err) {
      const delay = RETRY_DELAYS_MS[attempt];
      if (!(err instanceof ApiError) || err.status !== 503 || delay === undefined) throw err;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}

/** `GET /banners/serve-many` -- carousel/native-variant sibling of `serveBanner`: every eligible
 * campaign for the slot, up to `limit`, in the same priority order `serveBanner` itself picks its
 * single winner from. Never a `null`/204 case -- an empty result is just `{ items: [] }`. Same
 * 503-retry discipline as `serveBanner` (see its own docstring for why). */
export async function serveBanners(
  slotKey: string,
  limit = 6,
): Promise<{ items: BannerServeView[] }> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await http.get<{ items: BannerServeView[] }>("/banners/serve-many", {
        params: { slotKey, limit },
      });
    } catch (err) {
      const delay = RETRY_DELAYS_MS[attempt];
      if (!(err instanceof ApiError) || err.status !== 503 || delay === undefined) throw err;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}

/** Fire-and-forget engagement capture -- failures are swallowed so a metrics hiccup never breaks
 * the ad surface itself. */
export function recordBannerImpression(campaignId: string): void {
  http.post(`/banners/${campaignId}/impressions`, undefined).catch(() => {});
}

export function recordBannerClick(campaignId: string): void {
  http.post(`/banners/${campaignId}/clicks`, undefined).catch(() => {});
}
