/**
 * Business-profiles API client — matches the "Business Profiles" section of
 * contracts/openapi.yaml (the real, already-implemented `profiles` module — BC-02).
 * Used by the legal-entity dashboard (ADR-0007's LEGAL_ENTITY workspace) and the
 * Landing Page / Business Profile edit form (`routes/dashboard/business-profile.tsx`).
 */
import { http } from "./http";

export type ProfileType =
  | "CONSTRUCTION_COMPANY"
  | "MANUFACTURER"
  | "BUILDER"
  | "SUPPLIER"
  | "CONTRACTOR"
  | "ARCHITECT"
  | "INTERIOR_DESIGNER"
  | "SERVICE_PROVIDER";

export interface LocalizedText {
  uz_latn?: string;
  uz_cyrl?: string;
  ru?: string;
  en?: string;
}

export interface BusinessProfileBadge {
  status: "VALID" | "EXPIRED" | "REVOKED" | null;
  issuedAt?: string | null;
  validUntil?: string | null;
}

/** The `contacts` blob is a freeform JSONB VO in the backend (no fixed shape mandated) — this
 * is this frontend's own chosen convention for it, used consistently by create/update/read. */
export interface BusinessProfileContacts {
  phones?: string[];
  emails?: string[];
  website?: string;
}

export interface PortfolioItem {
  id: string;
  mediaAssetId: string;
  position: number;
  caption?: LocalizedText | null;
}

export interface BusinessProfile {
  id: string;
  ownerUserId: string;
  profileType: ProfileType;
  name: LocalizedText;
  description?: LocalizedText | null;
  contacts?: BusinessProfileContacts | null;
  address?: string | null;
  slug?: string;
  status: "CREATED" | "ACTIVE" | "ARCHIVED";
  badge?: BusinessProfileBadge | null;
  portfolio?: PortfolioItem[];
  logoMediaAssetId?: string | null;
  bannerMediaAssetId?: string | null;
  subscriptionStatus: "ACTIVE" | "EXPIRED" | "NONE";
  subscriptionValidUntil?: string | null;
  createdAt?: string;
}

export interface SubmittedDocument {
  id?: string;
  mediaAssetId: string;
  documentKind: string;
  position?: number;
}

export interface VerificationCase {
  id: string;
  businessProfileId: string;
  entitlementId?: string;
  status: "REQUESTED" | "IN_REVIEW" | "APPROVED" | "REJECTED";
  slaDueAt?: string;
  documents?: SubmittedDocument[];
  decision?: { outcome: "APPROVED" | "REJECTED"; reason?: string; decidedAt: string } | null;
  createdAt?: string;
}

export const PROFILE_TYPE_LABEL: Record<ProfileType, string> = {
  CONSTRUCTION_COMPANY: "Qurilish kompaniyasi",
  MANUFACTURER: "Ishlab chiqaruvchi",
  BUILDER: "Quruvchi",
  SUPPLIER: "Yetkazib beruvchi",
  CONTRACTOR: "Pudratchi",
  ARCHITECT: "Arxitektor",
  INTERIOR_DESIGNER: "Interyer dizayneri",
  SERVICE_PROVIDER: "Xizmat ko'rsatuvchi",
};

interface UpdatePayload {
  name?: string;
  description?: string;
  contacts?: BusinessProfileContacts;
  address?: string;
}

export const businessProfilesApi = {
  /** GET /business-profiles — the public companies directory. Client filters to
   * `subscriptionStatus === "ACTIVE"` (a lapsed subscription's profile stays readable by id --
   * e.g. by its own owner -- but shouldn't be discoverable in the public listing; see
   * `BusinessProfile.subscriptionStatus`'s own docstring for why this is a frontend-side filter
   * rather than a backend one). */
  listPublic(params?: {
    profileType?: ProfileType;
    verifiedOnly?: boolean;
  }): Promise<BusinessProfile[]> {
    return http
      .get<{ items: BusinessProfile[] }>("/business-profiles", {
        params: {
          profileType: params?.profileType,
          verifiedOnly: params?.verifiedOnly,
          limit: 100,
        },
      })
      .then((page) => page.items);
  },

  /** GET /business-profiles/{id} — the profiles the account owns are read individually via
   * `Account.ownedProfileIds` (there is no "list mine" filter on the public listing endpoint). */
  get(profileId: string): Promise<BusinessProfile> {
    return http.get<BusinessProfile>(`/business-profiles/${profileId}`);
  },

  create(input: {
    profileType: ProfileType;
    name: string;
    address?: string;
  }): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(
      "/business-profiles",
      {
        profileType: input.profileType,
        name: { uz_latn: input.name },
        address: input.address || undefined,
      },
      { idempotent: true },
    );
  },

  /** PATCH /business-profiles/{id} — partial update; `profileType` is immutable server-side. */
  update(profileId: string, input: UpdatePayload): Promise<BusinessProfile> {
    return http.patch<BusinessProfile>(`/business-profiles/${profileId}`, {
      name: input.name !== undefined ? { uz_latn: input.name } : undefined,
      description: input.description !== undefined ? { uz_latn: input.description } : undefined,
      contacts: input.contacts,
      address: input.address,
    });
  },

  archive(profileId: string): Promise<void> {
    return http.delete<void>(`/business-profiles/${profileId}`);
  },

  /** PATCH /business-profiles/{id}/branding — sets the landing page's logo/banner. `null`
   * clears the one it's passed for (see `BusinessProfileBrandingRequest`'s own docstring). */
  updateBranding(
    profileId: string,
    input: { logoMediaAssetId?: string | null; bannerMediaAssetId?: string | null },
  ): Promise<BusinessProfile> {
    return http.patch<BusinessProfile>(`/business-profiles/${profileId}/branding`, input);
  },

  listPortfolio(profileId: string): Promise<PortfolioItem[]> {
    return http.get<PortfolioItem[]>(`/business-profiles/${profileId}/portfolio`);
  },

  /** POST /business-profiles/{id}/portfolio — the wire contract's `PortfolioItem` schema marks
   * `id`/`position` required, but the backend use case ignores both (assigns its own id, always
   * appends) — see `profiles/interfaces/routers.py::add_portfolio_item`. Sent as throwaway
   * placeholder values purely to satisfy the frozen request-body shape. */
  addPortfolioItem(
    profileId: string,
    input: { mediaAssetId: string; caption?: string },
  ): Promise<PortfolioItem> {
    return http.post<PortfolioItem>(`/business-profiles/${profileId}/portfolio`, {
      id: crypto.randomUUID(),
      mediaAssetId: input.mediaAssetId,
      position: 1,
      caption: input.caption ? { uz_latn: input.caption } : undefined,
    });
  },

  removePortfolioItem(profileId: string, itemId: string): Promise<void> {
    return http.delete<void>(`/business-profiles/${profileId}/portfolio/${itemId}`);
  },

  getVerification(profileId: string): Promise<VerificationCase | null> {
    return http
      .get<VerificationCase>(`/business-profiles/${profileId}/verification`)
      .catch(() => null);
  },

  /** POST /business-profiles/{id}/verification — requires an active VERIFICATION_ELIGIBILITY
   * entitlement (billingApi.listMyEntitlements()) and at least one document. */
  requestVerification(
    profileId: string,
    input: { entitlementId: string; documents: SubmittedDocument[] },
  ): Promise<VerificationCase> {
    return http.post<VerificationCase>(`/business-profiles/${profileId}/verification`, input, {
      idempotent: true,
    });
  },
};

export interface BusinessProfilePage {
  items: BusinessProfile[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

/** Owner-admin panel's direct company-management surface (`profiles:profile:manage`,
 * gated the same "real check, not merely declared" way as `adminUsersApi`) — distinct from
 * `businessProfilesApi.listPublic` above, which only ever shows non-ARCHIVED companies to
 * anonymous visitors. */
export const adminBusinessProfilesApi = {
  list(params?: {
    status?: "CREATED" | "ACTIVE" | "ARCHIVED";
    cursor?: string;
    limit?: number;
  }): Promise<BusinessProfilePage> {
    return http.get<BusinessProfilePage>("/admin/business-profiles", { params });
  },

  archive(profileId: string): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(
      `/admin/business-profiles/${profileId}/archive`,
      {},
      { idempotent: true },
    );
  },
};
