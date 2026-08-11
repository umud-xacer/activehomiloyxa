/**
 * API client for the secret owner-admin panel's category management. Wraps the generic
 * `configuration` module's maker-checker config-authoring endpoints (`/admin/config/...`, shared
 * by all 8 config entity types) into category/form-definition-specific calls, plus the
 * `publish-solo` convenience endpoint that lets a single logged-in super-admin complete both the
 * maker and checker steps of a CONTROLLED-track publish without a second account.
 */
import { http } from "@/lib/http";
import type { FormField, FormFieldOption } from "@/lib/catalog-client";

export interface LocalizedText {
  uz_latn?: string | null;
  uz_cyrl?: string | null;
  ru?: string | null;
  en?: string | null;
}

export interface ConfigHeadDto {
  id: string;
  entityType: string;
  code: string;
  currentVersionId: string | null;
  status: string;
  businessOwner: string;
  createdAt: string;
}

export interface ConfigVersionDto {
  id: string;
  headId: string;
  versionNumber: number;
  status: string;
  definition: Record<string, unknown>;
  snapshot: Record<string, unknown> | null;
  approvedBy: string | null;
  publishedAt: string | null;
}

type EntityType =
  "category" | "form-definition" | "product-definition" | "placement-slot" | "platform-settings";

const base = (entityType: EntityType) => `/admin/config/${entityType}`;

async function listHeads(entityType: EntityType, limit = 100) {
  return http.get<{ items: ConfigHeadDto[]; page: { nextCursor: string | null } }>(
    base(entityType),
    { params: { limit } },
  );
}

async function getHead(entityType: EntityType, headId: string) {
  return http.get<ConfigHeadDto>(`${base(entityType)}/${headId}`);
}

async function getVersion(entityType: EntityType, headId: string, versionId: string) {
  return http.get<ConfigVersionDto>(`${base(entityType)}/${headId}/versions/${versionId}`);
}

async function createHead(
  entityType: EntityType,
  code: string,
  businessOwner: string,
  definition: Record<string, unknown>,
) {
  return http.post<ConfigVersionDto>(base(entityType), { code, businessOwner, definition });
}

async function createVersionDraft(
  entityType: EntityType,
  headId: string,
  definition: Record<string, unknown>,
) {
  return http.post<ConfigVersionDto>(`${base(entityType)}/${headId}/versions`, { definition });
}

async function validateVersion(entityType: EntityType, headId: string, versionId: string) {
  return http.post<{ valid: boolean; errors: unknown }>(
    `${base(entityType)}/${headId}/versions/${versionId}/validate`,
  );
}

/** Runs both the maker and (self-service) checker step in sequence, throwing with the gate's own
 * validation errors if the draft doesn't pass. */
async function publishSolo(entityType: EntityType, headId: string, versionId: string) {
  await validateVersion(entityType, headId, versionId);
  return http.post<ConfigVersionDto>(
    `${base(entityType)}/${headId}/versions/${versionId}/publish-solo`,
    {},
  );
}

export interface DynamicFieldDraft {
  code: string;
  label: LocalizedText;
  fieldType: FormField["fieldType"];
  required: boolean;
  options: FormFieldOption[];
}

function toFieldContent(field: DynamicFieldDraft, order: number) {
  return {
    code: field.code,
    section_code: "asosiy",
    label: field.label,
    field_type: field.fieldType,
    required: field.required,
    facet_eligible: false,
    order,
    default_value: null,
    options: field.options.map((o) => ({ value: o.value, label: o.label })),
    validators: field.required ? [{ validator_type: "required", params: {} }] : [],
  };
}

/** Creates and solo-publishes a new form-definition head from a flat field list (all fields in
 * one implicit "asosiy" section — the admin panel doesn't expose multi-section authoring, the
 * generic config API underneath does if a future pass needs it). Returns the new head id, which
 * a category's `formDefinitionId` binds to. */
export async function publishNewFormDefinition(
  code: string,
  name: LocalizedText,
  fields: DynamicFieldDraft[],
): Promise<string> {
  const definition = {
    descriptor: { name, description: null, display_order: 0, metadata: {} },
    sections: [{ code: "asosiy", label: name, order: 0 }],
    fields: fields.map(toFieldContent),
  };
  const version = await createHead("form-definition", code, "Owner Admin", definition);
  const published = await publishSolo("form-definition", version.headId, version.id);
  return published.headId;
}

/** Adds a new version to an existing form-definition head (editing a category's dynamic fields
 * never touches the category record itself — `formDefinitionId` points at the head, which always
 * resolves to its current published version). */
export async function updateFormDefinitionFields(
  headId: string,
  name: LocalizedText,
  fields: DynamicFieldDraft[],
): Promise<void> {
  const definition = {
    descriptor: { name, description: null, display_order: 0, metadata: {} },
    sections: [{ code: "asosiy", label: name, order: 0 }],
    fields: fields.map(toFieldContent),
  };
  const version = await createVersionDraft("form-definition", headId, definition);
  await publishSolo("form-definition", headId, version.id);
}

export type ListingKind = "PROPERTY" | "GOODS" | "SERVICE" | "VENUE";

export interface CategoryDraftInput {
  code: string;
  name: LocalizedText;
  path: string;
  parentCategoryId: string | null;
  displayOrder: number;
  formDefinitionId: string;
  iconUrl: string | null;
  treeStatus: "ACTIVE" | "RETIRED";
  /** Per-category page theming (`categories/$slug.tsx`'s Hero + which shared template renders) --
   * all optional, all additive on top of the pre-existing `iconUrl` metadata field. */
  heroImageUrl?: string | null;
  heroTagline?: string | null;
  accentColor?: string | null;
  listingKind?: ListingKind | null;
  /** A named entry in the frontend's icon registry (`lib/listing-kind.ts`'s `ICON_BY_NAME`) --
   * gives categories with no uploaded photo (mainly subcategories) a themed icon instead of a
   * bare fallback. Independent of `iconUrl` (a real image), which always wins when set. */
  iconName?: string | null;
}

function categoryDefinition(input: CategoryDraftInput) {
  const metadata: Record<string, unknown> = {};
  if (input.iconUrl) metadata.iconUrl = input.iconUrl;
  if (input.heroImageUrl) metadata.heroImageUrl = input.heroImageUrl;
  if (input.heroTagline) metadata.heroTagline = input.heroTagline;
  if (input.accentColor) metadata.accentColor = input.accentColor;
  if (input.listingKind) metadata.listingKind = input.listingKind;
  if (input.iconName) metadata.iconName = input.iconName;
  return {
    descriptor: {
      name: input.name,
      description: null,
      display_order: input.displayOrder,
      metadata,
    },
    parent_category_id: input.parentCategoryId,
    path: input.path,
    form_definition_id: input.formDefinitionId,
    tree_status: input.treeStatus,
  };
}

export async function publishNewCategory(input: CategoryDraftInput): Promise<ConfigVersionDto> {
  const version = await createHead(
    "category",
    input.code,
    "Owner Admin",
    categoryDefinition(input),
  );
  return publishSolo("category", version.headId, version.id);
}

export async function publishCategoryUpdate(
  headId: string,
  input: CategoryDraftInput,
): Promise<ConfigVersionDto> {
  const version = await createVersionDraft("category", headId, categoryDefinition(input));
  return publishSolo("category", headId, version.id);
}

/** Every category head with its currently published version resolved, for the admin list view
 * (the public `GET /categories` only returns ACTIVE ones — the panel needs RETIRED/DRAFT too). */
export async function listAllCategoryVersions(): Promise<
  Array<{ head: ConfigHeadDto; version: ConfigVersionDto | null }>
> {
  const { items } = await listHeads("category");
  const rows = await Promise.all(
    items.map(async (head) => ({
      head,
      version: head.currentVersionId
        ? await getVersion("category", head.id, head.currentVersionId)
        : null,
    })),
  );
  return rows;
}

export async function listAllFormDefinitionHeads(): Promise<ConfigHeadDto[]> {
  const { items } = await listHeads("form-definition");
  return items;
}

/** Resolves the form-definition head's OWN current published version (not to be confused with
 * the category's version id -- a category only stores the form head's id, never a version). */
export async function getFormDefinitionFields(
  headId: string,
): Promise<{ name: LocalizedText; fields: DynamicFieldDraft[] }> {
  const head = await getHead("form-definition", headId);
  if (!head.currentVersionId) return { name: {}, fields: [] };
  const version = await getVersion("form-definition", headId, head.currentVersionId);
  const def = version.definition as {
    descriptor: { name: LocalizedText };
    fields: Array<{
      code: string;
      label: LocalizedText;
      field_type: DynamicFieldDraft["fieldType"];
      required: boolean;
      options: FormFieldOption[];
    }>;
  };
  return {
    name: def.descriptor.name,
    fields: def.fields.map((f) => ({
      code: f.code,
      label: f.label,
      fieldType: f.field_type,
      required: f.required,
      options: f.options ?? [],
    })),
  };
}

// -- tariff plans (product-definition, Monetization task) --------------------------------------

export interface ProductDraftInput {
  code: string;
  name: LocalizedText;
  productType:
    "SUBSCRIPTION" | "PREMIUM" | "FEATURED" | "TOP_PLACEMENT" | "VERIFICATION" | "BANNER_PLACEMENT";
  priceAmount: string;
  priceCurrency: string;
  termDays: number | null;
  maxActiveListings: number | null;
}

function productDefinition(input: ProductDraftInput) {
  return {
    descriptor: { name: input.name, description: null, display_order: 0, metadata: {} },
    product_type: input.productType,
    price_amount: input.priceAmount,
    price_currency: input.priceCurrency,
    term_days: input.termDays,
    quota_set:
      input.maxActiveListings !== null ? { max_active_listings: input.maxActiveListings } : null,
    benefit_descriptor: {},
  };
}

export async function publishNewProduct(input: ProductDraftInput): Promise<ConfigVersionDto> {
  const version = await createHead(
    "product-definition",
    input.code,
    "Owner Admin",
    productDefinition(input),
  );
  return publishSolo("product-definition", version.headId, version.id);
}

export async function publishProductUpdate(
  headId: string,
  input: ProductDraftInput,
): Promise<ConfigVersionDto> {
  const version = await createVersionDraft("product-definition", headId, productDefinition(input));
  return publishSolo("product-definition", headId, version.id);
}

/** Every product-definition head with its currently published version resolved, for the admin
 * list view (mirrors `listAllCategoryVersions`'s own shape). */
export async function listAllProductVersions(): Promise<
  Array<{ head: ConfigHeadDto; version: ConfigVersionDto | null }>
> {
  const { items } = await listHeads("product-definition");
  const rows = await Promise.all(
    items.map(async (head) => ({
      head,
      version: head.currentVersionId
        ? await getVersion("product-definition", head.id, head.currentVersionId)
        : null,
    })),
  );
  return rows;
}

// -- placement slots (Ads/banner campaigns bind to a slot by SlotKey) --------------------------

export interface PlacementSlotDraftInput {
  code: string;
  name: LocalizedText;
  slotKey: string;
  pageZone: string;
  widthPx: number | null;
  heightPx: number | null;
}

function placementSlotDefinition(input: PlacementSlotDraftInput) {
  return {
    descriptor: { name: input.name, description: null, display_order: 0, metadata: {} },
    slot_key: input.slotKey,
    page_zone: input.pageZone,
    width_px: input.widthPx,
    height_px: input.heightPx,
    targeting_dimensions: [],
  };
}

export async function publishNewPlacementSlot(
  input: PlacementSlotDraftInput,
): Promise<ConfigVersionDto> {
  const version = await createHead(
    "placement-slot",
    input.code,
    "Owner Admin",
    placementSlotDefinition(input),
  );
  return publishSolo("placement-slot", version.headId, version.id);
}

export async function publishPlacementSlotUpdate(
  headId: string,
  input: PlacementSlotDraftInput,
): Promise<ConfigVersionDto> {
  const version = await createVersionDraft(
    "placement-slot",
    headId,
    placementSlotDefinition(input),
  );
  return publishSolo("placement-slot", headId, version.id);
}

/** Every placement-slot head with its currently published version resolved, for the admin list
 * view (mirrors `listAllCategoryVersions`'s own shape). */
export async function listAllPlacementSlotVersions(): Promise<
  Array<{ head: ConfigHeadDto; version: ConfigVersionDto | null }>
> {
  const { items } = await listHeads("placement-slot");
  const rows = await Promise.all(
    items.map(async (head) => ({
      head,
      version: head.currentVersionId
        ? await getVersion("placement-slot", head.id, head.currentVersionId)
        : null,
    })),
  );
  return rows;
}

// -- owner-admin panel access (platform-settings' `admin.owner_panel_slug`) --------------------
//
// The panel's own URL segment (frontend `/$ownerAdminSlug`) is stored as a platform setting
// instead of a build-time env var, specifically so a super-admin can change it from inside the
// panel itself whenever they want, without a code change or redeploy.

const PLATFORM_SETTINGS_CODE = "platform-settings-global";
const OWNER_PANEL_SLUG_KEY = "admin.owner_panel_slug";
export const OWNER_PANEL_SLUG_DEFAULT = "owner-admin";

/** Every top-level static route the frontend already owns (files and directories directly under
 * `src/routes/`), hand-kept in sync with `apps/backend/src/configuration/domain/whitelist.py`'s
 * `RESERVED_OWNER_PANEL_SLUGS` --
 * TanStack Router always resolves a static route ahead of the dynamic `/$ownerAdminSlug` one for
 * the same path, so setting the panel's slug to any of these would make that static page win
 * forever and silently strand the panel (confirmed incident: set to "boss", permanently shadowed
 * by the dedicated login route at that exact path). The backend is the real enforcement point
 * (rejects a save, and self-heals an already-bad stored value back to the default on read) --
 * this copy only gives instant client-side feedback instead of a round trip.
 *
 * Deliberately excludes "owner-admin" itself -- that was a real conflict back when the frontend
 * had a static `routes/owner-admin/` directory, but that's gone now; it's just this dynamic
 * route's fallback DEFAULT value (`OWNER_PANEL_SLUG_DEFAULT` below), which must stay assignable. */
export const OWNER_PANEL_RESERVED_SLUGS: ReadonlySet<string> = new Set([
  "about",
  "ad-rules",
  "admin",
  "agents",
  "ai",
  "api",
  "appliances",
  "auth",
  "blog",
  "boss",
  "categories",
  "checkout",
  "companies",
  "compare",
  "construction",
  "contact",
  "dashboard",
  "faq",
  "favorites",
  "furniture",
  "health",
  "hostels",
  "hotels",
  "interior",
  "invest",
  "jobs",
  "landscape",
  "list",
  "listing",
  "maintenance",
  "map",
  "materials",
  "messages",
  "news",
  "notifications",
  "offer",
  "payments",
  "pricing",
  "privacy",
  "properties",
  "public-offer",
  "ready",
  "recreation",
  "refund",
  "refund-policy",
  "rules",
  "saved",
  "search",
  "security",
  "security-policy",
  "services",
  "settings",
  "sitemap.xml",
  "subscriptions",
  "support",
  "terms",
  "verification",
  "wallet",
]);

const OWNER_PANEL_SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;

export function isValidOwnerPanelSlug(value: unknown): value is string {
  if (typeof value !== "string" || !value) return false;
  const slug = value.trim().toLowerCase();
  return OWNER_PANEL_SLUG_PATTERN.test(slug) && !OWNER_PANEL_RESERVED_SLUGS.has(slug);
}

async function getPlatformSettingsHead(): Promise<ConfigHeadDto | null> {
  const { items } = await listHeads("platform-settings");
  return items.find((h) => h.code === PLATFORM_SETTINGS_CODE) ?? null;
}

/** The currently-published owner-admin panel URL segment. Only reachable by an already
 * logged-in super-admin (`config:platform-settings:manage`) -- used by the `/admin` hub to build
 * a working link, and by the panel itself to link between its own pages. Self-heals the same way
 * the backend's `_current_owner_admin_slug` does: an invalid/reserved stored value is treated as
 * absent rather than trusted. */
export async function getOwnerPanelSlug(): Promise<string> {
  const head = await getPlatformSettingsHead();
  if (!head?.currentVersionId) return OWNER_PANEL_SLUG_DEFAULT;
  const version = await getVersion("platform-settings", head.id, head.currentVersionId);
  const settings = (version.snapshot?.settings as Record<string, unknown> | undefined) ?? {};
  const value = settings[OWNER_PANEL_SLUG_KEY];
  return isValidOwnerPanelSlug(value) ? value.trim().toLowerCase() : OWNER_PANEL_SLUG_DEFAULT;
}

/** Changes the owner-admin panel's URL segment. Reads forward from the current *definition* (not
 * snapshot) and only patches the one settings key -- `platform-settings` also carries homepage
 * zones/navigation/SEO templates/other settings this panel doesn't manage, and a new version
 * always replaces the whole document, so anything not carried forward here would be silently
 * dropped. */
export async function updateOwnerPanelSlug(newSlug: string): Promise<void> {
  const head = await getPlatformSettingsHead();
  if (!head?.currentVersionId) {
    throw new Error("Platform sozlamalari hali ishga tushirilmagan.");
  }
  const version = await getVersion("platform-settings", head.id, head.currentVersionId);
  const definition = version.definition as Record<string, unknown>;
  const settings = {
    ...(definition.settings as Record<string, unknown> | undefined),
    [OWNER_PANEL_SLUG_KEY]: newSlug,
  };
  const draft = await createVersionDraft("platform-settings", head.id, { ...definition, settings });
  await publishSolo("platform-settings", head.id, draft.id);
}

/** Public, unauthenticated yes/no check backing the `/$ownerAdminSlug` route guard
 * (`require-auth.ts`'s `requireOwnerAdminSlug`) -- never learns or reveals the real slug, only
 * whether a given guess matches it, so the real value never has to sit in the client bundle. */
export async function verifyOwnerAdminSlug(slug: string): Promise<boolean> {
  const { valid } = await http.post<{ valid: boolean }>("/public/owner-admin-access/verify", {
    slug,
  });
  return valid;
}

// -- icon upload -------------------------------------------------------------------------------

interface MediaUploadTicket {
  mediaAssetId: string;
  uploadUrl: string;
  method: string;
  headers?: Record<string, string>;
  expiresAt: string;
}

interface MediaAssetDto {
  id: string;
  url: string | null;
  scanStatus: "PENDING" | "CLEAN" | "QUARANTINED";
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Uploads a category icon and waits (briefly) for the malware scan to clear so the panel can
 * show the real CDN URL immediately. If scanning is still pending after the timeout, the media
 * asset id is still returned — the icon just won't preview until a later panel refresh. */
export async function uploadCategoryIcon(
  file: File,
): Promise<{ mediaAssetId: string; url: string | null }> {
  const ticket = await http.post<MediaUploadTicket>("/media/uploads", {
    contentType: file.type,
    sizeBytes: file.size,
    ownerContextType: "BANNER_CREATIVE",
  });
  const response = await fetch(ticket.uploadUrl, {
    method: ticket.method || "PUT",
    headers: { "Content-Type": file.type, ...ticket.headers },
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Ikonka yuklashda xatolik (status ${response.status})`);
  }

  for (let attempt = 0; attempt < 10; attempt++) {
    await sleep(700);
    const asset = await http.get<MediaAssetDto>(`/media/${ticket.mediaAssetId}`);
    if (asset.scanStatus === "CLEAN" && asset.url) {
      return { mediaAssetId: ticket.mediaAssetId, url: asset.url };
    }
    if (asset.scanStatus === "QUARANTINED") {
      throw new Error("Rasm zararli deb topildi va rad etildi.");
    }
  }
  return { mediaAssetId: ticket.mediaAssetId, url: null };
}
