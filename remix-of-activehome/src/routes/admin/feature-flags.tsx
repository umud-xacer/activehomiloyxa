import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ToggleLeft, Loader2, CheckCircle2, AlertCircle, ListChecks, Info } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import {
  adminConfigApi,
  FIELD_TYPES,
  VALIDATOR_TYPES,
  SORT_OPTIONS,
  RENDERING_HINTS,
  PERMISSION_KEYS,
  SETTINGS_SCHEMA,
} from "@/lib/admin-config-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/feature-flags")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Imkoniyatlar (Feature Flags) — Admin" }] }),
  component: Page,
});

function Pills({ items }: { items: readonly string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((v) => (
        <span key={v} className="rounded-full bg-muted px-2.5 py-1 font-mono text-[11px] text-foreground/80">
          {v}
        </span>
      ))}
    </div>
  );
}

function SettingsPanel() {
  const queryClient = useQueryClient();
  const { data: heads } = useQuery({
    queryKey: ["admin", "config-heads", "platform-settings"],
    queryFn: () => adminConfigApi.listHeads("platform-settings"),
  });
  const head = heads?.[0];

  const { data: version, isLoading } = useQuery({
    queryKey: ["admin", "platform-settings-version", head?.id, head?.currentVersionId],
    queryFn: () => adminConfigApi.getVersion("platform-settings", head!.id, head!.currentVersionId as string),
    enabled: !!head?.currentVersionId,
  });

  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (patch: Record<string, unknown>) => {
      if (!head || !version) throw new Error("Ma'lumot yuklanmadi");
      return adminConfigApi.updatePlatformSettings(head.id, version.definition, patch);
    },
    onSuccess: (_v, patch) => {
      setError(null);
      setOk(Object.keys(patch)[0]);
      queryClient.invalidateQueries({ queryKey: ["admin", "config-heads", "platform-settings"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "platform-settings-version"] });
      setTimeout(() => setOk(null), 2000);
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Saqlab bo'lmadi"),
    onSettled: () => setPendingKey(null),
  });

  if (!heads) return <div className="h-40 animate-pulse rounded-2xl bg-muted" />;
  if (!head) return <EmptyState title="Platforma sozlamalari topilmadi" description="Konfiguratsiya bo'limida yaratilishi kerak." />;
  if (isLoading || !version) return <div className="h-40 animate-pulse rounded-2xl bg-muted" />;

  const settings = (version.definition.settings as Record<string, unknown>) ?? {};

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
        <ToggleLeft className="size-4 text-primary" /> Imkoniyatlar va sozlamalar
      </div>
      <div className="divide-y divide-border">
        {SETTINGS_SCHEMA.map((s) => {
          const value = settings[s.key];
          const saving = mutation.isPending && pendingKey === s.key;
          return (
            <div key={s.key} className="flex items-center justify-between py-3">
              <div>
                <div className="text-sm text-foreground">{s.label}</div>
                <div className="font-mono text-[11px] text-muted-foreground">{s.key}</div>
              </div>
              {s.type === "bool" ? (
                <button
                  onClick={() => {
                    setPendingKey(s.key);
                    mutation.mutate({ [s.key]: !value });
                  }}
                  disabled={mutation.isPending}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition disabled:opacity-50 ${value ? "bg-primary" : "bg-muted"}`}
                >
                  {saving ? (
                    <Loader2 className="absolute inset-0 m-auto size-3.5 animate-spin text-white" />
                  ) : (
                    <span
                      className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition ${value ? "left-[22px]" : "left-0.5"}`}
                    />
                  )}
                </button>
              ) : (
                <input
                  type="number"
                  defaultValue={value as number}
                  onBlur={(e) => {
                    const num = Number(e.target.value);
                    if (num !== value) {
                      setPendingKey(s.key);
                      mutation.mutate({ [s.key]: num });
                    }
                  }}
                  className="w-24 rounded-lg border border-border bg-background px-2.5 py-1.5 text-right text-sm"
                />
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" /> {error}
        </div>
      )}
      {ok && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
          <CheckCircle2 className="size-4" /> Saqlandi va nashr qilindi
        </div>
      )}
    </div>
  );
}

function WhitelistReference() {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
        <ListChecks className="size-4 text-primary" /> Whitelist Registry (ma'lumot uchun)
      </div>
      <p className="mb-4 flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        Bu qiymatlar backend kodida qattiq belgilangan (konfiguratsiya emas) — shu sabab bu yerdan
        tahrirlab bo'lmaydi. Yangi qiymat qo'shish backend o'zgarishini talab qiladi.
      </p>
      <div className="space-y-4">
        <div>
          <div className="mb-1.5 text-xs font-semibold text-foreground/70">Maydon turlari (field types)</div>
          <Pills items={FIELD_TYPES} />
        </div>
        <div>
          <div className="mb-1.5 text-xs font-semibold text-foreground/70">Validatorlar</div>
          <Pills items={VALIDATOR_TYPES} />
        </div>
        <div>
          <div className="mb-1.5 text-xs font-semibold text-foreground/70">Saralash variantlari</div>
          <Pills items={SORT_OPTIONS} />
        </div>
        <div>
          <div className="mb-1.5 text-xs font-semibold text-foreground/70">Ko'rinish maslahatlari (rendering hints)</div>
          <Pills items={RENDERING_HINTS} />
        </div>
        <div>
          <div className="mb-1.5 text-xs font-semibold text-foreground/70">Ruxsat kalitlari (permission keys)</div>
          <Pills items={PERMISSION_KEYS} />
        </div>
      </div>
    </div>
  );
}

function Page() {
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Imkoniyatlar (Feature Flags)</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platforma darajasidagi yoqish/o'chirish sozlamalari va backend whitelist ma'lumotnomasi.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SettingsPanel />
        <WhitelistReference />
      </div>
    </AdminShell>
  );
}
