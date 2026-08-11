import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  Megaphone,
  Plus,
  Pencil,
  Loader2,
  ShieldCheck,
  LayoutTemplate,
  Play,
  Pause,
  Square,
  CalendarClock,
  X,
  ImagePlus,
  ArrowLeft,
} from "lucide-react";
import { requireOwnerAdminSlug } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";
import { uploadMedia } from "@/lib/media-client";
import { catalogClient } from "@/lib/catalog-client";
import {
  listAllPlacementSlotVersions,
  publishNewPlacementSlot,
  publishPlacementSlotUpdate,
  type PlacementSlotDraftInput,
  type ConfigHeadDto,
  type ConfigVersionDto,
} from "@/lib/owner-admin-client";
import {
  listCampaigns,
  createCampaign,
  updateCampaign,
  scheduleCampaign,
  pauseCampaign,
  resumeCampaign,
  endCampaign,
  type BannerCampaign,
  type BannerCampaignCreateInput,
  type CampaignStatus,
} from "@/lib/ads-client";

export const Route = createFileRoute("/$ownerAdminSlug/banners")({
  beforeLoad: requireOwnerAdminSlug,
  ssr: false,
  head: () => ({ meta: [{ title: "Bannerlar boshqaruvi — ActiveHome" }] }),
  component: Page,
});

const PAGE_ZONES = [
  "HOMEPAGE_HERO",
  "HOMEPAGE_FEATURED_CATEGORIES",
  "HOMEPAGE_PROMOTED_LISTINGS",
  "HOMEPAGE_BANNER",
  "CATEGORY_PAGE_TOP",
  "SEARCH_RESULTS_TOP",
  "LISTING_DETAIL_SIDEBAR",
] as const;

const STATUS_LABEL: Record<CampaignStatus, string> = {
  DRAFT: "Qoralama",
  SCHEDULED: "Rejalashtirilgan",
  RUNNING: "Faol",
  PAUSED: "To'xtatilgan",
  ENDED: "Tugagan",
};

const STATUS_TONE: Record<CampaignStatus, string> = {
  DRAFT: "bg-muted text-muted-foreground",
  SCHEDULED: "bg-primary/10 text-primary",
  RUNNING: "bg-success/10 text-success",
  PAUSED: "bg-warning/10 text-warning",
  ENDED: "bg-muted text-muted-foreground",
};

interface SlotRow {
  head: ConfigHeadDto;
  version: ConfigVersionDto | null;
}

function slotSnapshot(row: SlotRow): Record<string, unknown> | undefined {
  return (row.version?.snapshot ?? row.version?.definition) as Record<string, unknown> | undefined;
}

function slotName(row: SlotRow): string {
  const snapshot = slotSnapshot(row) as
    { descriptor?: { name?: { uz_latn?: string } } } | undefined;
  return snapshot?.descriptor?.name?.uz_latn || row.head.code;
}

function slotKeyOf(row: SlotRow): string {
  const snapshot = slotSnapshot(row) as { slot_key?: string } | undefined;
  return snapshot?.slot_key ?? row.head.code;
}

function emptySlotDraft(): PlacementSlotDraftInput {
  return {
    code: "",
    name: { uz_latn: "" },
    slotKey: "",
    pageZone: PAGE_ZONES[0],
    widthPx: null,
    heightPx: null,
  };
}

function SlotFormRow({
  draft,
  onChange,
  onCancel,
  onSave,
  busy,
}: {
  draft: PlacementSlotDraftInput;
  onChange: (next: PlacementSlotDraftInput) => void;
  onCancel: () => void;
  onSave: () => void;
  busy: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-xl border border-border/70 bg-muted/30 p-4 sm:grid-cols-6">
      <input
        value={draft.code}
        onChange={(e) => onChange({ ...draft, code: e.target.value })}
        placeholder="kod (masalan: homepage-hero)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <input
        value={draft.name.uz_latn ?? ""}
        onChange={(e) => onChange({ ...draft, name: { ...draft.name, uz_latn: e.target.value } })}
        placeholder="Nomi"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <input
        value={draft.slotKey}
        onChange={(e) => onChange({ ...draft, slotKey: e.target.value })}
        placeholder="SlotKey (masalan: home-hero-1)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs sm:col-span-2"
      />
      <select
        value={draft.pageZone}
        onChange={(e) => onChange({ ...draft, pageZone: e.target.value })}
        className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs sm:col-span-2"
      >
        {PAGE_ZONES.map((z) => (
          <option key={z} value={z}>
            {z}
          </option>
        ))}
      </select>
      <input
        type="number"
        value={draft.widthPx ?? ""}
        onChange={(e) =>
          onChange({ ...draft, widthPx: e.target.value ? Number(e.target.value) : null })
        }
        placeholder="Kenglik (px)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
      />
      <input
        type="number"
        value={draft.heightPx ?? ""}
        onChange={(e) =>
          onChange({ ...draft, heightPx: e.target.value ? Number(e.target.value) : null })
        }
        placeholder="Balandlik (px)"
        className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
      />
      <div className="flex items-center gap-2 sm:col-span-2 sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted"
        >
          Bekor qilish
        </button>
        <button
          type="button"
          disabled={busy || !draft.code || !draft.name.uz_latn || !draft.slotKey}
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

function PlacementSlotsSection() {
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [editingHeadId, setEditingHeadId] = useState<string | null>(null);
  const [draft, setDraft] = useState<PlacementSlotDraftInput>(emptySlotDraft());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["owner-admin", "placement-slots"],
    queryFn: listAllPlacementSlotVersions,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["owner-admin", "placement-slots"] });
    setAdding(false);
    setEditingHeadId(null);
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      if (editingHeadId) {
        await publishPlacementSlotUpdate(editingHeadId, draft);
      } else {
        await publishNewPlacementSlot(draft);
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
      title="Banner joylari (Placement Slots)"
      icon={LayoutTemplate}
      description="Kampaniyalar shu joylarga bog'lanadi — sahifa, hudud va o'lchamini shu yerda belgilang."
      index={0}
      action={
        !adding && (
          <button
            type="button"
            onClick={() => {
              setDraft(emptySlotDraft());
              setEditingHeadId(null);
              setAdding(true);
            }}
            className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
          >
            <Plus className="size-3.5" /> Yangi joy
          </button>
        )
      }
      noPadding
    >
      <div className="space-y-3 p-6">
        {error && (
          <p className="rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
        )}
        {isLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {adding && (
          <SlotFormRow
            draft={draft}
            onChange={setDraft}
            onCancel={() => setAdding(false)}
            onSave={save}
            busy={busy}
          />
        )}
        {!isLoading && rows.length === 0 && !adding && (
          <EmptyState
            icon={LayoutTemplate}
            title="Hozircha banner joyi yo'q"
            description="Kampaniya yaratishdan oldin kamida bitta joy belgilang."
          />
        )}
        {rows.map((row) =>
          editingHeadId === row.head.id ? (
            <SlotFormRow
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
                <p className="text-sm font-semibold text-foreground">{slotName(row)}</p>
                <p className="text-xs text-muted-foreground">
                  SlotKey: <span className="font-mono">{slotKeyOf(row)}</span> ·{" "}
                  {row.version?.status ?? "—"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  const snapshot = slotSnapshot(row) as
                    | {
                        descriptor?: { name?: { uz_latn?: string } };
                        slot_key?: string;
                        page_zone?: string;
                        width_px?: number | null;
                        height_px?: number | null;
                      }
                    | undefined;
                  setDraft({
                    code: row.head.code,
                    name: { uz_latn: snapshot?.descriptor?.name?.uz_latn ?? row.head.code },
                    slotKey: snapshot?.slot_key ?? row.head.code,
                    pageZone: snapshot?.page_zone ?? PAGE_ZONES[0],
                    widthPx: snapshot?.width_px ?? null,
                    heightPx: snapshot?.height_px ?? null,
                  });
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

// -- datetime-local <-> ISO helpers -------------------------------------------------------------

function toLocalInputValue(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(value: string): string {
  return new Date(value).toISOString();
}

// -- campaign create/edit panel ------------------------------------------------------------------

/** The 5 slotKeys `routes/index.tsx`'s `AdSlot` placements actually query -- picking one of
 * these means "put it live on the homepage" with zero manual code/pageZone/width/height typing.
 * A placement slot for the chosen key is auto-created behind the scenes on submit if it doesn't
 * exist yet (see `ensureSlotExists` in `CampaignFormPanel`). An admin who needs a non-homepage
 * placement (category page, search results, etc.) still uses the "Banner joylari" section above
 * to hand-create a custom slot, then it appears in the "Boshqa joy" group of the dropdown below. */
const KNOWN_HOMEPAGE_SLOTS: { slotKey: string; label: string }[] = [
  { slotKey: "HOMEPAGE_BANNER_1", label: "Bosh sahifa banner 1 (kategoriyalardan keyin)" },
  { slotKey: "HOMEPAGE_BANNER_2", label: "Bosh sahifa banner 2 (xarita oldidan)" },
  { slotKey: "HOMEPAGE_BANNER_3", label: "Bosh sahifa banner 3 (ekotizimdan keyin)" },
  { slotKey: "HOMEPAGE_SIDEBAR_LEFT", label: "Chap yon panel (katta ekranlarda)" },
  { slotKey: "HOMEPAGE_SIDEBAR_RIGHT", label: "O'ng yon panel (katta ekranlarda)" },
];

function defaultScheduleEnd(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString();
}

interface CampaignPanelProps {
  editing: BannerCampaign | null;
  slots: SlotRow[];
  onClose: () => void;
  onSaved: () => void;
}

function CampaignFormPanel({ editing, slots, onClose, onSaved }: CampaignPanelProps) {
  const queryClient = useQueryClient();
  const isEditing = editing !== null;
  const knownSlotKeys = new Set(KNOWN_HOMEPAGE_SLOTS.map((s) => s.slotKey));
  const customSlots = slots.filter((s) => !knownSlotKeys.has(slotKeyOf(s)));
  const [slotKey, setSlotKey] = useState(
    editing?.slotKey ?? KNOWN_HOMEPAGE_SLOTS[0].slotKey,
  );
  const [creativeMediaAssetId, setCreativeMediaAssetId] = useState(
    editing?.creativeMediaAssetId ?? "",
  );
  const [creativePreview, setCreativePreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [scheduleStart, setScheduleStart] = useState(
    editing ? toLocalInputValue(editing.scheduleStart) : toLocalInputValue(new Date().toISOString()),
  );
  const [scheduleEnd, setScheduleEnd] = useState(
    editing ? toLocalInputValue(editing.scheduleEnd) : toLocalInputValue(defaultScheduleEnd()),
  );
  const [priority, setPriority] = useState(editing?.priority ?? 0);
  const [geo, setGeo] = useState(editing?.targeting?.geo ?? "");
  const [targetUrl, setTargetUrl] = useState(editing?.targetUrl ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Publishes a placement slot for `slotKey` if none exists yet -- lets the campaign form work
   * for a known homepage placement with zero prior setup in "Banner joylari". A no-op (skips the
   * extra round trip) when the slot is already there, whether from a prior quick-add or a
   * hand-created custom one. */
  const ensureSlotExists = async (key: string) => {
    if (slots.some((s) => slotKeyOf(s) === key)) return;
    const known = KNOWN_HOMEPAGE_SLOTS.find((s) => s.slotKey === key);
    await publishNewPlacementSlot({
      code: key.toLowerCase().replace(/_/g, "-"),
      name: { uz_latn: known?.label ?? key },
      slotKey: key,
      pageZone: "HOMEPAGE_BANNER",
      widthPx: null,
      heightPx: null,
    });
    queryClient.invalidateQueries({ queryKey: ["owner-admin", "placement-slots"] });
  };

  const handleCreativeChange = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadMedia(file, "BANNER_CREATIVE");
      setCreativeMediaAssetId(uploaded.mediaAssetId);
      setCreativePreview(uploaded.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kreativ yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  const canSubmit =
    slotKey.trim().length > 0 &&
    creativeMediaAssetId.trim().length > 0 &&
    scheduleStart.length > 0 &&
    scheduleEnd.length > 0;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const input: BannerCampaignCreateInput = {
        slotKey,
        creativeMediaAssetId,
        scheduleStart: fromLocalInputValue(scheduleStart),
        scheduleEnd: fromLocalInputValue(scheduleEnd),
        priority,
        targeting: { geo: geo || null },
        targetUrl: targetUrl.trim() || null,
      };
      if (isEditing) {
        await updateCampaign(editing.id, {
          creativeMediaAssetId: input.creativeMediaAssetId,
          scheduleStart: input.scheduleStart,
          scheduleEnd: input.scheduleEnd,
          priority: input.priority,
          targeting: input.targeting,
          targetUrl: input.targetUrl,
        });
      } else {
        await ensureSlotExists(slotKey);
        const created = await createCampaign(input);
        // Quick-add path -- go straight to SCHEDULED/RUNNING so the admin doesn't need a second
        // click; a failure here just leaves it as a real, retryable DRAFT (the campaign list's
        // own "Rejalashtirish" action), never a lost/duplicated campaign.
        await scheduleCampaign(created.id).catch(() => {});
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
        className="w-full max-w-xl rounded-3xl border border-border bg-card p-6 shadow-elevated sm:p-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-semibold text-foreground">
              {isEditing ? "Kampaniyani tahrirlash" : "Yangi banner kampaniyasi"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Faqat DRAFT holatdagi kampaniyalarni tahrirlash mumkin.
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

        <div className="mt-6 space-y-5">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Banner joyi *</label>
            <select
              value={slotKey}
              onChange={(e) => setSlotKey(e.target.value)}
              disabled={isEditing}
              className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm disabled:opacity-60"
            >
              <optgroup label="Bosh sahifa">
                {KNOWN_HOMEPAGE_SLOTS.map((s) => (
                  <option key={s.slotKey} value={s.slotKey}>
                    {s.label}
                  </option>
                ))}
              </optgroup>
              {customSlots.length > 0 && (
                <optgroup label="Boshqa joy">
                  {customSlots.map((s) => (
                    <option key={s.head.id} value={slotKeyOf(s)}>
                      {slotName(s)} ({slotKeyOf(s)})
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Bosh sahifa joylari avtomatik tayyorlanadi — alohida joy yaratish shart emas. Boshqa
              sahifa uchun avval yuqoridagi "Banner joylari" bo'limida joy yarating.
            </p>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">
              Kreativ (rasm yoki GIF) *
            </label>
            <div className="mt-1 flex items-center gap-3">
              <div className="flex h-16 w-28 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border bg-muted">
                {uploading ? (
                  <Loader2 className="size-5 animate-spin text-muted-foreground" />
                ) : creativePreview ? (
                  <img src={creativePreview} alt="" className="size-full object-cover" />
                ) : (
                  <ImagePlus className="size-5 text-muted-foreground" />
                )}
              </div>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted">
                Rasm tanlash
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={(e) => handleCreativeChange(e.target.files?.[0])}
                />
              </label>
              {creativeMediaAssetId && !creativePreview && (
                <span className="text-xs text-muted-foreground">Kreativ biriktirilgan</span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Boshlanishi *</label>
              <input
                type="datetime-local"
                value={scheduleStart}
                onChange={(e) => setScheduleStart(e.target.value)}
                className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">Tugashi *</label>
              <input
                type="datetime-local"
                value={scheduleEnd}
                onChange={(e) => setScheduleEnd(e.target.value)}
                className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground">Ustuvorlik</label>
              <input
                type="number"
                min={0}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value) || 0)}
                className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground">
                Hudud (geo, ixtiyoriy)
              </label>
              <input
                value={geo}
                onChange={(e) => setGeo(e.target.value)}
                placeholder="Masalan: TASHKENT"
                className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">
              Havola (bosilganda ochiladigan sahifa, ixtiyoriy)
            </label>
            <input
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://..."
              className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Bo'sh qoldirilsa, banner bosilmaydigan oddiy rasm sifatida ko'rinadi.
            </p>
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
              {isEditing ? "Saqlash" : "Joylashtirish"}
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

function CampaignRow({
  campaign,
  onEdit,
  onAction,
  busy,
}: {
  campaign: BannerCampaign;
  onEdit: (c: BannerCampaign) => void;
  onAction: (c: BannerCampaign, action: "schedule" | "pause" | "resume" | "end") => void;
  busy: string | null;
}) {
  const isBusy = busy === campaign.id;
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground">{campaign.slotKey}</span>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_TONE[campaign.status]}`}
          >
            {STATUS_LABEL[campaign.status]}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {new Date(campaign.scheduleStart).toLocaleString("uz-UZ")} —{" "}
          {new Date(campaign.scheduleEnd).toLocaleString("uz-UZ")} · Ustuvorlik {campaign.priority}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {campaign.status === "DRAFT" && (
          <>
            <button
              type="button"
              onClick={() => onEdit(campaign)}
              className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/70"
            >
              <Pencil className="size-3.5" /> Tahrirlash
            </button>
            <button
              type="button"
              disabled={isBusy}
              onClick={() => onAction(campaign, "schedule")}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            >
              {isBusy ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <CalendarClock className="size-3.5" />
              )}
              Rejalashtirish
            </button>
          </>
        )}
        {(campaign.status === "SCHEDULED" || campaign.status === "RUNNING") && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => onAction(campaign, "pause")}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
          >
            {isBusy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Pause className="size-3.5" />
            )}
            To'xtatish
          </button>
        )}
        {campaign.status === "PAUSED" && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => onAction(campaign, "resume")}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
          >
            {isBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            Davom ettirish
          </button>
        )}
        {campaign.status !== "ENDED" && campaign.status !== "DRAFT" && (
          <button
            type="button"
            disabled={isBusy}
            onClick={() => onAction(campaign, "end")}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-destructive transition hover:bg-destructive/10 disabled:opacity-50"
          >
            {isBusy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Square className="size-3.5" />
            )}
            Yakunlash
          </button>
        )}
      </div>
    </div>
  );
}

function CampaignsSection({ slots }: { slots: SlotRow[] }) {
  const queryClient = useQueryClient();
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<BannerCampaign | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const {
    data: campaigns = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["owner-admin", "campaigns"],
    queryFn: () => listCampaigns(),
    retry: false,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["owner-admin", "campaigns"] });
    setPanelOpen(false);
    setEditingCampaign(null);
  };

  const runAction = async (
    campaign: BannerCampaign,
    action: "schedule" | "pause" | "resume" | "end",
  ) => {
    setBusyId(campaign.id);
    setActionError(null);
    try {
      const fn = {
        schedule: scheduleCampaign,
        pause: pauseCampaign,
        resume: resumeCampaign,
        end: endCampaign,
      }[action];
      await fn(campaign.id);
      queryClient.invalidateQueries({ queryKey: ["owner-admin", "campaigns"] });
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <SectionCard
        title="Banner kampaniyalari"
        icon={Megaphone}
        description="Kreativ, jadval va ustuvorlikni sozlab, kampaniyani rejalashtiring."
        index={1}
        action={
          <button
            type="button"
            onClick={() => {
              setEditingCampaign(null);
              setPanelOpen(true);
            }}
            className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          >
            <Plus className="size-3.5" /> Yangi kampaniya
          </button>
        }
        noPadding
      >
        {actionError && (
          <p className="mx-6 mt-4 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {actionError}
          </p>
        )}
        {isLoading && (
          <div className="flex items-center gap-2 px-6 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {error instanceof ApiError && error.status === 403 && (
          <div className="px-6 py-8 text-sm text-destructive">
            Sizda kampaniyalarni boshqarish uchun ruxsat yo'q.
          </div>
        )}
        {!isLoading && campaigns.length === 0 && (
          <div className="px-6 py-8">
            <EmptyState
              icon={Megaphone}
              title="Hozircha kampaniya yo'q"
              description="Birinchi banner kampaniyangizni yarating."
            />
          </div>
        )}
        <div className="divide-y divide-border/70">
          {campaigns.map((c) => (
            <CampaignRow
              key={c.id}
              campaign={c}
              onEdit={(camp) => {
                setEditingCampaign(camp);
                setPanelOpen(true);
              }}
              onAction={runAction}
              busy={busyId}
            />
          ))}
        </div>
      </SectionCard>

      <AnimatePresence>
        {panelOpen && (
          <CampaignFormPanel
            editing={editingCampaign}
            slots={slots}
            onClose={() => {
              setPanelOpen(false);
              setEditingCampaign(null);
            }}
            onSaved={refresh}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function Page() {
  const { data: account } = useMe();
  const { ownerAdminSlug } = Route.useParams();
  const { data: slotRows = [] } = useQuery({
    queryKey: ["owner-admin", "placement-slots"],
    queryFn: listAllPlacementSlotVersions,
  });
  const { data: campaigns = [] } = useQuery({
    queryKey: ["owner-admin", "campaigns"],
    queryFn: () => listCampaigns(),
    retry: false,
  });
  // Prefetched so the category-targeting affordance can grow later without another round trip.
  useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });

  const runningCount = campaigns.filter((c) => c.status === "RUNNING").length;
  const scheduledCount = campaigns.filter((c) => c.status === "SCHEDULED").length;

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
            <Link
              to="/$ownerAdminSlug"
              params={{ ownerAdminSlug }}
              className="mb-2 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-3.5" /> Kategoriyalar boshqaruviga qaytish
            </Link>
            <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
              <ShieldCheck className="size-3.5" /> Super Admin
            </div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Bannerlar boshqaruvi
            </h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Banner joylarini belgilang va kampaniyalarni rejalashtiring, to'xtating yoki
              yakunlang.
            </p>
          </div>
        </motion.div>

        <section className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <StatCard
            icon={LayoutTemplate}
            label="Banner joylari"
            value={slotRows.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Play}
            label="Faol kampaniyalar"
            value={runningCount}
            accent="success"
            index={1}
          />
          <StatCard
            icon={CalendarClock}
            label="Rejalashtirilgan"
            value={scheduledCount}
            accent="warning"
            index={2}
          />
        </section>

        <PlacementSlotsSection />
        <CampaignsSection slots={slotRows} />
      </div>
    </DashboardShell>
  );
}
