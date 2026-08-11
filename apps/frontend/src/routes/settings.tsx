import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  UserRound,
  Lock,
  Bell,
  Monitor,
  Trash2,
  Loader2,
  Save,
  LogOut,
  Phone,
  ShieldCheck,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { useMe, useInvalidateAuth } from "@/features/auth/useAuth";
import { authApi } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/settings")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Sozlamalar — ActiveHome" },
      { name: "description", content: "Profil, xavfsizlik va bildirishnoma sozlamalari." },
    ],
  }),
  component: Page,
});

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message || fallback : fallback;
}

function Page() {
  const { data: account } = useMe();
  const invalidateAuth = useInvalidateAuth();

  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 lg:px-8">
        <ProfileSection
          displayName={account.displayName ?? ""}
          email={account.email ?? ""}
          onSaved={invalidateAuth}
        />
        <PhoneSection phoneNumber={account.phoneNumber} onSaved={invalidateAuth} />
        <PasswordSection />
        <PreferencesSection
          emailPref={account.notificationPreferences?.email ?? true}
          webPushPref={account.notificationPreferences?.webPush ?? true}
          smsPref={account.notificationPreferences?.sms ?? true}
          phoneRevealMode={account.privacySettings?.phoneRevealMode ?? "ON_REQUEST"}
          onSaved={invalidateAuth}
        />
        <SessionsSection />
        <DangerZoneSection />
      </div>
    </DashboardShell>
  );
}

function ProfileSection({
  displayName,
  email,
  onSaved,
}: {
  displayName: string;
  email: string;
  onSaved: () => void;
}) {
  const [name, setName] = useState(displayName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await authApi.updateMe({ displayName: name });
      onSaved();
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err, "Saqlab bo'lmadi."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard title="Profil" icon={UserRound}>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Ism</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Email</span>
          <input
            value={email}
            disabled
            className="mt-1.5 w-full rounded-xl border border-border bg-muted px-3 py-2.5 text-sm text-muted-foreground outline-none"
          />
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        {saved && !error && <p className="text-xs text-success">Saqlandi.</p>}
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Saqlash
        </button>
      </form>
    </SectionCard>
  );
}

function PhoneSection({
  phoneNumber,
  onSaved,
}: {
  phoneNumber: string | null;
  onSaved: () => void;
}) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("+998");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestCode = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authApi.requestPhoneLinkOtp(phone);
      setStep("code");
    } catch (err) {
      setError(errorMessage(err, "Kod yuborilmadi. Raqamni tekshiring."));
    } finally {
      setBusy(false);
    }
  };

  const confirmCode = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await authApi.confirmPhoneLink(phone, code);
      onSaved();
      setStep("phone");
      setCode("");
    } catch (err) {
      setError(errorMessage(err, "Kod noto'g'ri. Qayta urinib ko'ring."));
    } finally {
      setBusy(false);
    }
  };

  if (phoneNumber) {
    return (
      <SectionCard title="Telefon raqami" icon={Phone}>
        <div className="flex items-center gap-2 rounded-xl border border-border/70 bg-background/50 px-3 py-2.5 text-sm text-foreground">
          <ShieldCheck className="size-4 text-success" />
          {phoneNumber}
          <span className="ml-auto text-[11px] font-semibold text-success">Tasdiqlangan</span>
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Bu raqam parolni unutganingizda tizimga kirish uchun ham ishlatiladi.
        </p>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Telefon raqami" icon={Phone}>
      <p className="mb-4 text-xs text-muted-foreground">
        Telefon raqamingizni biriktiring — parolni unutganingizda shu raqam orqali tizimga
        kirasiz.
      </p>
      {step === "phone" ? (
        <form onSubmit={requestCode} className="space-y-4">
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Telefon raqami</span>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+998901234567"
              required
              className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
            />
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Phone className="size-4" />}
            Kod yuborish
          </button>
        </form>
      ) : (
        <form onSubmit={confirmCode} className="space-y-4">
          <p className="text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{phone}</span> raqamiga kod yuborildi.
          </p>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Tasdiqlash kodi</span>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              required
              className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
            />
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
              Tasdiqlash
            </button>
            <button
              type="button"
              onClick={() => {
                setStep("phone");
                setCode("");
                setError(null);
              }}
              className="text-xs font-semibold text-muted-foreground hover:text-foreground"
            >
              Boshqa raqam
            </button>
          </div>
        </form>
      )}
    </SectionCard>
  );
}

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await authApi.changePassword(current, next);
      setCurrent("");
      setNext("");
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err, "Parolni almashtirib bo'lmadi."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard title="Parolni almashtirish" icon={Lock}>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Joriy parol</span>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Yangi parol</span>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
          />
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        {saved && !error && <p className="text-xs text-success">Parol almashtirildi.</p>}
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Yangilash
        </button>
      </form>
    </SectionCard>
  );
}

function PreferencesSection({
  emailPref,
  webPushPref,
  smsPref,
  phoneRevealMode,
  onSaved,
}: {
  emailPref: boolean;
  webPushPref: boolean;
  smsPref: boolean;
  phoneRevealMode: "ALWAYS" | "ON_REQUEST" | "NEVER";
  onSaved: () => void;
}) {
  const [email, setEmail] = useState(emailPref);
  const [webPush, setWebPush] = useState(webPushPref);
  const [sms, setSms] = useState(smsPref);
  const [reveal, setReveal] = useState(phoneRevealMode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await authApi.updatePreferences({
        notificationPreferences: { email, webPush, sms },
        privacySettings: { phoneRevealMode: reveal },
      });
      onSaved();
      setSaved(true);
    } catch (err) {
      setError(errorMessage(err, "Saqlab bo'lmadi."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <SectionCard title="Bildirishnoma va maxfiylik" icon={Bell}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2.5">
          {[
            { key: "email" as const, label: "Email orqali xabarnoma", value: email, set: setEmail },
            {
              key: "webPush" as const,
              label: "Push-bildirishnoma",
              value: webPush,
              set: setWebPush,
            },
            { key: "sms" as const, label: "SMS orqali xabarnoma", value: sms, set: setSms },
          ].map((row) => (
            <label
              key={row.key}
              className="flex items-center justify-between rounded-xl border border-border/70 bg-background/50 px-3 py-2.5"
            >
              <span className="text-sm text-foreground">{row.label}</span>
              <input
                type="checkbox"
                checked={row.value}
                onChange={(e) => row.set(e.target.checked)}
                className="size-4 accent-primary"
              />
            </label>
          ))}
        </div>
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">
            Telefon raqamni ko'rsatish
          </span>
          <select
            value={reveal}
            onChange={(e) => setReveal(e.target.value as typeof reveal)}
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
          >
            <option value="ALWAYS">Har doim ko'rinadi</option>
            <option value="ON_REQUEST">So'ralganda</option>
            <option value="NEVER">Hech qachon</option>
          </select>
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        {saved && !error && <p className="text-xs text-success">Saqlandi.</p>}
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Saqlash
        </button>
      </form>
    </SectionCard>
  );
}

function SessionsSection() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => authApi.listSessions(),
  });

  const revoke = async (sessionId: string) => {
    setError(null);
    try {
      await authApi.revokeSession(sessionId);
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    } catch (err) {
      setError(errorMessage(err, "Sessiyani tugatib bo'lmadi."));
    }
  };

  return (
    <SectionCard title="Faol sessiyalar" icon={Monitor}>
      {error && <p className="mb-3 text-xs text-destructive">{error}</p>}
      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      ) : (
        <ul className="space-y-2">
          {sessions.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between rounded-xl border border-border/70 bg-background/50 px-3 py-2.5"
            >
              <div className="text-sm text-foreground">
                {s.userAgent || "Noma'lum qurilma"}
                {s.current && (
                  <span className="ml-2 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-semibold text-success">
                    Joriy
                  </span>
                )}
                <div className="text-[11px] text-muted-foreground">
                  {s.ipAddress} · {new Date(s.createdAt).toLocaleString()}
                </div>
              </div>
              {!s.current && (
                <button
                  type="button"
                  onClick={() => revoke(s.id)}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-destructive hover:underline"
                >
                  <LogOut className="size-3.5" /> Tugatish
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function DangerZoneSection() {
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onClose = async () => {
    if (!window.confirm("Hisobingizni yopmoqchimisiz? Bu amalni ortga qaytarib bo'lmaydi.")) return;
    setBusy(true);
    setError(null);
    try {
      await authApi.closeAccount();
      invalidateAuth();
      navigate({ to: "/" });
    } catch (err) {
      setError(errorMessage(err, "Hisobni yopib bo'lmadi."));
      setBusy(false);
    }
  };

  return (
    <SectionCard title="Xavfli hudud" icon={Trash2}>
      <p className="text-sm text-muted-foreground">
        Hisobingizni yopish shaxsiy ma'lumotlaringizni anonimlashtiradi. E'lonlar va buyurtmalar
        tarixi saqlanib qoladi, lekin sizga bog'lanib bo'lmaydi.
      </p>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      <button
        type="button"
        onClick={onClose}
        disabled={busy}
        className="mt-4 inline-flex items-center gap-1.5 rounded-full border border-destructive/40 px-4 py-2 text-sm font-semibold text-destructive transition hover:bg-destructive/10 disabled:opacity-60"
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
        Hisobni yopish
      </button>
    </SectionCard>
  );
}
