import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Loader2,
  Users as UsersIcon,
  Search,
  Ban,
  RotateCcw,
  Shield,
  Trash2,
  X,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import { adminUsersApi, type UserAdminView } from "@/lib/admin-users-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/users")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Foydalanuvchilar — ActiveHome Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<UserAdminView["status"], string> = {
  ACTIVE: "Faol",
  SUSPENDED: "Bloklangan",
  CLOSED: "Yopilgan",
};

const STATUS_CLASS: Record<UserAdminView["status"], string> = {
  ACTIVE: "bg-success/10 text-success",
  SUSPENDED: "bg-destructive/10 text-destructive",
  CLOSED: "bg-muted text-muted-foreground",
};

const ROLE_SUGGESTIONS = ["administrator", "super-admin"];

function RoleAssignForm({ userId, onDone }: { userId: string; onDone: () => void }) {
  const [roleCode, setRoleCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!roleCode.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await adminUsersApi.assignRole(userId, roleCode.trim());
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rolni biriktirib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-border/60 bg-background/60 p-3">
      <input
        value={roleCode}
        onChange={(e) => setRoleCode(e.target.value)}
        placeholder="rol kodi, masalan: administrator"
        className="min-w-[180px] flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none focus:border-primary"
      />
      {ROLE_SUGGESTIONS.map((r) => (
        <button
          key={r}
          type="button"
          onClick={() => setRoleCode(r)}
          className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition hover:bg-primary/10 hover:text-primary"
        >
          {r}
        </button>
      ))}
      <button
        type="button"
        disabled={busy || !roleCode.trim()}
        onClick={submit}
        className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition hover:opacity-90 disabled:opacity-50"
      >
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Shield className="size-3.5" />}
        Biriktirish
      </button>
      {error && <p className="w-full text-xs text-destructive">{error}</p>}
    </div>
  );
}

function UserRow({ user, index }: { user: UserAdminView; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRoleForm, setShowRoleForm] = useState(false);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

  const toggleStatus = async () => {
    setBusy(true);
    setError(null);
    try {
      await adminUsersApi.changeStatus(
        user.id,
        user.status === "SUSPENDED" ? "REACTIVATE" : "SUSPEND",
        user.status === "SUSPENDED" ? undefined : "Admin panel orqali bloklandi",
      );
      await invalidate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  const deletePermanently = async () => {
    if (
      !window.confirm(
        "Bu foydalanuvchini BUTUNLAY o'chirmoqchimisiz? Bu amalni qaytarib bo'lmaydi — akkaunt tizimga kira olmay qoladi va shaxsiy ma'lumotlari (email, telefon, ism) tozalanadi.",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminUsersApi.changeStatus(user.id, "CLOSE", "Admin panel orqali butunlay o'chirildi");
      await invalidate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "O'chirib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.03, duration: 0.3 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-4 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASS[user.status]}`}
            >
              {STATUS_LABEL[user.status]}
            </span>
            {user.createdAt && (
              <span className="text-xs text-muted-foreground">
                {new Date(user.createdAt).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="mt-1 text-sm font-semibold text-foreground">
            {user.email || user.phoneNumber || "—"}
          </div>
          <div className="text-xs text-muted-foreground">{user.id}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setShowRoleForm((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-primary/20"
          >
            <Shield className="size-3.5" /> Rol berish
          </button>
          <button
            type="button"
            disabled={busy || user.status === "CLOSED"}
            onClick={toggleStatus}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${
              user.status === "SUSPENDED"
                ? "bg-success/10 text-success hover:bg-success/20"
                : "bg-destructive/10 text-destructive hover:bg-destructive/20"
            }`}
          >
            {busy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : user.status === "SUSPENDED" ? (
              <RotateCcw className="size-3.5" />
            ) : (
              <Ban className="size-3.5" />
            )}
            {user.status === "SUSPENDED" ? "Faollashtirish" : "Bloklash"}
          </button>
          <button
            type="button"
            disabled={busy || user.status === "CLOSED"}
            onClick={deletePermanently}
            title="Butunlay o'chirish — qaytarib bo'lmaydi"
            className="inline-flex items-center gap-1.5 rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground transition hover:opacity-90 disabled:opacity-50"
          >
            <Trash2 className="size-3.5" />
            O'chirish
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      {showRoleForm && (
        <RoleAssignForm
          userId={user.id}
          onDone={() => {
            setShowRoleForm(false);
            invalidate();
          }}
        />
      )}
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<UserAdminView["status"] | "">("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "users", statusFilter, query],
    queryFn: () =>
      adminUsersApi.listUsers({
        status: statusFilter || undefined,
        query: query || undefined,
        limit: 50,
      }),
    retry: false,
  });

  const items = data?.items ?? [];

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <h1 className="font-display text-3xl font-semibold tracking-tight">Foydalanuvchilar</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Barcha akkauntlarni qidiring, bloklang yoki faollashtiring, rol biriktiring.
          </p>
        </motion.div>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={UsersIcon}
            label="Jami foydalanuvchilar"
            value={data?.page.total ?? items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Ban}
            label="Bloklangan (shu sahifada)"
            value={items.filter((i) => i.status === "SUSPENDED").length}
            accent="warning"
            index={1}
          />
          <StatCard
            icon={RotateCcw}
            label="Faol (shu sahifada)"
            value={items.filter((i) => i.status === "ACTIVE").length}
            accent="success"
            index={2}
          />
        </section>

        <SectionCard
          title="Qidiruv va filtr"
          icon={Search}
          index={0}
          action={
            <div className="flex items-center gap-2">
              {(["", "ACTIVE", "SUSPENDED", "CLOSED"] as const).map((s) => (
                <button
                  key={s || "all"}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    statusFilter === s
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                  }`}
                >
                  {s === "" ? "Barchasi" : STATUS_LABEL[s]}
                </button>
              ))}
            </div>
          }
        >
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Email yoki telefon bo'yicha qidirish…"
              className="w-full rounded-xl border border-border bg-background py-2.5 pl-10 pr-9 text-sm outline-none focus:border-primary"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Foydalanuvchilar ro'yxati" icon={UsersIcon} index={1}>
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}

          {error instanceof ApiError && error.status === 403 && (
            <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <ShieldAlert className="mt-0.5 size-5 shrink-0" />
              Bu sahifa faqat "identity:account:manage_status" ruxsatiga ega adminlar uchun.
            </div>
          )}

          {data && items.length === 0 && (
            <EmptyState
              icon={UsersIcon}
              title="Foydalanuvchi topilmadi"
              description="Qidiruv yoki filtrni o'zgartirib ko'ring."
            />
          )}

          <div className="space-y-3">
            {items.map((user, i) => (
              <UserRow key={user.id} user={user} index={i} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
