/**
 * "Trusted partner" organizations -- the backend has no admin-curated organization/company
 * concept yet (the closest thing, `profiles`' `BusinessProfile`, is owner-scoped self-service, not
 * an admin-authored "featured partners" list). These 5 are the real partner banks and logos from
 * the platform's original Django build (`ActiveReturn`'s `blog.partner` fixture), carried over so
 * this section shows genuine partners rather than invented placeholder companies.
 *
 * Swap point: `getOrganizations()` is the only place that knows this list is a static carry-over.
 * Once a real backend concept exists for admin-curated partner organizations, replace its body
 * with the real fetch -- the only caller (`OrganizationsCarousel`) already treats it as async.
 */
import anorbankLogo from "@/assets/partners/Artboard_30-100.jpg";
import davrbankLogo from "@/assets/partners/Artboard_34-100.jpg";
import infinbankLogo from "@/assets/partners/Artboard_38-100.jpg";
import trastbankLogo from "@/assets/partners/Artboard_51-100.jpg";
import turonbankLogo from "@/assets/partners/Artboard_52-100.jpg";

export interface Organization {
  key: string;
  name: string;
  kind: string;
  logo: string;
  to: string;
}

/** Links point at the closest existing route for that org's line of business (there's no
 * per-organization profile page yet). */
const ORGANIZATIONS: Organization[] = [
  { key: "anorbank", name: "Anorbank", kind: "Ipoteka", logo: anorbankLogo, to: "/payments" },
  { key: "davrbank", name: "Davr bank", kind: "Ipoteka", logo: davrbankLogo, to: "/payments" },
  { key: "trastbank", name: "Trast bank", kind: "Ipoteka", logo: trastbankLogo, to: "/payments" },
  { key: "turonbank", name: "Turon bank", kind: "Ipoteka", logo: turonbankLogo, to: "/payments" },
  { key: "infinbank", name: "InfinBank", kind: "Ipoteka", logo: infinbankLogo, to: "/payments" },
];

export async function getOrganizations(): Promise<Organization[]> {
  return ORGANIZATIONS;
}
