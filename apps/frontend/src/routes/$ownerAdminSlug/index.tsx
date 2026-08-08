import { useEffect, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutGrid,
  Plus,
  Pencil,
  Loader2,
  ShieldCheck,
  Layers,
  EyeOff,
  Eye,
  Trash2,
  ImagePlus,
  X,
  CreditCard,
  ChevronRight,
  ChevronDown,
  Megaphone,
  KeyRound,
} from "lucide-react";
import { requireOwnerAdminSlug } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";
import {
  listAllCategoryVersions,
  getFormDefinitionFields,
  publishNewFormDefinition,
  updateFormDefinitionFields,
  publishNewCategory,
  publishCategoryUpdate,
  uploadCategoryIcon,
  listAllProductVersions,
  publishNewProduct,
  publishProductUpdate,
  updateOwnerPanelSlug,
  isValidOwnerPanelSlug,
  OWNER_PANEL_RESERVED_SLUGS,
  type ConfigHeadDto,
  type ConfigVersionDto,
  type DynamicFieldDraft,
  type LocalizedText,
  type ListingKind,
  type ProductDraftInput,
} from "@/lib/owner-admin-client";
import type { FormField as FieldType } from "@/lib/catalog-client";

export const Route = createFileRoute("/$ownerAdminSlug/")({
  beforeLoad: requireOwnerAdminSlug,
  // `requireOwnerAdminSlug` only enforces client-side (no request-scoped cookie forwarding into SSR
  // yet) -- without this, the server would render the full panel into the initial HTML for
  // anyone who requests the URL, defeating the "this route doesn't exist" posture entirely.
  ssr: false,
  head: () => ({ meta: [{ title: "Owner Admin — ActiveHome" }] }),
  component: Page,
});

const FIELD_TYPES: { value: FieldType["fieldType"]; label: string }[] = [
  { value: "text", label: "Matn" },
  { value: "number", label: "Son" },
  { value: "select", label: "Tanlov (bitta)" },
  { value: "multiselect", label: "Tanlov (bir nechta)" },
  { value: "boolean", label: "Ha/Yo'q" },
  { value: "date", label: "Sana" },
  { value: "range", label: "Oraliq" },
  { value: "location", label: "Joylashuv" },
  { value: "file", label: "Fayl" },
];

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/['’ʻʼ`]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

interface CategoryRow {
  head: ConfigHeadDto;
  version: ConfigVersionDto | null;
}

function categoryName(row: CategoryRow): string {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { descriptor?: { name?: LocalizedText } } | undefined;
  return snapshot?.descriptor?.name?.uz_latn || row.head.code;
}

function categoryPath(row: CategoryRow): string {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { path?: string } | undefined;
  return snapshot?.path || "—";
}

function categoryTreeStatus(row: CategoryRow): "ACTIVE" | "RETIRED" {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { tree_status?: "ACTIVE" | "RETIRED" } | undefined;
  return snapshot?.tree_status ?? "RETIRED";
}

function categoryFormHeadId(row: CategoryRow): string | null {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { form_definition_id?: string } | undefined;
  return snapshot?.form_definition_id ?? null;
}

function categoryParentId(row: CategoryRow): string | null {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { parent_category_id?: string | null } | undefined;
  return snapshot?.parent_category_id ?? null;
}

function categoryDisplayOrder(row: CategoryRow): number {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { descriptor?: { display_order?: number } } | undefined;
  return snapshot?.descriptor?.display_order ?? 0;
}

function categoryIconUrl(row: CategoryRow): string | null {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    { descriptor?: { metadata?: { iconUrl?: string } } } | undefined;
  return snapshot?.descriptor?.metadata?.iconUrl ?? null;
}

/** Per-category Hero/page-template metadata -- same additive `descriptor.metadata` slot
 * `categoryIconUrl` already reads from (see `owner-admin-client.ts`'s `categoryDefinition`). */
function categoryPageMeta(row: CategoryRow): {
  heroImageUrl: string | null;
  heroTagline: string;
  accentColor: string | null;
  listingKind: ListingKind;
} {
  const snapshot = (row.version?.snapshot ?? row.version?.definition) as
    | {
        descriptor?: {
          metadata?: {
            heroImageUrl?: string;
            heroTagline?: string;
            accentColor?: string;
            listingKind?: string;
          };
        };
      }
    | undefined;
  const metadata = snapshot?.descriptor?.metadata ?? {};
  const kind = metadata.listingKind;
  return {
    heroImageUrl: metadata.heroImageUrl ?? null,
    heroTagline: metadata.heroTagline ?? "",
    accentColor: metadata.accentColor ?? null,
    listingKind: kind === "GOODS" || kind === "SERVICE" || kind === "VENUE" ? kind : "PROPERTY",
  };
}

/** How many ancestors `row` has within `all` (0 for a root category). Walks the parent chain via
 * a lookup map; guards against a cycle (shouldn't exist -- the backend's `taxonomy.creates_cycle`
 * rejects one at publish-time -- but a defensive stop is cheap and this is UI-only indentation,
 * not a correctness-load-bearing computation). */
function categoryDepth(row: CategoryRow, all: CategoryRow[]): number {
  const byId = new Map(all.map((r) => [r.head.id, r]));
  const seen = new Set<string>();
  let depth = 0;
  let currentParentId = categoryParentId(row);
  while (currentParentId && !seen.has(currentParentId)) {
    seen.add(currentParentId);
    const parent = byId.get(currentParentId);
    if (!parent) break;
    depth += 1;
    currentParentId = categoryParentId(parent);
  }
  return depth;
}

interface CategoryTreeNode {
  row: CategoryRow;
  children: CategoryTreeNode[];
}

/** Groups the flat admin list into a parent-child tree, each sibling group sorted by
 * `display_order` (ties broken by name). A category whose `parent_category_id` doesn't resolve
 * to another row in the list (a data inconsistency, or a retired/deleted parent) is treated as a
 * root rather than silently dropped -- an admin should always be able to find every category
 * somewhere in the tree. */
function buildCategoryTree(items: CategoryRow[]): CategoryTreeNode[] {
  const byId = new Map(items.map((r) => [r.head.id, r]));
  const byParent = new Map<string, CategoryRow[]>();
  const roots: CategoryRow[] = [];

  for (const row of items) {
    const parentId = categoryParentId(row);
    if (parentId && byId.has(parentId)) {
      if (!byParent.has(parentId)) byParent.set(parentId, []);
      byParent.get(parentId)!.push(row);
    } else {
      roots.push(row);
    }
  }

  const byOrder = (a: CategoryRow, b: CategoryRow) =>
    categoryDisplayOrder(a) - categoryDisplayOrder(b) ||
    categoryName(a).localeCompare(categoryName(b));

  const build = (row: CategoryRow): CategoryTreeNode => ({
    row,
    children: (byParent.get(row.head.id) ?? []).sort(byOrder).map(build),
  });

  return roots.sort(byOrder).map(build);
}

function emptyField(): DynamicFieldDraft {
  return { code: "", label: { uz_latn: "" }, fieldType: "text", required: false, options: [] };
}

interface FormPanelProps {
  editing: CategoryRow | null;
  parentOptions: CategoryRow[];
  onClose: () => void;
  onSaved: () => void;
}

function CategoryFormPanel({ editing, parentOptions, onClose, onSaved }: FormPanelProps) {
  const isEditing = editing !== null;
  const existingIcon = editing ? categoryIconUrl(editing) : null;

  const [nameUz, setNameUz] = useState(isEditing ? categoryName(editing) : "");
  const [nameRu, setNameRu] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [path, setPath] = useState(isEditing ? categoryPath(editing).replace(/^\//, "") : "");
  const [pathTouched, setPathTouched] = useState(isEditing);
  const [parentId, setParentId] = useState<string>(
    isEditing ? (categoryParentId(editing) ?? "") : "",
  );
  const [displayOrder, setDisplayOrder] = useState<number>(
    isEditing ? categoryDisplayOrder(editing) : 0,
  );
  const [iconUrl, setIconUrl] = useState<string | null>(existingIcon);
  const [iconUploading, setIconUploading] = useState(false);
  const existingMeta = editing ? categoryPageMeta(editing) : null;
  const [listingKind, setListingKind] = useState<ListingKind>(
    existingMeta?.listingKind ?? "PROPERTY",
  );
  const [heroImageUrl, setHeroImageUrl] = useState<string | null>(
    existingMeta?.heroImageUrl ?? null,
  );
  const [heroUploading, setHeroUploading] = useState(false);
  const [heroTagline, setHeroTagline] = useState(existingMeta?.heroTagline ?? "");
  const [accentColor, setAccentColor] = useState(existingMeta?.accentColor ?? "#6366f1");
  const [fields, setFields] = useState<DynamicFieldDraft[]>([emptyField()]);
  const [fieldsLoaded, setFieldsLoaded] = useState(!isEditing);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEditing || fieldsLoaded) return;
    const formHeadId = categoryFormHeadId(editing);
    if (!formHeadId) {
      setFieldsLoaded(true);
      return;
    }
    getFormDefinitionFields(formHeadId)
      .then(({ name, fields: loadedFields }) => {
        setNameRu(name.ru ?? "");
        setNameEn(name.en ?? "");
        setFields(loadedFields.length > 0 ? loadedFields : [emptyField()]);
      })
      .catch(() => {
        setFields([emptyField()]);
      })
      .finally(() => setFieldsLoaded(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEditing, fieldsLoaded]);

  const effectivePath = pathTouched ? path : slugify(nameUz);

  const updateField = (index: number, patch: Partial<DynamicFieldDraft>) => {
    setFields((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  };

  const handleIconChange = async (file: File | undefined) => {
    if (!file) return;
    setIconUploading(true);
    setError(null);
    try {
      const result = await uploadCategoryIcon(file);
      setIconUrl(result.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ikonka yuklab bo'lmadi.");
    } finally {
      setIconUploading(false);
    }
  };

  const handleHeroImageChange = async (file: File | undefined) => {
    if (!file) return;
    setHeroUploading(true);
    setError(null);
    try {
      const result = await uploadCategoryIcon(file);
      setHeroImageUrl(result.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hero rasmini yuklab bo'lmadi.");
    } finally {
      setHeroUploading(false);
    }
  };

  const canSubmit =
    nameUz.trim().length > 0 &&
    effectivePath.trim().length > 0 &&
    fields.every((f) => f.code.trim() && f.label.uz_latn?.trim());

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const name: LocalizedText = {
        uz_latn: nameUz.trim(),
        ru: nameRu || null,
        en: nameEn || null,
      };
      const cleanFields = fields
        .filter((f) => f.code.trim())
        .map((f) => ({ ...f, code: slugify(f.code) || f.code }));

      if (isEditing) {
        const formHeadId = categoryFormHeadId(editing);
        if (formHeadId) {
          await updateFormDefinitionFields(formHeadId, name, cleanFields);
        }
        await publishCategoryUpdate(editing.head.id, {
          code: editing.head.code,
          name,
          path: `/${effectivePath}`,
          parentCategoryId: parentId || null,
          displayOrder,
          formDefinitionId: formHeadId ?? "",
          iconUrl,
          treeStatus: categoryTreeStatus(editing),
          heroImageUrl,
          heroTagline: heroTagline.trim() || null,
          accentColor,
          listingKind,
        });
      } else {
        const code = slugify(nameUz);
        const formHeadId = await publishNewFormDefinition(`${code}-form`, name, cleanFields);
        await publishNewCategory({
          code,
          name,
          path: `/${effectivePath}`,
          parentCategoryId: parentId || null,
          displayOrder,
          formDefinitionId: formHeadId,
          iconUrl,
          treeStatus: "ACTIVE",
          heroImageUrl,
          heroTagline: heroTagline.trim() || null,
          accentColor,
          listingKind,
        });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi. Qayta urinib ko'ring.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 py-10 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.98 }}
        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl rounded-3xl border border-border bg-card p-6 shadow-elevated sm:p-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-foreground">
              {isEditing ? "Kategoriyani tahrirlash" : "Yangi kategoriya"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Nomi, ikonkasi va dinamik maydonlarini sozlang.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full p-1.5 text-muted-foreground transition hover:bg-muted"
          >
            <X className="size-5" />
          </button>
        </div>

        {!fieldsLoaded ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="size-6 animate-spin" />
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Nomi (o'zbekcha) *
                </label>
                <input
                  value={nameUz}
                  onChange={(e) => setNameUz(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  placeholder="Masalan: Ko'chmas mulk"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">Nomi (ruscha)</label>
                <input
                  value={nameRu}
                  onChange={(e) => setNameRu(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Nomi (inglizcha)
                </label>
                <input
                  value={nameEn}
                  onChange={(e) => setNameEn(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Yo'l (path) — /...
                </label>
                <input
                  value={effectivePath}
                  onChange={(e) => {
                    setPathTouched(true);
                    setPath(e.target.value);
                  }}
                  disabled={isEditing}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm disabled:opacity-60"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Ota-kategoriya (ixtiyoriy)
                </label>
                <select
                  value={parentId}
                  onChange={(e) => setParentId(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                >
                  <option value="">— Yo'q (bosh kategoriya) —</option>
                  {parentOptions
                    .filter((r) => !editing || r.head.id !== editing.head.id)
                    .map((r) => (
                      <option key={r.head.id} value={r.head.id}>
                        {"— ".repeat(categoryDepth(r, parentOptions))}
                        {categoryName(r)}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="text-xs font-medium text-muted-foreground">
                  Tartib raqami (bir xil darajadagi kategoriyalar orasida)
                </label>
                <input
                  type="number"
                  value={displayOrder}
                  onChange={(e) => setDisplayOrder(Number(e.target.value) || 0)}
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  placeholder="0"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Kichik son avval chiqadi. Bir xil ota-kategoriya ostidagi bolalar shu bo'yicha
                  tartiblanadi.
                </p>
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground">Ikonka</label>
              <div className="mt-1 flex items-center gap-3">
                <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border bg-muted">
                  {iconUploading ? (
                    <Loader2 className="size-5 animate-spin text-muted-foreground" />
                  ) : iconUrl ? (
                    <img src={iconUrl} alt="" className="size-full object-cover" />
                  ) : (
                    <ImagePlus className="size-5 text-muted-foreground" />
                  )}
                </div>
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted">
                  Rasm tanlash
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    className="hidden"
                    onChange={(e) => handleIconChange(e.target.files?.[0])}
                  />
                </label>
              </div>
            </div>

            <div className="rounded-2xl border border-border/70 bg-muted/20 p-4">
              <p className="text-xs font-semibold text-foreground">
                Sahifa dizayni (Hero) — ixtiyoriy
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Kategoriya sahifasi qaysi shablon bilan (ko'chmas mulk / tovar / xizmat / obyekt) va
                qanday fonda ochilishini belgilaydi.
              </p>

              <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Sahifa turi</label>
                  <select
                    value={listingKind}
                    onChange={(e) => setListingKind(e.target.value as ListingKind)}
                    className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                  >
                    <option value="PROPERTY">Ko'chmas mulk</option>
                    <option value="GOODS">Tovar / mahsulot</option>
                    <option value="SERVICE">Xizmat ko'rsatuvchi</option>
                    <option value="VENUE">Obyekt / maskan</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Urg'u rangi</label>
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="color"
                      value={accentColor}
                      onChange={(e) => setAccentColor(e.target.value)}
                      className="h-9 w-12 shrink-0 cursor-pointer rounded-lg border border-border bg-background p-1"
                    />
                    <input
                      value={accentColor}
                      onChange={(e) => setAccentColor(e.target.value)}
                      className="w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              </div>

              <div className="mt-4">
                <label className="text-xs font-medium text-muted-foreground">
                  Hero shiori (tagline)
                </label>
                <input
                  value={heroTagline}
                  onChange={(e) => setHeroTagline(e.target.value)}
                  placeholder="Masalan: Qurilish materiallari uchun professional marketplace"
                  className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
                />
              </div>

              <div className="mt-4">
                <label className="text-xs font-medium text-muted-foreground">
                  Hero foni (rasm)
                </label>
                <div className="mt-1 flex items-center gap-3">
                  <div className="flex h-14 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border bg-muted">
                    {heroUploading ? (
                      <Loader2 className="size-5 animate-spin text-muted-foreground" />
                    ) : heroImageUrl ? (
                      <img src={heroImageUrl} alt="" className="size-full object-cover" />
                    ) : (
                      <ImagePlus className="size-5 text-muted-foreground" />
                    )}
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted">
                    Rasm tanlash
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(e) => handleHeroImageChange(e.target.files?.[0])}
                    />
                  </label>
                  {heroImageUrl && (
                    <button
                      type="button"
                      onClick={() => setHeroImageUrl(null)}
                      className="text-xs text-muted-foreground hover:text-destructive"
                    >
                      O'chirish
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-muted-foreground">
                  Dinamik maydonlar (e'lon shakli)
                </label>
                <button
                  type="button"
                  onClick={() => setFields((prev) => [...prev, emptyField()])}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                >
                  <Plus className="size-3.5" /> Maydon qo'shish
                </button>
              </div>
              <div className="mt-2 space-y-3">
                {fields.map((field, i) => (
                  <div
                    key={i}
                    className="grid grid-cols-1 gap-2 rounded-xl border border-border/70 p-3 sm:grid-cols-[1fr_1fr_auto_auto_auto]"
                  >
                    <input
                      value={field.code}
                      onChange={(e) => updateField(i, { code: e.target.value })}
                      placeholder="kod (masalan: xonalar_soni)"
                      className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                    />
                    <input
                      value={field.label.uz_latn ?? ""}
                      onChange={(e) =>
                        updateField(i, { label: { ...field.label, uz_latn: e.target.value } })
                      }
                      placeholder="Ko'rinadigan nomi"
                      className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                    />
                    <select
                      value={field.fieldType}
                      onChange={(e) =>
                        updateField(i, { fieldType: e.target.value as FieldType["fieldType"] })
                      }
                      className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
                    >
                      {FIELD_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1.5 whitespace-nowrap px-1 text-xs text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(i, { required: e.target.checked })}
                      />
                      Majburiy
                    </label>
                    <button
                      type="button"
                      onClick={() => setFields((prev) => prev.filter((_, idx) => idx !== i))}
                      className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                    {(field.fieldType === "select" || field.fieldType === "multiselect") && (
                      <input
                        value={field.options.map((o) => o.value).join(", ")}
                        onChange={(e) =>
                          updateField(i, {
                            options: e.target.value
                              .split(",")
                              .map((v) => v.trim())
                              .filter(Boolean)
                              .map((v) => ({ value: v, label: { uz_latn: v } })),
                          })
                        }
                        placeholder="Variantlar, vergul bilan: 1, 2, 3+"
                        className="col-span-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {error && (
              <p className="rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-border px-4 py-2 text-sm font-medium text-foreground transition hover:bg-muted"
              >
                Bekor qilish
              </button>
              <button
                type="button"
                disabled={!canSubmit || busy}
                onClick={submit}
                className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
              >
                {busy && <Loader2 className="size-4 animate-spin" />}
                {isEditing ? "Saqlash" : "Yaratish va e'lon qilish"}
              </button>
            </div>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

interface ProductRow {
  head: ConfigHeadDto;
  version: ConfigVersionDto | null;
}

function productSnapshot(row: ProductRow): Record<string, unknown> | undefined {
  return (row.version?.snapshot ?? row.version?.definition) as Record<string, unknown> | undefined;
}

function productName(row: ProductRow): string {
  const snapshot = productSnapshot(row) as { descriptor?: { name?: LocalizedText } } | undefined;
  return snapshot?.descriptor?.name?.uz_latn || row.head.code;
}

const PRODUCT_TYPE_LABEL: Record<ProductDraftInput["productType"], string> = {
  SUBSCRIPTION: "Obuna",
  PREMIUM: "Premium joylashtirish",
  FEATURED: "Tavsiya etilgan",
  TOP_PLACEMENT: "Yuqorida ko'rsatish",
  VERIFICATION: "Verifikatsiya",
  BANNER_PLACEMENT: "Banner joyi",
};

const PRODUCT_TYPES = Object.keys(PRODUCT_TYPE_LABEL) as ProductDraftInput["productType"][];

function emptyProductDraft(
  productType: ProductDraftInput["productType"] = "SUBSCRIPTION",
): ProductDraftInput {
  return {
    code: "",
    name: { uz_latn: "" },
    productType,
    priceAmount: "",
    priceCurrency: "UZS",
    termDays: productType === "SUBSCRIPTION" ? 7 : null,
    maxActiveListings: null,
  };
}

function draftFromRow(row: ProductRow): ProductDraftInput {
  const snapshot = productSnapshot(row) as
    | {
        descriptor?: { name?: LocalizedText };
        product_type?: ProductDraftInput["productType"];
        price_amount?: string | number;
        price_currency?: string;
        term_days?: number | null;
        quota_set?: { max_active_listings?: number | null } | null;
      }
    | undefined;
  return {
    code: row.head.code,
    name: snapshot?.descriptor?.name ?? { uz_latn: row.head.code },
    productType: snapshot?.product_type ?? "SUBSCRIPTION",
    priceAmount: String(snapshot?.price_amount ?? ""),
    priceCurrency: snapshot?.price_currency ?? "UZS",
    termDays: snapshot?.term_days ?? null,
    maxActiveListings: snapshot?.quota_set?.max_active_listings ?? null,
  };
}

function TariffFormRow({
  draft,
  onChange,
  onCancel,
  onSave,
  busy,
}: {
  draft: ProductDraftInput;
  onChange: (next: ProductDraftInput) => void;
  onCancel: () => void;
  onSave: () => void;
  busy: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-xl border border-border/70 bg-muted/30 p-4 sm:grid-cols-6">
      <input
        value={draft.code}
        onChange={(e) => onChange({ ...draft, code: e.target.value })}
        placeholder="kod (masalan: sub-weekly)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <input
        value={draft.name.uz_latn ?? ""}
        onChange={(e) => onChange({ ...draft, name: { ...draft.name, uz_latn: e.target.value } })}
        placeholder="Nomi (masalan: Haftalik obuna)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <select
        value={draft.productType}
        onChange={(e) =>
          onChange({ ...draft, productType: e.target.value as ProductDraftInput["productType"] })
        }
        className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs sm:col-span-2"
      >
        {PRODUCT_TYPES.map((t) => (
          <option key={t} value={t}>
            {PRODUCT_TYPE_LABEL[t]}
          </option>
        ))}
      </select>
      <input
        value={draft.termDays ?? ""}
        onChange={(e) =>
          onChange({ ...draft, termDays: e.target.value ? Number(e.target.value) : null })
        }
        placeholder="Amal qilish muddati, kun (ixtiyoriy)"
        inputMode="numeric"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <input
        value={draft.priceAmount}
        onChange={(e) => onChange({ ...draft, priceAmount: e.target.value })}
        placeholder="Narxi (so'm)"
        inputMode="decimal"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
      />
      {draft.productType === "SUBSCRIPTION" && (
        <input
          value={draft.maxActiveListings ?? ""}
          onChange={(e) =>
            onChange({
              ...draft,
              maxActiveListings: e.target.value ? Number(e.target.value) : null,
            })
          }
          placeholder="Max e'lonlar soni (ixtiyoriy)"
          inputMode="numeric"
          className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
        />
      )}
      <div className="flex items-center gap-2 sm:col-span-6 sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted"
        >
          Bekor qilish
        </button>
        <button
          type="button"
          disabled={busy || !draft.code || !draft.name.uz_latn || !draft.priceAmount}
          onClick={onSave}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        >
          {busy && <Loader2 className="size-3.5 animate-spin" />}
          Saqlash
        </button>
      </div>
    </div>
  );
}

function TariffsSection() {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editingHeadId, setEditingHeadId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ProductDraftInput>(emptyProductDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<ProductDraftInput["productType"] | "">("");

  const { data: rows, isLoading } = useQuery({
    queryKey: ["owner-admin", "products"],
    queryFn: listAllProductVersions,
  });

  const visibleRows = (rows ?? []).filter((r) => {
    if (!typeFilter) return true;
    const snapshot = productSnapshot(r) as { product_type?: string } | undefined;
    return snapshot?.product_type === typeFilter;
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["owner-admin", "products"] });
    setAdding(false);
    setEditingHeadId(null);
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (editingHeadId) {
        await publishProductUpdate(editingHeadId, draft);
      } else {
        await publishNewProduct(draft);
      }
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi. Qayta urinib ko'ring.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard
      title="Tariflar va monetizatsiya mahsulotlari"
      icon={CreditCard}
      description="Obuna rejalari, premium/tavsiya etilgan joylashtirish, verifikatsiya va banner narxlari."
      index={1}
      action={
        !adding && (
          <button
            type="button"
            onClick={() => {
              setDraft(emptyProductDraft(typeFilter || "SUBSCRIPTION"));
              setEditingHeadId(null);
              setAdding(true);
            }}
            className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
          >
            <Plus className="size-3.5" /> Yangi mahsulot
          </button>
        )
      }
      noPadding
    >
      <div className="space-y-3 p-6">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setTypeFilter("")}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              typeFilter === ""
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
            }`}
          >
            Barchasi
          </button>
          {PRODUCT_TYPES.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTypeFilter(t)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                typeFilter === t
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
              }`}
            >
              {PRODUCT_TYPE_LABEL[t]}
            </button>
          ))}
        </div>
        {error && (
          <p className="rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
        )}
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {adding && (
          <TariffFormRow
            draft={draft}
            onChange={setDraft}
            onCancel={() => setAdding(false)}
            onSave={save}
            busy={busy}
          />
        )}
        {!isLoading && visibleRows.length === 0 && !adding && (
          <EmptyState
            icon={CreditCard}
            title="Hozircha mahsulot yo'q"
            description="Birinchi tarif yoki monetizatsiya mahsulotini qo'shing."
          />
        )}
        {visibleRows.map((row) =>
          editingHeadId === row.head.id ? (
            <TariffFormRow
              key={row.head.id}
              draft={draft}
              onChange={setDraft}
              onCancel={() => setEditingHeadId(null)}
              onSave={save}
              busy={busy}
            />
          ) : (
            <div
              key={row.head.id}
              className="flex items-center justify-between gap-4 rounded-xl border border-border/70 px-4 py-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-foreground">{productName(row)}</p>
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                    {
                      PRODUCT_TYPE_LABEL[
                        (
                          productSnapshot(row) as
                            { product_type?: ProductDraftInput["productType"] } | undefined
                        )?.product_type ?? "SUBSCRIPTION"
                      ]
                    }
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {row.head.code} · {row.version?.status ?? "—"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setDraft(draftFromRow(row));
                  setEditingHeadId(row.head.id);
                  setAdding(false);
                }}
                className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/70"
              >
                <Pencil className="size-3.5" /> Tahrirlash
              </button>
            </div>
          ),
        )}
      </div>
    </SectionCard>
  );
}

function CategoryTreeRow({
  node,
  depth,
  collapsed,
  onToggleCollapse,
  onToggleStatus,
  toggling,
  onEdit,
}: {
  node: CategoryTreeNode;
  depth: number;
  collapsed: Set<string>;
  onToggleCollapse: (id: string) => void;
  onToggleStatus: (row: CategoryRow) => void;
  toggling: string | null;
  onEdit: (row: CategoryRow) => void;
}) {
  const { row, children } = node;
  const status = categoryTreeStatus(row);
  const icon = categoryIconUrl(row);
  const isCollapsed = collapsed.has(row.head.id);
  const hasChildren = children.length > 0;

  return (
    <>
      <div className="flex items-center justify-between gap-4 px-6 py-4">
        <div className="flex min-w-0 items-center gap-2" style={{ paddingLeft: depth * 24 }}>
          {hasChildren ? (
            <button
              type="button"
              onClick={() => onToggleCollapse(row.head.id)}
              className="shrink-0 rounded p-0.5 text-muted-foreground transition hover:bg-muted"
              aria-label={isCollapsed ? "Yoyish" : "Yig'ish"}
            >
              {isCollapsed ? (
                <ChevronRight className="size-3.5" />
              ) : (
                <ChevronDown className="size-3.5" />
              )}
            </button>
          ) : (
            <span className="size-4 shrink-0" />
          )}
          <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted">
            {icon ? (
              <img src={icon} alt="" className="size-full object-cover" />
            ) : (
              <LayoutGrid className="size-4 text-muted-foreground" />
            )}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-foreground">
              {categoryName(row)}
            </div>
            <div className="truncate text-xs text-muted-foreground">{categoryPath(row)}</div>
          </div>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              status === "ACTIVE" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
            }`}
          >
            {status}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => onToggleStatus(row)}
            disabled={toggling === row.head.id}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
          >
            {toggling === row.head.id ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : status === "ACTIVE" ? (
              <EyeOff className="size-3.5" />
            ) : (
              <Eye className="size-3.5" />
            )}
            {status === "ACTIVE" ? "Yashirish" : "Faollashtirish"}
          </button>
          <button
            type="button"
            onClick={() => onEdit(row)}
            className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/70"
          >
            <Pencil className="size-3.5" /> Tahrirlash
          </button>
        </div>
      </div>
      {!isCollapsed &&
        children.map((child) => (
          <CategoryTreeRow
            key={child.row.head.id}
            node={child}
            depth={depth + 1}
            collapsed={collapsed}
            onToggleCollapse={onToggleCollapse}
            onToggleStatus={onToggleStatus}
            toggling={toggling}
            onEdit={onEdit}
          />
        ))}
    </>
  );
}

/** Lets a super-admin change the panel's own URL segment (`/$ownerAdminSlug`) from inside the
 * panel itself, at will -- stored as the `admin.owner_panel_slug` platform setting
 * (`owner-admin-client.ts`), not anything fixed in this repo's source. Saving redirects to the
 * new URL immediately since the old one stops working the moment the setting changes. */
function OwnerPanelSlugCard({ currentSlug }: { currentSlug: string }) {
  const navigate = useNavigate();
  const [value, setValue] = useState(currentSlug);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setValue(currentSlug), [currentSlug]);

  const trimmed = value.trim().toLowerCase();
  const canSave = !saving && trimmed.length > 0 && trimmed !== currentSlug;

  const save = async () => {
    if (!canSave) return;
    if (!isValidOwnerPanelSlug(trimmed)) {
      setError(
        OWNER_PANEL_RESERVED_SLUGS.has(trimmed)
          ? "Bu manzil allaqachon boshqa sahifa uchun band (masalan, /boss login sahifasi). Boshqa nom tanlang."
          : "Manzil faqat lotin harflari, raqamlar va tire (-) dan iborat bo'lishi kerak.",
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateOwnerPanelSlug(trimmed);
      await navigate({ to: "/$ownerAdminSlug", params: { ownerAdminSlug: trimmed } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlashda xatolik yuz berdi.");
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title="Panel manzili"
      icon={KeyRound}
      description="Bu paneldan faqat shu manzil (URL) orqali kirasiz — xohlagan vaqtingizda o'zgartiring."
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">activehome.uz/</span>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))}
          className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button
          type="button"
          onClick={save}
          disabled={!canSave}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving && <Loader2 className="size-4 animate-spin" />}
          O'zgartirish
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      <p className="mt-2 text-xs text-muted-foreground">
        O'zgartirgach, joriy manzil ({currentSlug}) darhol ishlamay qoladi — yangisini eslab qoling.
      </p>
    </SectionCard>
  );
}

function Page() {
  const { data: account } = useMe();
  const { ownerAdminSlug } = Route.useParams();
  const queryClient = useQueryClient();
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<CategoryRow | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  const {
    data: rows,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["owner-admin", "categories"],
    queryFn: listAllCategoryVersions,
    retry: false,
  });

  const items = rows ?? [];
  const activeCount = items.filter((r) => categoryTreeStatus(r) === "ACTIVE").length;
  const retiredCount = items.length - activeCount;

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["owner-admin"] });
    setPanelOpen(false);
    setEditingRow(null);
  };

  const toggleStatus = async (row: CategoryRow) => {
    setToggling(row.head.id);
    try {
      const nextStatus = categoryTreeStatus(row) === "ACTIVE" ? "RETIRED" : "ACTIVE";
      const formHeadId = categoryFormHeadId(row) ?? "";
      await publishCategoryUpdate(row.head.id, {
        code: row.head.code,
        name: { uz_latn: categoryName(row) },
        path: categoryPath(row),
        parentCategoryId: categoryParentId(row),
        displayOrder: categoryDisplayOrder(row),
        formDefinitionId: formHeadId,
        iconUrl: categoryIconUrl(row),
        treeStatus: nextStatus,
      });
      refresh();
    } finally {
      setToggling(null);
    }
  };

  const toggleCollapse = (id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const tree = buildCategoryTree(items);

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative flex flex-wrap items-center justify-between gap-4 overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <div>
            <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
              <ShieldCheck className="size-3.5" /> Super Admin
            </div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Kategoriyalar boshqaruvi
            </h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Yangi kategoriya qo'shing, dinamik e'lon maydonlarini sozlang — o'zgarishlar bosh
              sahifada va e'lon joylash sahifasida darhol aks etadi.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link
              to="/$ownerAdminSlug/banners"
              params={{ ownerAdminSlug }}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-5 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted"
            >
              <Megaphone className="size-4" /> Bannerlar boshqaruvi
            </Link>
            <button
              type="button"
              onClick={() => {
                setEditingRow(null);
                setPanelOpen(true);
              }}
              className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            >
              <Plus className="size-4" /> Yangi kategoriya
            </button>
          </div>
        </motion.div>

        <OwnerPanelSlugCard currentSlug={ownerAdminSlug} />

        <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard
            icon={LayoutGrid}
            label="Jami kategoriya"
            value={items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Eye}
            label="Faol (ACTIVE)"
            value={activeCount}
            accent="success"
            index={1}
          />
          <StatCard
            icon={EyeOff}
            label="Yashirilgan (RETIRED)"
            value={retiredCount}
            accent="warning"
            index={2}
          />
        </section>

        <SectionCard title="Barcha kategoriyalar" icon={Layers} index={0} noPadding>
          {isLoading && (
            <div className="flex items-center gap-2 px-6 py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}

          {error instanceof ApiError && error.status === 403 && (
            <div className="px-6 py-8 text-sm text-destructive">
              Sizda kategoriyalarni boshqarish uchun ruxsat yo'q.
            </div>
          )}

          {rows && items.length === 0 && (
            <div className="px-6 py-8">
              <EmptyState
                icon={LayoutGrid}
                title="Hozircha kategoriya yo'q"
                description="Birinchi kategoriyangizni qo'shing."
              />
            </div>
          )}

          <div className="divide-y divide-border/70">
            {tree.map((node) => (
              <CategoryTreeRow
                key={node.row.head.id}
                node={node}
                depth={0}
                collapsed={collapsedIds}
                onToggleCollapse={toggleCollapse}
                onToggleStatus={toggleStatus}
                toggling={toggling}
                onEdit={(row) => {
                  setEditingRow(row);
                  setPanelOpen(true);
                }}
              />
            ))}
          </div>
        </SectionCard>

        <TariffsSection />
      </div>

      <AnimatePresence>
        {panelOpen && (
          <CategoryFormPanel
            editing={editingRow}
            parentOptions={items.filter((r) => categoryTreeStatus(r) === "ACTIVE")}
            onClose={() => {
              setPanelOpen(false);
              setEditingRow(null);
            }}
            onSaved={refresh}
          />
        )}
      </AnimatePresence>
    </DashboardShell>
  );
}
