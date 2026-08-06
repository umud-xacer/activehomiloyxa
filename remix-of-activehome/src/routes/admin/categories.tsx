import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Plus, Loader2, FolderTree, Archive, CheckCircle2, AlertCircle, Pencil, ChevronRight } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminConfigApi, type ConfigHead } from "@/lib/admin-config-api";
import { listingApi, type BackendCategory } from "@/lib/listing-api";
import { ApiError } from "@/lib/http";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/admin/categories")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Kategoriyalar — Admin" }] }),
  component: Page,
});

const slugify = (s: string) =>
  s
    .toLowerCase()
    .trim()
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const INPUT = "w-full rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm";

function CreateForm({ categories, onDone }: { categories: BackendCategory[]; onDone: () => void }) {
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [pathEdited, setPathEdited] = useState(false);
  const [parentCategoryId, setParentCategoryId] = useState("");
  const [formDefinitionId, setFormDefinitionId] = useState("");
  const [displayOrder, setDisplayOrder] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const { data: formDefs } = useQuery({
    queryKey: ["admin", "config-heads", "form-definition"],
    queryFn: () => adminConfigApi.listHeads("form-definition"),
  });

  const mutation = useMutation({
    mutationFn: () =>
      adminConfigApi.createCategory({
        name,
        path: path || slugify(name),
        formDefinitionId,
        parentCategoryId: parentCategoryId || undefined,
        displayOrder: Number(displayOrder) || 0,
      }),
    onSuccess: () => {
      setOk(true);
      setName("");
      setPath("");
      setPathEdited(false);
      setParentCategoryId("");
      setFormDefinitionId("");
      setDisplayOrder("0");
      onDone();
      setTimeout(() => setOk(false), 2500);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Kategoriya yaratib bo'lmadi"),
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (!formDefinitionId) {
          setError("Forma tanlang");
          return;
        }
        mutation.mutate();
      }}
      className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-soft"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Plus className="size-4 text-primary" /> Yangi kategoriya
      </div>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Nomi *</span>
        <input
          required
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            if (!pathEdited) setPath(slugify(e.target.value));
          }}
          placeholder="Masalan: Kvartiralar"
          className={INPUT}
        />
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Slug (URL kod) *</span>
        <input
          required
          value={path}
          onChange={(e) => {
            setPathEdited(true);
            setPath(slugify(e.target.value));
          }}
          placeholder="kvartiralar"
          className={`${INPUT} font-mono`}
        />
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Forma (e'lon maydonlari) *</span>
        <Select value={formDefinitionId} onValueChange={setFormDefinitionId}>
          <SelectTrigger className="w-full rounded-xl border-border bg-background py-2.5 text-sm">
            <SelectValue placeholder="Forma tanlang..." />
          </SelectTrigger>
          <SelectContent>
            {formDefs?.map((f) => (
              <SelectItem key={f.id} value={f.id}>
                {f.code}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {formDefs && formDefs.length === 0 && (
          <span className="mt-1 block text-[11px] text-warning">
            Hali forma yo'q — avval Konfiguratsiya → Formalar bo'limida yarating.
          </span>
        )}
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Ota kategoriya (ixtiyoriy)</span>
        <Select value={parentCategoryId} onValueChange={(v) => setParentCategoryId(v === "NONE" ? "" : v)}>
          <SelectTrigger className="w-full rounded-xl border-border bg-background py-2.5 text-sm">
            <SelectValue placeholder="— Yo'q (asosiy) —" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="NONE">— Yo'q (asosiy) —</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name.uz_latn ?? c.path}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      <label className="block">
        <span className="mb-1.5 block text-xs font-semibold text-foreground/80">Tartib raqami</span>
        <input
          type="number"
          value={displayOrder}
          onChange={(e) => setDisplayOrder(e.target.value)}
          className={INPUT}
        />
      </label>

      {error && (
        <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" /> {error}
        </div>
      )}
      {ok && (
        <div className="flex items-center gap-2 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-success">
          <CheckCircle2 className="size-4" /> Kategoriya yaratildi va nashr qilindi
        </div>
      )}

      <button
        type="submit"
        disabled={mutation.isPending}
        className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
      >
        {mutation.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
        Yaratish
      </button>
    </form>
  );
}

/** Loads the config head + current version for a category (matched by `code === path`) --
 * the only way to get the full `definition` document needed to edit it. */
function useCategoryHead(path: string, enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "category-head", path],
    enabled,
    queryFn: async () => {
      const heads = await adminConfigApi.listHeads("category");
      const head = heads.find((h) => h.code === path);
      if (!head || !head.currentVersionId) throw new Error("Kategoriya versiyasi topilmadi");
      const version = await adminConfigApi.getVersion("category", head.id, head.currentVersionId);
      return { head, definition: version.definition };
    },
  });
}

function EditForm({
  cat,
  categories,
  onDone,
  onCancel,
}: {
  cat: BackendCategory;
  categories: BackendCategory[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const { data, isLoading, error: loadError } = useCategoryHead(cat.path, true);
  const { data: formDefs } = useQuery({
    queryKey: ["admin", "config-heads", "form-definition"],
    queryFn: () => adminConfigApi.listHeads("form-definition"),
  });

  const [name, setName] = useState(cat.name.uz_latn ?? "");
  const [parentCategoryId, setParentCategoryId] = useState(cat.parentId ?? "");
  const [formDefinitionId, setFormDefinitionId] = useState(cat.formDefinitionId ?? "");
  const [displayOrder, setDisplayOrder] = useState(String(cat.displayOrder ?? 0));
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      if (!data) throw new Error("Ma'lumot yuklanmadi");
      return adminConfigApi.updateCategory(data.head.id, data.definition, {
        name,
        parentCategoryId: parentCategoryId || null,
        formDefinitionId,
        displayOrder: Number(displayOrder) || 0,
      });
    },
    onSuccess: onDone,
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Saqlab bo'lmadi"),
  });

  const otherCategories = categories.filter((c) => c.id !== cat.id);

  return (
    <div className="space-y-3 border-t border-border bg-muted/20 px-4 py-4">
      {isLoading ? (
        <div className="h-24 animate-pulse rounded-xl bg-muted" />
      ) : loadError ? (
        <div className="text-xs text-destructive">
          {loadError instanceof ApiError ? loadError.problem.detail ?? loadError.problem.title : String(loadError)}
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-foreground/80">Nomi</span>
              <input value={name} onChange={(e) => setName(e.target.value)} className={`${INPUT} py-2`} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-foreground/80">Tartib raqami</span>
              <input
                type="number"
                value={displayOrder}
                onChange={(e) => setDisplayOrder(e.target.value)}
                className={`${INPUT} py-2`}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-foreground/80">Ota kategoriya</span>
              <Select value={parentCategoryId} onValueChange={(v) => setParentCategoryId(v === "NONE" ? "" : v)}>
                <SelectTrigger className="w-full rounded-xl border-border bg-background py-2 text-sm">
                  <SelectValue placeholder="— Yo'q (asosiy) —" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="NONE">— Yo'q (asosiy) —</SelectItem>
                  {otherCategories.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name.uz_latn ?? c.path}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-semibold text-foreground/80">Forma</span>
              <Select value={formDefinitionId} onValueChange={setFormDefinitionId}>
                <SelectTrigger className="w-full rounded-xl border-border bg-background py-2 text-sm">
                  <SelectValue placeholder="Forma tanlang..." />
                </SelectTrigger>
                <SelectContent>
                  {formDefs?.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.code}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
          </div>

          {error && <div className="text-xs text-destructive">{error}</div>}

          <div className="flex items-center gap-2">
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
            >
              {mutation.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <CheckCircle2 className="size-3.5" />}
              Saqlash
            </button>
            <button
              onClick={onCancel}
              className="rounded-full border border-border px-4 py-1.5 text-xs font-semibold text-foreground hover:bg-muted"
            >
              Bekor qilish
            </button>
          </div>
        </>
      )}
    </div>
  );
}

interface TreeNode {
  cat: BackendCategory;
  children: TreeNode[];
}

function buildTree(categories: BackendCategory[]): TreeNode[] {
  const byParent = new Map<string | null, BackendCategory[]>();
  for (const c of categories) {
    const key = c.parentId ?? null;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key)!.push(c);
  }
  for (const list of byParent.values()) {
    list.sort((a, b) => (a.displayOrder ?? 0) - (b.displayOrder ?? 0) || a.path.localeCompare(b.path));
  }
  const build = (parentId: string | null): TreeNode[] =>
    (byParent.get(parentId) ?? []).map((cat) => ({ cat, children: build(cat.id) }));
  return build(null);
}

function CategoryRow({
  node,
  depth,
  categories,
  editingId,
  setEditingId,
  onArchive,
  archivePending,
  refresh,
}: {
  node: TreeNode;
  depth: number;
  categories: BackendCategory[];
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  onArchive: (cat: BackendCategory) => void;
  archivePending: boolean;
  refresh: () => void;
}) {
  const { cat, children } = node;
  const editing = editingId === cat.id;

  return (
    <div>
      <div className="flex items-center justify-between px-4 py-3" style={{ paddingLeft: `${16 + depth * 24}px` }}>
        <div className="flex min-w-0 items-center gap-1.5">
          {depth > 0 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground/50" />}
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-foreground">{cat.name.uz_latn ?? cat.path}</div>
            <div className="font-mono text-[11px] text-muted-foreground">
              /{cat.path} {cat.displayOrder ? `· #${cat.displayOrder}` : ""}
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success">
            {cat.status ?? "ACTIVE"}
          </span>
          <button
            onClick={() => setEditingId(editing ? null : cat.id)}
            className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-muted"
          >
            <Pencil className="size-3" /> Tahrirlash
          </button>
          <button
            onClick={() => onArchive(cat)}
            disabled={archivePending}
            className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-muted disabled:opacity-50"
          >
            <Archive className="size-3" /> Arxivlash
          </button>
        </div>
      </div>
      {editing && (
        <EditForm
          cat={cat}
          categories={categories}
          onDone={() => {
            setEditingId(null);
            refresh();
          }}
          onCancel={() => setEditingId(null)}
        />
      )}
      {children.map((child) => (
        <CategoryRow
          key={child.cat.id}
          node={child}
          depth={depth + 1}
          categories={categories}
          editingId={editingId}
          setEditingId={setEditingId}
          onArchive={onArchive}
          archivePending={archivePending}
          refresh={refresh}
        />
      ))}
    </div>
  );
}

function Page() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const { data: categories = [], isLoading } = useQuery({
    queryKey: ["categories", "admin-list"],
    queryFn: () => listingApi.listCategories(),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["categories"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "category-head"] });
  };

  const retireMutation = useMutation({
    mutationFn: async (cat: BackendCategory) => {
      const heads: ConfigHead[] = await adminConfigApi.listHeads("category");
      const head = heads.find((h) => h.code === cat.path);
      if (!head || !head.currentVersionId) throw new Error("Head topilmadi");
      const version = await adminConfigApi.getVersion("category", head.id, head.currentVersionId);
      return adminConfigApi.retireCategory(head.id, version.definition);
    },
    onSuccess: refresh,
  });

  const active = useMemo(() => categories.filter((c) => c.status !== "RETIRED"), [categories]);
  const retired = categories.filter((c) => c.status === "RETIRED");
  const tree = useMemo(() => buildTree(active), [active]);

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Kategoriyalar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          E'lon kategoriyalarini daraxt ko'rinishida yarating, tahrirlang va boshqaring.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
        <CreateForm categories={active} onDone={refresh} />

        <div>
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <FolderTree className="size-4 text-primary" /> Mavjud kategoriyalar ({active.length})
          </div>
          {isLoading ? (
            <div className="h-40 animate-pulse rounded-2xl bg-muted" />
          ) : active.length === 0 ? (
            <EmptyState title="Kategoriya yo'q" description="Chapdagi forma orqali birinchisini yarating." />
          ) : (
            <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card">
              {tree.map((node) => (
                <CategoryRow
                  key={node.cat.id}
                  node={node}
                  depth={0}
                  categories={active}
                  editingId={editingId}
                  setEditingId={setEditingId}
                  onArchive={(cat) => confirm(`"${cat.name.uz_latn ?? cat.path}" kategoriyasini arxivlaysizmi?`) && retireMutation.mutate(cat)}
                  archivePending={retireMutation.isPending}
                  refresh={refresh}
                />
              ))}
            </div>
          )}

          {retired.length > 0 && (
            <div className="mt-6">
              <div className="mb-2 text-xs font-semibold text-muted-foreground">Arxivlangan ({retired.length})</div>
              <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border bg-card/50">
                {retired.map((c) => (
                  <div key={c.id} className="flex items-center justify-between px-4 py-2.5 text-sm text-muted-foreground">
                    <span className="truncate">{c.name.uz_latn ?? c.path}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold">RETIRED</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </AdminShell>
  );
}
