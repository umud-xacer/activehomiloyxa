import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Loader2, SlidersHorizontal, CheckCircle2, AlertCircle, Trash2, Sparkles } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import {
  adminConfigApi,
  SORT_OPTIONS,
  type ConfigHead,
  type FacetContent,
  type FormFieldContent,
  type SortOption,
} from "@/lib/admin-config-api";
import { categoriesOptions } from "@/features/properties/queries";
import { ApiError } from "@/lib/http";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/admin/search-config")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Qidiruv sozlamalari — Admin" }] }),
  component: Page,
});

const slugify = (s: string) =>
  s
    .toLowerCase()
    .trim()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const SORT_LABEL: Record<SortOption, string> = {
  RELEVANCE: "Mos kelish (relevance)",
  NEWEST: "Eng yangi",
  PRICE_ASC: "Narx: arzondan",
  PRICE_DESC: "Narx: qimmatdan",
};

/** Loads the facet-eligible fields of the form bound to a given category, so the facet editor
 * can offer a quick-pick instead of forcing free-text field_code entry. */
function useFacetEligibleFields(categoryId: string) {
  const { data: categories } = useQuery(categoriesOptions());
  const cat = categories?.find((c) => c.id === categoryId);
  return useQuery({
    queryKey: ["admin", "form-def-version", cat?.formDefinitionId],
    enabled: !!cat?.formDefinitionId,
    queryFn: async () => {
      const head = await adminConfigApi.getHead("form-definition", cat!.formDefinitionId!);
      if (!head.currentVersionId) return [];
      const version = await adminConfigApi.getVersion("form-definition", head.id, head.currentVersionId);
      const fields = (version.definition.fields ?? []) as FormFieldContent[];
      return fields.filter((f) => f.facet_eligible);
    },
  });
}

function FacetEditor({ facets, onChange, categoryId }: { facets: FacetContent[]; onChange: (f: FacetContent[]) => void; categoryId: string }) {
  const { data: eligible } = useFacetEligibleFields(categoryId);
  const unused = (eligible ?? []).filter((f) => !facets.some((x) => x.field_code === f.code));

  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-foreground/80">Filtrlar (facets)</div>
      <div className="space-y-1.5">
        {facets.map((f, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <input
              value={f.field_code}
              onChange={(e) => {
                const next = [...facets];
                next[i] = { ...f, field_code: e.target.value };
                onChange(next);
              }}
              placeholder="field_code"
              className="w-32 rounded-lg border border-border bg-background px-2.5 py-1.5 font-mono text-xs"
            />
            <input
              value={f.label.uz_latn ?? ""}
              onChange={(e) => {
                const next = [...facets];
                next[i] = { ...f, label: { ...f.label, uz_latn: e.target.value } };
                onChange(next);
              }}
              placeholder="Ko'rinadigan nomi"
              className="flex-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
            />
            <input
              type="number"
              value={f.order}
              onChange={(e) => {
                const next = [...facets];
                next[i] = { ...f, order: Number(e.target.value) || 0 };
                onChange(next);
              }}
              className="w-16 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
            />
            <button type="button" onClick={() => onChange(facets.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-destructive">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => onChange([...facets, { field_code: "", label: { uz_latn: "" }, order: facets.length }])}
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline"
        >
          <Plus className="size-3" /> Filtr qo'shish
        </button>
      </div>

      {categoryId && unused.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-dashed border-border bg-muted/30 p-2.5">
          <div className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold text-muted-foreground">
            <Sparkles className="size-3" /> Ushbu kategoriya formasidagi filtrlash mumkin bo'lgan maydonlar
          </div>
          <div className="flex flex-wrap gap-1.5">
            {unused.map((f) => (
              <button
                key={f.code}
                type="button"
                onClick={() => onChange([...facets, { field_code: f.code, label: f.label, order: facets.length }])}
                className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-muted"
              >
                + {f.label.uz_latn ?? f.code}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfigBuilder({
  initialName,
  initialCode,
  lockCode,
  initialScopeCategoryId,
  lockScope,
  initialFacets,
  initialSortOptions,
  initialDefaultSort,
  initialPromotionCap,
  onSave,
  saving,
  saveError,
  saveLabel,
}: {
  initialName: string;
  initialCode: string;
  lockCode: boolean;
  initialScopeCategoryId: string | null;
  lockScope: boolean;
  initialFacets: FacetContent[];
  initialSortOptions: SortOption[];
  initialDefaultSort: SortOption;
  initialPromotionCap: number;
  onSave: (input: {
    name: string;
    code: string;
    scopeCategoryId?: string;
    facets: FacetContent[];
    sortOptions: SortOption[];
    defaultSort: SortOption;
    promotionPageCap: number;
  }) => void;
  saving: boolean;
  saveError: string | null;
  saveLabel: string;
}) {
  const { data: categories } = useQuery(categoriesOptions());
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState(initialCode);
  const [codeEdited, setCodeEdited] = useState(lockCode);
  const [scopeCategoryId, setScopeCategoryId] = useState(initialScopeCategoryId ?? "");
  const [facets, setFacets] = useState<FacetContent[]>(initialFacets);
  const [sortOptions, setSortOptions] = useState<SortOption[]>(initialSortOptions);
  const [defaultSort, setDefaultSort] = useState<SortOption>(initialDefaultSort);
  const [promotionCap, setPromotionCap] = useState(String(initialPromotionCap));
  const [localError, setLocalError] = useState<string | null>(null);

  const toggleSort = (opt: SortOption) => {
    setSortOptions((prev) => (prev.includes(opt) ? prev.filter((o) => o !== opt) : [...prev, opt]));
  };

  const submit = () => {
    setLocalError(null);
    if (!name.trim()) return setLocalError("Nom kiriting");
    if (sortOptions.length === 0) return setLocalError("Kamida bitta saralash variantini tanlang");
    if (!sortOptions.includes(defaultSort)) return setLocalError("Standart saralash tanlangan variantlar ichida bo'lishi kerak");
    if (facets.some((f) => !f.field_code.trim())) return setLocalError("Har bir filtr uchun field_code kiriting");
    onSave({
      name,
      code: code || slugify(name),
      scopeCategoryId: scopeCategoryId || undefined,
      facets,
      sortOptions,
      defaultSort,
      promotionPageCap: Number(promotionCap) || 0,
    });
  };

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Nomi *</span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!codeEdited) setCode(slugify(e.target.value));
            }}
            placeholder="Masalan: Kvartiralar uchun qidiruv"
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Kod *{lockCode && " (o'zgarmas)"}</span>
          <input
            value={code}
            disabled={lockCode}
            onChange={(e) => {
              setCodeEdited(true);
              setCode(slugify(e.target.value));
            }}
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 font-mono text-sm disabled:opacity-60"
          />
        </label>
      </div>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Qamrov (scope)</span>
        <Select
          value={scopeCategoryId || "GLOBAL"}
          onValueChange={(v) => setScopeCategoryId(v === "GLOBAL" ? "" : v)}
          disabled={lockScope}
        >
          <SelectTrigger className="w-full rounded-xl border-border bg-background py-2.5 text-sm disabled:opacity-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="GLOBAL">Global (barcha kategoriyalar uchun)</SelectItem>
            {categories?.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name.uz_latn ?? c.path}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <FacetEditor facets={facets} onChange={setFacets} categoryId={scopeCategoryId} />

      <div>
        <div className="mb-1.5 text-xs font-semibold text-foreground/80">Saralash variantlari</div>
        <div className="flex flex-wrap gap-2">
          {SORT_OPTIONS.map((opt) => (
            <label
              key={opt}
              className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                sortOptions.includes(opt) ? "border-primary bg-primary/10 text-primary" : "border-border text-foreground/70 hover:bg-muted"
              }`}
            >
              <input type="checkbox" checked={sortOptions.includes(opt)} onChange={() => toggleSort(opt)} className="hidden" />
              {SORT_LABEL[opt]}
            </label>
          ))}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Standart saralash</span>
          <Select value={defaultSort} onValueChange={(v) => setDefaultSort(v as SortOption)}>
            <SelectTrigger className="w-full rounded-xl border-border bg-background py-2.5 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortOptions.map((opt) => (
                <SelectItem key={opt} value={opt}>
                  {SORT_LABEL[opt]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Reklama sahifa chegarasi (promotion_page_cap)</span>
          <input
            type="number"
            min={0}
            value={promotionCap}
            onChange={(e) => setPromotionCap(e.target.value)}
            className="w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm"
          />
        </label>
      </div>

      {(localError || saveError) && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" /> {localError ?? saveError}
        </div>
      )}

      <button
        type="button"
        onClick={submit}
        disabled={saving}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
      >
        {saving ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
        {saveLabel}
      </button>
    </div>
  );
}

function CreatePanel({ onDone }: { onDone: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (input: {
      name: string;
      code: string;
      scopeCategoryId?: string;
      facets: FacetContent[];
      sortOptions: SortOption[];
      defaultSort: SortOption;
      promotionPageCap: number;
    }) => adminConfigApi.createSearchConfiguration(input),
    onSuccess: onDone,
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Yaratib bo'lmadi"),
  });

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Plus className="size-4 text-primary" /> Yangi qidiruv sozlamasi
      </div>
      <ConfigBuilder
        initialName=""
        initialCode=""
        lockCode={false}
        initialScopeCategoryId={null}
        lockScope={false}
        initialFacets={[]}
        initialSortOptions={["RELEVANCE", "NEWEST"]}
        initialDefaultSort="RELEVANCE"
        initialPromotionCap={0}
        onSave={(input) => {
          setError(null);
          mutation.mutate(input);
        }}
        saving={mutation.isPending}
        saveError={error}
        saveLabel="Yaratish va nashr qilish"
      />
    </div>
  );
}

function EditPanel({ head, onDone }: { head: ConfigHead; onDone: () => void }) {
  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["admin", "search-config-version", head.id, head.currentVersionId],
    queryFn: () => adminConfigApi.getVersion("search-configuration", head.id, head.currentVersionId as string),
    enabled: !!head.currentVersionId,
  });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (input: { facets: FacetContent[]; sortOptions: SortOption[]; defaultSort: SortOption; promotionPageCap: number }) => {
      if (!data) throw new Error("Ma'lumot yuklanmadi");
      return adminConfigApi.updateSearchConfiguration(head.id, data.definition, input);
    },
    onSuccess: onDone,
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Saqlab bo'lmadi"),
  });

  if (isLoading) return <div className="h-64 animate-pulse rounded-2xl bg-muted" />;
  if (loadError || !data)
    return <div className="text-xs text-destructive">{loadError instanceof ApiError ? loadError.problem.detail ?? loadError.problem.title : "Yuklanmadi"}</div>;

  const def = data.definition as {
    descriptor?: { name?: { uz_latn?: string } };
    scope_category_id?: string | null;
    facets?: FacetContent[];
    sort_options?: SortOption[];
    default_sort?: SortOption;
    promotion_page_cap?: number;
  };

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <ConfigBuilder
        initialName={def.descriptor?.name?.uz_latn ?? ""}
        initialCode={head.code}
        lockCode
        initialScopeCategoryId={def.scope_category_id ?? null}
        lockScope
        initialFacets={def.facets ?? []}
        initialSortOptions={def.sort_options ?? []}
        initialDefaultSort={def.default_sort ?? "RELEVANCE"}
        initialPromotionCap={def.promotion_page_cap ?? 0}
        onSave={(input) => {
          setError(null);
          mutation.mutate({
            facets: input.facets,
            sortOptions: input.sortOptions,
            defaultSort: input.defaultSort,
            promotionPageCap: input.promotionPageCap,
          });
        }}
        saving={mutation.isPending}
        saveError={error}
        saveLabel="O'zgarishlarni saqlash"
      />
    </div>
  );
}

function Page() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"list" | "create">("list");
  const [editingHeadId, setEditingHeadId] = useState<string | null>(null);

  const { data: heads = [], isLoading } = useQuery({
    queryKey: ["admin", "config-heads", "search-configuration"],
    queryFn: () => adminConfigApi.listHeads("search-configuration"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "config-heads", "search-configuration"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "search-config-version"] });
    setMode("list");
    setEditingHeadId(null);
  };

  const editingHead = heads.find((h) => h.id === editingHeadId);

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-foreground">Qidiruv sozlamalari</h1>
          <p className="mt-1 text-sm text-muted-foreground">Qidiruv filtrlari (facets) va saralash variantlarini boshqarish.</p>
        </div>
        {mode === "list" && !editingHeadId && (
          <button
            onClick={() => setMode("create")}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
          >
            <Plus className="size-4" /> Yangi sozlama
          </button>
        )}
      </div>

      {mode === "create" ? (
        <>
          <button onClick={() => setMode("list")} className="mb-4 text-xs font-semibold text-muted-foreground hover:text-foreground">
            ← Ro'yxatga qaytish
          </button>
          <CreatePanel onDone={refresh} />
        </>
      ) : editingHead ? (
        <>
          <button onClick={() => setEditingHeadId(null)} className="mb-4 text-xs font-semibold text-muted-foreground hover:text-foreground">
            ← Ro'yxatga qaytish
          </button>
          <EditPanel head={editingHead} onDone={refresh} />
        </>
      ) : isLoading ? (
        <div className="h-64 animate-pulse rounded-2xl bg-muted" />
      ) : heads.length === 0 ? (
        <EmptyState icon={SlidersHorizontal} title="Sozlama yo'q" description="Yuqoridagi tugma orqali birinchisini yarating." />
      ) : (
        <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card">
          {heads.map((h) => (
            <button
              key={h.id}
              onClick={() => setEditingHeadId(h.id)}
              className="flex w-full items-center justify-between px-4 py-3.5 text-left hover:bg-muted/30"
            >
              <div>
                <div className="text-sm font-medium text-foreground">{h.code}</div>
                <div className="text-[11px] text-muted-foreground">{h.businessOwner}</div>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  h.status === "PUBLISHED" ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
                }`}
              >
                {h.status}
              </span>
            </button>
          ))}
        </div>
      )}
    </AdminShell>
  );
}
