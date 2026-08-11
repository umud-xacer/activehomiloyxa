/**
 * API client for banner campaign management (BC-09 Ads, `/admin/campaigns*`). A campaign
 * references its placement slot, creative, and billing entitlement by identifier only (the
 * contract's own `createCampaign` description) — this client does not resolve or validate those
 * identifiers, it just carries them through to the backend, which enforces I-20/I-21 itself.
 */
import { http } from "@/lib/http";

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

/** `GET /banners/serve` -- 204 (no eligible campaign for this slot right now) surfaces as `null`,
 * never an error, so a caller can render nothing rather than an error state for the ordinary
 * "no active campaign" case. */
export async function serveBanner(slotKey: string): Promise<BannerServeView | null> {
  return http.get<BannerServeView | null>("/banners/serve", { params: { slotKey } });
}

/** Fire-and-forget engagement capture -- failures are swallowed so a metrics hiccup never breaks
 * the ad surface itself. */
export function recordBannerImpression(campaignId: string): void {
  http.post(`/banners/${campaignId}/impressions`, undefined).catch(() => {});
}

export function recordBannerClick(campaignId: string): void {
  http.post(`/banners/${campaignId}/clicks`, undefined).catch(() => {});
}
