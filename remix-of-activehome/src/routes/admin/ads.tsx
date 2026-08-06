import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Play, Pause, Square, CalendarClock } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminAdsApi, type BannerCampaign } from "@/lib/admin-ads-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/ads")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Reklama kampaniyalari — Admin" }] }),
  component: Page,
});

const campaignsOptions = {
  queryKey: ["admin", "campaigns"],
  queryFn: () => adminAdsApi.listCampaigns(),
};

const STATUS_STYLE: Record<BannerCampaign["status"], string> = {
  DRAFT: "bg-muted text-muted-foreground",
  SCHEDULED: "bg-primary/15 text-primary",
  RUNNING: "bg-success/15 text-success",
  PAUSED: "bg-warning/15 text-warning",
  ENDED: "bg-muted text-muted-foreground",
};

function CampaignRow({ campaign }: { campaign: BannerCampaign }) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "campaigns"] });
  const schedule = useMutation({ mutationFn: () => adminAdsApi.scheduleCampaign(campaign.id), onSuccess: invalidate });
  const pause = useMutation({ mutationFn: () => adminAdsApi.pauseCampaign(campaign.id), onSuccess: invalidate });
  const resume = useMutation({ mutationFn: () => adminAdsApi.resumeCampaign(campaign.id), onSuccess: invalidate });
  const end = useMutation({ mutationFn: () => adminAdsApi.endCampaign(campaign.id), onSuccess: invalidate });

  return (
    <div className="flex flex-col gap-3 border-b border-border p-5 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{campaign.slotKey}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className={`rounded-full px-2 py-0.5 font-semibold ${STATUS_STYLE[campaign.status]}`}>
            {campaign.status}
          </span>
          <span>
            {new Date(campaign.scheduleStart).toLocaleDateString()} → {new Date(campaign.scheduleEnd).toLocaleDateString()}
          </span>
          <span>Priority: {campaign.priority}</span>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {campaign.status === "DRAFT" && (
          <button
            onClick={() => schedule.mutate()}
            disabled={schedule.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 disabled:opacity-50"
          >
            <CalendarClock className="size-3.5" /> Rejalashtirish
          </button>
        )}
        {campaign.status === "RUNNING" && (
          <button
            onClick={() => pause.mutate()}
            disabled={pause.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-warning/15 px-3 py-1.5 text-xs font-semibold text-warning hover:bg-warning/25 disabled:opacity-50"
          >
            <Pause className="size-3.5" /> To'xtatish
          </button>
        )}
        {campaign.status === "PAUSED" && (
          <button
            onClick={() => resume.mutate()}
            disabled={resume.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-success/15 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/25 disabled:opacity-50"
          >
            <Play className="size-3.5" /> Davom ettirish
          </button>
        )}
        {(campaign.status === "RUNNING" || campaign.status === "SCHEDULED" || campaign.status === "PAUSED") && (
          <button
            onClick={() => end.mutate()}
            disabled={end.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/25 disabled:opacity-50"
          >
            <Square className="size-3.5" /> Yakunlash
          </button>
        )}
      </div>
    </div>
  );
}

function CreateCampaignForm() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [slotKey, setSlotKey] = useState("homepage-hero");
  const [creativeMediaAssetId, setCreativeMediaAssetId] = useState("");
  const [entitlementId, setEntitlementId] = useState("");
  const [scheduleStart, setScheduleStart] = useState("");
  const [scheduleEnd, setScheduleEnd] = useState("");
  const [priority, setPriority] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      adminAdsApi.createCampaign({
        slotKey,
        creativeMediaAssetId,
        entitlementId,
        scheduleStart: new Date(scheduleStart).toISOString(),
        scheduleEnd: new Date(scheduleEnd).toISOString(),
        priority,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "campaigns"] });
      setOpen(false);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik"),
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
      >
        <Plus className="size-4" /> Yangi kampaniya
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="mb-6 space-y-3 rounded-2xl border border-border bg-card p-5"
    >
      <p className="text-xs text-muted-foreground">
        Kampaniya `entitlementId` uchun avval BANNER_SLOT_BOOKING turidagi haqiqiy entitlement mavjud bo'lishi kerak
        (billing orqali). `creativeMediaAssetId` esa avvaldan yuklangan, tekshiruvdan o'tgan media rasm bo'lishi kerak.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Slot key
          <input value={slotKey} onChange={(e) => setSlotKey(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Priority
          <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Creative media asset ID
          <input value={creativeMediaAssetId} onChange={(e) => setCreativeMediaAssetId(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Entitlement ID
          <input value={entitlementId} onChange={(e) => setEntitlementId(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Boshlanish
          <input type="datetime-local" value={scheduleStart} onChange={(e) => setScheduleStart(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Tugash
          <input type="datetime-local" value={scheduleEnd} onChange={(e) => setScheduleEnd(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={mutation.isPending} className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50">
          Yaratish
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-full border border-border px-4 py-2 text-xs font-semibold text-foreground hover:bg-muted">
          Bekor qilish
        </button>
      </div>
    </form>
  );
}

function Page() {
  const { data, isLoading, error } = useQuery(campaignsOptions);

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-foreground">Reklama kampaniyalari</h1>
          <p className="mt-1 text-sm text-muted-foreground">Banner slotlarini yaratish, rejalashtirish va boshqarish.</p>
        </div>
      </div>

      <CreateCampaignForm />

      {error ? (
        <EmptyState
          title={error instanceof ApiError && error.problem.status === 403 ? "Ruxsat yo'q" : "Xatolik"}
          description={error instanceof ApiError ? error.problem.detail ?? error.problem.title : String(error)}
        />
      ) : isLoading ? (
        <div className="h-40 animate-pulse rounded-2xl bg-muted" />
      ) : data && data.length > 0 ? (
        <div className="rounded-2xl border border-border bg-card">
          {data.map((c) => (
            <CampaignRow key={c.id} campaign={c} />
          ))}
        </div>
      ) : (
        <EmptyState title="Kampaniyalar yo'q" description="Hali birorta reklama kampaniyasi yaratilmagan." />
      )}
    </AdminShell>
  );
}
