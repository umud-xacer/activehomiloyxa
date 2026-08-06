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
}

export interface BannerCampaignCreateInput {
  slotKey: string;
  creativeMediaAssetId: string;
  entitlementId: string;
  scheduleStart: string;
  scheduleEnd: string;
  priority: number;
  targeting?: BannerTargeting;
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
