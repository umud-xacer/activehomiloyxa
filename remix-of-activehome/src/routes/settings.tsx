import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, AlertCircle, Monitor, LogOut } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { authApi } from "@/lib/auth-api";
import { ApiError } from "@/lib/http";
import { formatRelativeDate } from "@/lib/format";

export const Route = createFileRoute("/settings")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Settings — ActiveHome" },
      { name: "description", content: "Manage your profile, security and preferences." },
    ],
  }),
  component: Page,
});

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <h2 className="font-display text-sm font-semibold text-foreground">{title}</h2>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

const meOptions = { queryKey: ["me"], queryFn: () => authApi.getMe() };

function ProfileSection() {
  const { data: account } = useQuery(meOptions);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => {
    if (account) {
      setDisplayName(account.displayName ?? "");
      setEmail(account.email ?? "");
    }
  }, [account]);

  const onSave = async () => {
    setLoading(true);
    setStatus(null);
    try {
      await authApi.updateMe({ displayName, email: email || undefined });
      setStatus({ ok: true, msg: "Saqlandi" });
    } catch (err) {
      setStatus({ ok: false, msg: err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard title="Profil">
      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">Ism</span>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
        />
      </label>
      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">Email</span>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
        />
      </label>
      {status && (
        <div className={`flex items-center gap-2 text-xs ${status.ok ? "text-success" : "text-destructive"}`}>
          {status.ok ? <CheckCircle2 className="size-3.5" /> : <AlertCircle className="size-3.5" />}
          {status.msg}
        </div>
      )}
      <button
        onClick={onSave}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-60"
      >
        {loading && <Loader2 className="size-4 animate-spin" />}
        Saqlash
      </button>
    </SectionCard>
  );
}

function PasswordSection() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ ok: boolean; msg: string } | null>(null);

  const onSave = async () => {
    setLoading(true);
    setStatus(null);
    try {
      await authApi.changePassword({ currentPassword, newPassword });
      setStatus({ ok: true, msg: "Parol yangilandi" });
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setStatus({ ok: false, msg: err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard title="Parolni almashtirish">
      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">Joriy parol</span>
        <input
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
        />
      </label>
      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">Yangi parol</span>
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
        />
      </label>
      {status && (
        <div className={`flex items-center gap-2 text-xs ${status.ok ? "text-success" : "text-destructive"}`}>
          {status.ok ? <CheckCircle2 className="size-3.5" /> : <AlertCircle className="size-3.5" />}
          {status.msg}
        </div>
      )}
      <button
        onClick={onSave}
        disabled={loading || !currentPassword || !newPassword}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-60"
      >
        {loading && <Loader2 className="size-4 animate-spin" />}
        Yangilash
      </button>
    </SectionCard>
  );
}

function PreferencesSection() {
  const { data: account } = useQuery(meOptions);
  const [email, setEmail] = useState(true);
  const [sms, setSms] = useState(true);
  const [webPush, setWebPush] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);

  const onSave = async () => {
    setLoading(true);
    try {
      await authApi.updatePreferences({ notificationPreferences: { email, sms, webPush } });
      setSaved(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard title="Bildirishnoma sozlamalari">
      <p className="text-xs text-muted-foreground">Hisob: {account?.email}</p>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} className="size-4 rounded border-border" />
        Email orqali bildirishnomalar
      </label>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="checkbox" checked={sms} onChange={(e) => setSms(e.target.checked)} className="size-4 rounded border-border" />
        SMS orqali bildirishnomalar
      </label>
      <label className="flex items-center gap-2 text-sm text-foreground">
        <input type="checkbox" checked={webPush} onChange={(e) => setWebPush(e.target.checked)} className="size-4 rounded border-border" />
        Push bildirishnomalar
      </label>
      {saved && (
        <div className="flex items-center gap-2 text-xs text-success">
          <CheckCircle2 className="size-3.5" /> Saqlandi
        </div>
      )}
      <button
        onClick={onSave}
        disabled={loading}
        className="inline-flex items-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-60"
      >
        {loading && <Loader2 className="size-4 animate-spin" />}
        Saqlash
      </button>
    </SectionCard>
  );
}

function SessionsSection() {
  const { data: sessions, refetch } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => authApi.listSessions(),
  });

  const onRevoke = async (id: string) => {
    await authApi.revokeSession(id);
    refetch();
  };

  return (
    <SectionCard title="Faol sessiyalar">
      <div className="space-y-2">
        {sessions?.map((s) => (
          <div key={s.id} className="flex items-center justify-between rounded-xl border border-border bg-background/50 px-3 py-2.5">
            <div className="flex items-center gap-2 text-sm text-foreground">
              <Monitor className="size-4 text-muted-foreground" />
              <div>
                <div>{s.userAgent ?? "Noma'lum qurilma"} {s.current && <span className="text-xs text-primary">(joriy)</span>}</div>
                <div className="text-xs text-muted-foreground">{formatRelativeDate(s.createdAt)}</div>
              </div>
            </div>
            {!s.current && (
              <button
                onClick={() => onRevoke(s.id)}
                className="text-xs font-semibold text-destructive hover:underline"
              >
                Bekor qilish
              </button>
            )}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function DangerZone() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(false);

  const onClose = async () => {
    setLoading(true);
    try {
      await authApi.closeAccount();
      queryClient.clear();
      navigate({ to: "/" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <SectionCard title="Xavfli hudud">
      {confirming ? (
        <div className="space-y-3">
          <p className="text-xs text-destructive">Hisobingiz butunlay yopiladi. Ishonchingiz komilmi?</p>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-full bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground disabled:opacity-60"
            >
              {loading && <Loader2 className="size-4 animate-spin" />}
              Ha, hisobni yopish
            </button>
            <button onClick={() => setConfirming(false)} className="text-sm text-muted-foreground hover:underline">
              Bekor qilish
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="inline-flex items-center gap-2 rounded-full border border-destructive/40 px-4 py-2 text-sm font-semibold text-destructive hover:bg-destructive/10"
        >
          <LogOut className="size-4" /> Hisobni yopish
        </button>
      )}
    </SectionCard>
  );
}

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Account" title="Settings" description="Manage your profile, security and preferences." />
      <div className="mx-auto max-w-2xl space-y-6 px-6 py-12">
        <ProfileSection />
        <PasswordSection />
        <PreferencesSection />
        <SessionsSection />
        <DangerZone />
      </div>
    </AppShell>
  );
}
