import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, CheckCircle2, UploadCloud } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import {
  adminConfigApi,
  CONFIG_ENTITY_TYPES,
  type ConfigEntityType,
  type ConfigHead,
} from "@/lib/admin-config-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/config")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Konfiguratsiya — Admin" }] }),
  component: Page,
});

const HEAD_STATUS_STYLE: Record<ConfigHead["status"], string> = {
  DRAFT: "bg-muted text-muted-foreground",
  PUBLISHED: "bg-success/15 text-success",
  DEPRECATED: "bg-warning/15 text-warning",
  ARCHIVED: "bg-muted text-muted-foreground",
};

function NewHeadForm({ entityType, onCreated }: { entityType: ConfigEntityType; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [businessOwner, setBusinessOwner] = useState("Super Administrator");
  const [definition, setDefinition] = useState('{\n  "descriptor": { "name": { "uz_latn": "" } }\n}');
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => adminConfigApi.createDraft(entityType, { code, businessOwner, definition: JSON.parse(definition) }),
    onSuccess: () => {
      onCreated();
      setOpen(false);
      setError(null);
    },
    onError: (err) => {
      if (err instanceof SyntaxError) setError("Definition — noto'g'ri JSON");
      else setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik");
    },
  });

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
      >
        <Plus className="size-4" /> Yangi {CONFIG_ENTITY_TYPES.find((t) => t.value === entityType)?.label}
      </button>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        try {
          JSON.parse(definition);
        } catch {
          setError("Definition — noto'g'ri JSON");
          return;
        }
        mutation.mutate();
      }}
      className="mb-6 space-y-3 rounded-2xl border border-border bg-card p-5"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block text-xs">
          Code (noyob kod)
          <input value={code} onChange={(e) => setCode(e.target.value)} required className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
        <label className="block text-xs">
          Business owner
          <input value={businessOwner} onChange={(e) => setBusinessOwner(e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
        </label>
      </div>
      <label className="block text-xs">
        Definition (JSON)
        <textarea
          value={definition}
          onChange={(e) => setDefinition(e.target.value)}
          rows={8}
          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
        />
      </label>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={mutation.isPending} className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50">
          Yaratish (draft)
        </button>
        <button type="button" onClick={() => setOpen(false)} className="rounded-full border border-border px-4 py-2 text-xs font-semibold text-foreground hover:bg-muted">
          Bekor qilish
        </button>
      </div>
    </form>
  );
}

function HeadDetail({ entityType, head }: { entityType: ConfigEntityType; head: ConfigHead }) {
  const queryClient = useQueryClient();
  const invalidateVersions = () => queryClient.invalidateQueries({ queryKey: ["admin", "config-versions", entityType, head.id] });
  const invalidateHeads = () => queryClient.invalidateQueries({ queryKey: ["admin", "config-heads", entityType] });

  const { data: versions, isLoading } = useQuery({
    queryKey: ["admin", "config-versions", entityType, head.id],
    queryFn: () => adminConfigApi.listVersions(entityType, head.id),
  });

  const latest = versions?.[versions.length - 1];
  const [definition, setDefinition] = useState<string | null>(null);
  const editableDefinition = definition ?? (latest ? JSON.stringify(latest.definition, null, 2) : "");
  const [message, setMessage] = useState<string | null>(null);

  const draftMutation = useMutation({
    mutationFn: (def: Record<string, unknown>) =>
      latest && latest.status === "DRAFT"
        ? adminConfigApi.updateDraft(entityType, head.id, latest.id, def)
        : adminConfigApi.createVersionDraft(entityType, head.id, def),
    onSuccess: () => {
      invalidateVersions();
      setMessage("Draft saqlandi.");
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => {
      if (!latest) throw new Error("Versiya yo'q");
      return adminConfigApi.publish(entityType, head.id, latest.id);
    },
    onSuccess: (v) => {
      invalidateVersions();
      invalidateHeads();
      setMessage(`Holat: ${v.status}`);
    },
    onError: (err) => setMessage(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik"),
  });

  const validateMutation = useMutation({
    mutationFn: () => {
      if (!latest) throw new Error("Versiya yo'q");
      return adminConfigApi.validate(entityType, head.id, latest.id);
    },
    onSuccess: (r) => setMessage(r.valid ? "Valid ✓" : `Xato: ${r.errors.map((e) => e.message).join("; ")}`),
  });

  if (isLoading) return <div className="h-32 animate-pulse rounded-2xl bg-muted" />;

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-foreground">{head.code}</div>
          <div className="text-xs text-muted-foreground">
            {versions?.length ?? 0} ta versiya · joriy: {latest?.status ?? "—"}
          </div>
        </div>
      </div>

      <label className="block text-xs">
        Definition (JSON) — {latest?.status === "PUBLISHED" ? "yangi draft versiya sifatida saqlanadi" : "joriy draftni tahrirlaysiz"}
        <textarea
          value={editableDefinition}
          onChange={(e) => setDefinition(e.target.value)}
          rows={12}
          className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
        />
      </label>

      {message && <p className="mt-2 text-xs text-muted-foreground">{message}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => {
            try {
              draftMutation.mutate(JSON.parse(editableDefinition));
            } catch {
              setMessage("Noto'g'ri JSON");
            }
          }}
          disabled={draftMutation.isPending}
          className="rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
        >
          Draft saqlash
        </button>
        <button
          onClick={() => validateMutation.mutate()}
          disabled={!latest || validateMutation.isPending}
          className="inline-flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
        >
          <CheckCircle2 className="size-3.5" /> Tekshirish
        </button>
        <button
          onClick={() => publishMutation.mutate()}
          disabled={!latest || latest.status === "PUBLISHED" || publishMutation.isPending}
          className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
        >
          <UploadCloud className="size-3.5" /> Nashr qilish
        </button>
      </div>
    </div>
  );
}

function Page() {
  const [entityType, setEntityType] = useState<ConfigEntityType>("category");
  const [selectedHeadId, setSelectedHeadId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: heads, isLoading, error } = useQuery({
    queryKey: ["admin", "config-heads", entityType],
    queryFn: () => adminConfigApi.listHeads(entityType),
  });

  const selectedHead = heads?.find((h) => h.id === selectedHeadId) ?? null;

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Konfiguratsiya</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Kategoriyalar, formalar, rollar, qidiruv sozlamalari, platforma sozlamalari va h.k. — yaratish, tekshirish, nashr qilish.
        </p>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        {CONFIG_ENTITY_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => {
              setEntityType(t.value);
              setSelectedHeadId(null);
            }}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              entityType === t.value
                ? "bg-primary text-primary-foreground shadow-soft"
                : "border border-border bg-card text-foreground/70 hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div>
          <NewHeadForm
            entityType={entityType}
            onCreated={() => queryClient.invalidateQueries({ queryKey: ["admin", "config-heads", entityType] })}
          />
          <div className="mt-4 rounded-2xl border border-border bg-card">
            {error ? (
              <div className="p-4">
                <EmptyState
                  title={error instanceof ApiError && error.problem.status === 403 ? "Ruxsat yo'q" : "Xatolik"}
                  description={error instanceof ApiError ? error.problem.detail ?? error.problem.title : String(error)}
                />
              </div>
            ) : isLoading ? (
              <div className="h-32 animate-pulse" />
            ) : heads && heads.length > 0 ? (
              heads.map((h) => (
                <button
                  key={h.id}
                  onClick={() => setSelectedHeadId(h.id)}
                  className={`flex w-full items-center justify-between border-b border-border px-4 py-3 text-left text-sm last:border-0 hover:bg-muted/50 ${
                    selectedHeadId === h.id ? "bg-muted" : ""
                  }`}
                >
                  <span className="truncate font-medium text-foreground">{h.code}</span>
                  <span className={`ml-2 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${HEAD_STATUS_STYLE[h.status]}`}>
                    {h.status}
                  </span>
                </button>
              ))
            ) : (
              <div className="p-4 text-xs text-muted-foreground">Hali hech narsa yaratilmagan.</div>
            )}
          </div>
        </div>

        <div>
          {selectedHead ? (
            <HeadDetail entityType={entityType} head={selectedHead} />
          ) : (
            <EmptyState title="Head tanlanmagan" description="Chapdagi ro'yxatdan bittasini tanlang yoki yangisini yarating." />
          )}
        </div>
      </div>
    </AdminShell>
  );
}
