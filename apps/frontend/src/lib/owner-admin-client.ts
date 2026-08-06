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

type EntityType = "category" | "form-definition" | "product-definition" | "placement-slot";

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

export interface CategoryDraftInput {
  code: string;
  name: LocalizedText;
  path: string;
  parentCategoryId: string | null;
  displayOrder: number;
  formDefinitionId: string;
  iconUrl: string | null;
  treeStatus: "ACTIVE" | "RETIRED";
}

function categoryDefinition(input: CategoryDraftInput) {
  return {
    descriptor: {
      name: input.name,
      description: null,
      display_order: input.displayOrder,
      metadata: input.iconUrl ? { iconUrl: input.iconUrl } : {},
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
