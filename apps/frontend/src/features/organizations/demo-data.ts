/**
 * "Trusted partner" organizations -- the homepage's compact "Tashkilotlar" rail
 * (`components/site/OrganizationsCarousel.tsx`). Originally a hand-curated list of 5 real
 * partner-bank logos carried over from the platform's original Django build (see prior git
 * history for the fixture-based version). Swapped to a real fetch now that self-service
 * `BusinessProfile` (`profiles` module, ADR-0010) is the real "organizations" backend concept --
 * every publicly-visible (`subscriptionStatus === "ACTIVE"`, trial or paid) profile appears here
 * automatically the moment it completes onboarding, capped to the homepage's own display limit;
 * the complete list (no cap) lives at `/companies`, linked via the carousel's own "Barcha
 * tashkilotlarni ko'rish" button.
 *
 * Swap point: `getOrganizations()` is the only place that knows about this fetch -- the only
 * caller (`OrganizationsCarousel`) already treats it as async and doesn't care where the data
 * actually comes from.
 */
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
} from "@/lib/business-profiles-client";
import { getMediaAssetUrl } from "@/lib/media-client";

export interface Organization {
  key: string;
  name: string;
  kind: string;
  logo: string;
  to: string;
}

/** Real API companies almost always outnumber the homepage's compact rail -- the site owner's
 * own explicit spec: show at most 5 here, everything else only in the full `/companies` catalog. */
export const HOMEPAGE_ORGANIZATIONS_LIMIT = 5;

function orgName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
}

export async function getOrganizations(
  limit: number = HOMEPAGE_ORGANIZATIONS_LIMIT,
): Promise<Organization[]> {
  const profiles = await businessProfilesApi.listPublic();
  const active = profiles.filter((p) => p.subscriptionStatus === "ACTIVE").slice(0, limit);
  const resolved = await Promise.all(
    active.map(async (profile) => ({
      key: profile.id,
      name: orgName(profile),
      kind: PROFILE_TYPE_LABEL[profile.profileType],
      logo: profile.logoMediaAssetId ? await getMediaAssetUrl(profile.logoMediaAssetId) : null,
      to: `/companies/${profile.slug || profile.id}`,
    })),
  );
  // A logo-less profile would render a broken <img> in this brand-rail context -- skip it here
  // (it still appears normally on `/companies`, which already has its own initials fallback).
  return resolved.filter((org): org is Organization => !!org.logo);
}
