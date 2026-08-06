import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Search, Users, Ban, RotateCcw, ShieldPlus, ShieldMinus, Loader2 } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminUsersApi, type UserAdminView } from "@/lib/admin-users-api";
import { adminConfigApi } from "@/lib/admin-config-api";
import { ApiError } from "@/lib/http";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export const Route = createFileRoute("/admin/users")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Foydalanuvchilar — Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<UserAdminView["status"], { label: string; cls: string }> = {
  ACTIVE: { label: "Faol", cls: "bg-success/15 text-success" },
  SUSPENDED: { label: "Bloklangan", cls: "bg-destructive/15 text-destructive" },
  CLOSED: { label: "Yopilgan", cls: "bg-muted text-muted-foreground" },
};

const roleHeadsOptions = {
  queryKey: ["admin", "config-heads", "role-definition"],
  queryFn: () => adminConfigApi.listHeads("role-definition"),
};

function RoleActions({ user }: { user: UserAdminView }) {
  const queryClient = useQueryClient();
  const { data: roles } = useQuery(roleHeadsOptions);
  const [roleCode, setRoleCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

  const assign = useMutation({
    mutationFn: () => adminUsersApi.assignRole(user.id, roleCode),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik"),
  });

  const revoke = useMutation({
    mutationFn: (headId: string) => adminUsersApi.revokeRole(user.id, headId),
    onSuccess: () => {
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik"),
  });

  const activeRoles = (roles ?? []).filter((r) => r.status !== "ARCHIVED");

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Select value={roleCode} onValueChange={setRoleCode}>
        <SelectTrigger className="h-8 w-36 rounded-full border-border bg-background/50 text-xs">
          <SelectValue placeholder="Rol tanlang" />
        </SelectTrigger>
        <SelectContent>
          {activeRoles.map((r) => (
            <SelectItem key={r.id} value={r.code}>
              {r.code}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <button
        onClick={() => roleCode && assign.mutate()}
        disabled={!roleCode || assign.isPending}
        title="Rol berish"
        className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-muted disabled:opacity-50"
      >
        {assign.isPending ? <Loader2 className="size-3 animate-spin" /> : <ShieldPlus className="size-3" />}
        Berish
      </button>
      <button
        onClick={() => {
          const head = activeRoles.find((r) => r.code === roleCode);
          if (head) revoke.mutate(head.id);
        }}
        disabled={!roleCode || revoke.isPending}
        title="Rolni olib tashlash"
        className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-muted disabled:opacity-50"
      >
        {revoke.isPending ? <Loader2 className="size-3 animate-spin" /> : <ShieldMinus className="size-3" />}
        Olib tashlash
      </button>
      {error && <span className="w-full text-[11px] text-destructive">{error}</span>}
    </div>
  );
}

function UserRow({ user }: { user: UserAdminView }) {
  const queryClient = useQueryClient();
  const status = STATUS_LABEL[user.status];

  const statusMutation = useMutation({
    mutationFn: (action: "SUSPEND" | "REACTIVATE") => adminUsersApi.changeStatus(user.id, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <div className="flex flex-col gap-3 border-b border-border p-4 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-foreground">{user.email ?? user.phoneNumber ?? "—"}</span>
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${status.cls}`}>{status.label}</span>
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{user.id}</div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <RoleActions user={user} />
        {user.status === "ACTIVE" ? (
          <button
            onClick={() => statusMutation.mutate("SUSPEND")}
            disabled={statusMutation.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/25 disabled:opacity-50"
          >
            <Ban className="size-3.5" /> Bloklash
          </button>
        ) : user.status === "SUSPENDED" ? (
          <button
            onClick={() => statusMutation.mutate("REACTIVATE")}
            disabled={statusMutation.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-success/15 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/25 disabled:opacity-50"
          >
            <RotateCcw className="size-3.5" /> Faollashtirish
          </button>
        ) : null}
      </div>
    </div>
  );
}

function Page() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [status, setStatus] = useState<string>("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pages, setPages] = useState<UserAdminView[][]>([]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "users", submittedQuery, status, cursor],
    queryFn: () => adminUsersApi.listUsers({ query: submittedQuery || undefined, status: status || undefined, cursor }),
  });

  const items = pages.length > 0 ? pages.flat() : data?.items ?? [];

  const loadMore = () => {
    if (!data) return;
    setPages((prev) => [...prev, data.items]);
    setCursor(data.page.nextCursor ?? undefined);
  };

  const resetSearch = (next: { query?: string; status?: string }) => {
    setPages([]);
    setCursor(undefined);
    if (next.query !== undefined) setSubmittedQuery(next.query);
    if (next.status !== undefined) setStatus(next.status);
  };

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Foydalanuvchilar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Qidirish, bloklash/faollashtirish va rol berish/olib tashlash.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          resetSearch({ query });
        }}
        className="mb-5 flex flex-wrap items-center gap-3"
      >
        <div className="relative flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Email, telefon yoki ism bo'yicha qidirish..."
            className="w-full rounded-full border border-border bg-card py-2 pl-9 pr-3 text-sm"
          />
        </div>
        <Select value={status} onValueChange={(v) => resetSearch({ status: v === "ALL" ? "" : v })}>
          <SelectTrigger className="w-40 rounded-full border-border bg-card px-4 py-2 text-sm">
            <SelectValue placeholder="Barcha holatlar" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">Barcha holatlar</SelectItem>
            <SelectItem value="ACTIVE">Faol</SelectItem>
            <SelectItem value="SUSPENDED">Bloklangan</SelectItem>
            <SelectItem value="CLOSED">Yopilgan</SelectItem>
          </SelectContent>
        </Select>
        <button
          type="submit"
          className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
        >
          Qidirish
        </button>
      </form>

      {error ? (
        <EmptyState
          icon={Users}
          title={error instanceof ApiError && error.problem.status === 403 ? "Ruxsat yo'q" : "Xatolik"}
          description={error instanceof ApiError ? error.problem.detail ?? error.problem.title : String(error)}
        />
      ) : isLoading && items.length === 0 ? (
        <div className="h-64 animate-pulse rounded-2xl bg-muted" />
      ) : items.length === 0 ? (
        <EmptyState icon={Users} title="Foydalanuvchi topilmadi" description="Qidiruv yoki filtrlarni o'zgartiring." />
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-border bg-card">
            {items.map((u) => (
              <UserRow key={u.id} user={u} />
            ))}
          </div>
          {data?.page.nextCursor && (
            <div className="mt-4 flex justify-center">
              <button
                onClick={loadMore}
                disabled={isLoading}
                className="rounded-full border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
              >
                {isLoading ? <Loader2 className="size-4 animate-spin" /> : "Ko'proq yuklash"}
              </button>
            </div>
          )}
        </>
      )}
    </AdminShell>
  );
}
