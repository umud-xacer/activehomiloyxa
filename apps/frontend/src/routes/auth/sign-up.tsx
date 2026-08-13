import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import {
  Mail,
  Lock,
  User,
  Phone,
  KeyRound,
  Loader2,
  ArrowRight,
  ArrowLeft,
  AlertCircle,
  UserRound,
  Building2,
  Clock3,
  Eye,
  EyeOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { authApi, type AccountKind, type Anketa } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";
import { AuthShell, SocialSignInButtons } from "./sign-in";

export const Route = createFileRoute("/auth/sign-up")({
  head: () => ({
    meta: [
      { title: "Ro'yxatdan o'tish — ActiveHome" },
      { name: "description", content: "ActiveHome'da akkaunt yarating." },
    ],
  }),
  component: SignUpPage,
});

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message || fallback;
  return fallback;
}

type WizardStep = "role" | "individual-start" | "anketa" | "verify" | "pending";

const ROLES: { kind: AccountKind; title: string; desc: string; Icon: LucideIcon }[] = [
  {
    kind: "INDIVIDUAL",
    title: "Jismoniy shaxs",
    desc: "Uy qidirmoqchiman, ijaraga olmoqchiman yoki xizmat izlayapman.",
    Icon: UserRound,
  },
  {
    kind: "LEGAL_ENTITY",
    title: "Yuridik shaxs — Ishlab chiqaruvchi",
    desc: "Kompaniyam bor: qurilish, ishlab chiqarish yoki xizmat ko'rsataman.",
    Icon: Building2,
  },
];

function SignUpPage() {
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();

  const [step, setStep] = useState<WizardStep>("role");
  const [accountKind, setAccountKind] = useState<AccountKind | null>(null);
  const [anketa, setAnketa] = useState<Anketa>({});
  const [authMode, setAuthMode] = useState<"email" | "phone">("email");

  const roleLabel = ROLES.find((r) => r.kind === accountKind)?.title;

  return (
    <AuthShell side="ActiveHome'ga qo'shiling">
      {step !== "role" && step !== "pending" && (
        <button
          type="button"
          onClick={() => {
            if (step === "verify") return setStep("anketa");
            if (step === "anketa" && accountKind === "INDIVIDUAL") {
              return setStep("individual-start");
            }
            return setStep("role");
          }}
          className="mb-4 inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" /> Orqaga
        </button>
      )}

      {step === "role" && (
        <>
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Akkauntingiz turini tanlang
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Bu tanlov sizga qaysi panel ochilishini belgilaydi.
          </p>
          <div className="mt-8 space-y-3">
            {ROLES.map(({ kind, title, desc, Icon }) => (
              <button
                key={kind}
                type="button"
                onClick={() => {
                  setAccountKind(kind);
                  setStep(kind === "INDIVIDUAL" ? "individual-start" : "anketa");
                }}
                className="group flex w-full items-start gap-4 rounded-2xl border border-border bg-card p-4 text-left shadow-soft transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-elevated"
              >
                <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Icon className="size-5" />
                </div>
                <div className="min-w-0">
                  <div className="font-display text-base font-semibold text-foreground">
                    {title}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{desc}</div>
                </div>
                <ArrowRight className="ml-auto mt-3 size-4 shrink-0 text-foreground/30 transition group-hover:text-primary" />
              </button>
            ))}
          </div>
        </>
      )}

      {step === "individual-start" && (
        <>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Jismoniy shaxs</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Google yoki Apple bilan bir bosishda ro'yxatdan o'ting — anketasiz, admin
            tasdiqlashisiz.
          </p>
          <SocialSignInButtons />
          <div className="mt-6 flex items-center gap-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <span className="h-px flex-1 bg-border" /> yoki
            <span className="h-px flex-1 bg-border" />
          </div>
          <button
            type="button"
            onClick={() => {
              setAccountKind("INDIVIDUAL");
              setStep("anketa");
            }}
            className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground shadow-soft transition hover:bg-muted"
          >
            Email yoki telefon bilan davom etish
          </button>
        </>
      )}

      {step === "anketa" && accountKind && (
        <>
          <h1 className="font-display text-3xl font-semibold tracking-tight">{roleLabel}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Qisqa anketa — admin tekshiruvi uchun kerak.
          </p>
          <AnketaForm
            accountKind={accountKind}
            initial={anketa}
            onNext={(values) => {
              setAnketa(values);
              setStep("verify");
            }}
          />
        </>
      )}

      {step === "verify" && accountKind && (
        <>
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Aloqa ma'lumotini tasdiqlang
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Oxirgi qadam — email yoki telefon orqali tasdiqlang.
          </p>

          <div className="mt-6 inline-flex rounded-full border border-border bg-card p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setAuthMode("email")}
              className={`rounded-full px-4 py-1.5 transition ${
                authMode === "email" ? "bg-primary text-primary-foreground" : "text-foreground/70"
              }`}
            >
              Email
            </button>
            <button
              type="button"
              onClick={() => setAuthMode("phone")}
              className={`rounded-full px-4 py-1.5 transition ${
                authMode === "phone" ? "bg-primary text-primary-foreground" : "text-foreground/70"
              }`}
            >
              Telefon (OTP)
            </button>
          </div>

          {authMode === "email" ? (
            <EmailSignUp
              accountKind={accountKind}
              anketa={anketa}
              onPending={() => setStep("pending")}
            />
          ) : (
            <PhoneOtpSignUp
              accountKind={accountKind}
              anketa={anketa}
              onDone={(account) => {
                invalidateAuth();
                navigate({ to: dashboardPathForAccount(account) });
              }}
            />
          )}
        </>
      )}

      {step === "pending" && (
        <div className="mt-4 flex flex-col items-center text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Clock3 className="size-7" />
          </div>
          <h1 className="font-display mt-6 text-2xl font-semibold tracking-tight">
            {accountKind === "INDIVIDUAL" ? "Akkauntingiz tayyor" : "So'rovingiz qabul qilindi"}
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            {accountKind === "INDIVIDUAL"
              ? "Emailingizni tasdiqlagach tizimga kiring — panelingiz darhol ochiladi, admin tasdiqlashi shart emas."
              : "Emailingizni tasdiqlagach tizimga kiring — admin anketangizni ko'rib chiqib tasdiqlagach, sizga tegishli panel ochiladi."}
          </p>
          <Link
            to="/auth/sign-in"
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
          >
            Kirish sahifasiga o'tish
          </Link>
        </div>
      )}

      {step === "role" && (
        <p className="mt-6 text-center text-xs text-muted-foreground">
          Akkauntingiz bormi?{" "}
          <Link to="/auth/sign-in" className="font-semibold text-primary hover:underline">
            Kirish
          </Link>
        </p>
      )}
    </AuthShell>
  );
}

function AnketaForm({
  accountKind,
  initial,
  onNext,
}: {
  accountKind: AccountKind;
  initial: Anketa;
  onNext: (values: Anketa) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(initial).map(([k, v]) => [k, String(v ?? "")])),
  );

  const set = (key: string) => (v: string) => setValues((prev) => ({ ...prev, [key]: v }));

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onNext(values);
  };

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-4">
      <FieldRow
        icon={Phone}
        type="tel"
        label="Telefon raqami"
        value={values.phone ?? ""}
        onChange={set("phone")}
        placeholder="+998901234567"
        autoComplete="tel"
        required
      />

      {accountKind === "INDIVIDUAL" && (
        <>
          <FieldRow
            icon={User}
            type="text"
            label="To'liq ism"
            value={values.fullName ?? ""}
            onChange={set("fullName")}
            placeholder="Ism Familiya"
            required
          />
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Maqsad</span>
            <select
              value={values.purpose ?? ""}
              onChange={(e) => set("purpose")(e.target.value)}
              required
              className="mt-1.5 w-full rounded-2xl border border-border bg-card px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
            >
              <option value="" disabled>
                Tanlang
              </option>
              <option value="buy">Sotib olish</option>
              <option value="rent">Ijaraga olish</option>
              <option value="service">Xizmat qidirish</option>
            </select>
          </label>
        </>
      )}

      {accountKind === "LEGAL_ENTITY" && (
        <>
          <FieldRow
            icon={Building2}
            type="text"
            label="Kompaniya nomi"
            value={values.companyName ?? ""}
            onChange={set("companyName")}
            placeholder="MChJ nomi"
            required
          />
          <FieldRow
            icon={User}
            type="text"
            label="STIR"
            value={values.stir ?? ""}
            onChange={set("stir")}
            placeholder="123456789"
            required
          />
          <FieldRow
            icon={User}
            type="text"
            label="Faoliyat yo'nalishi"
            value={values.activity ?? ""}
            onChange={set("activity")}
            placeholder="Masalan: qurilish materiallari ishlab chiqarish"
            required
          />
          <FieldRow
            icon={User}
            type="text"
            label="Mas'ul shaxs"
            value={values.contactPerson ?? ""}
            onChange={set("contactPerson")}
            placeholder="Ism Familiya"
            required
          />
        </>
      )}

      {accountKind === "INVESTOR" && (
        <>
          <FieldRow
            icon={User}
            type="text"
            label="F.I.Sh yoki kompaniya"
            value={values.fullName ?? ""}
            onChange={set("fullName")}
            placeholder="Ism Familiya"
            required
          />
          <FieldRow
            icon={User}
            type="text"
            label="Qiziqish yo'nalishi"
            value={values.interest ?? ""}
            onChange={set("interest")}
            placeholder="Masalan: turar-joy loyihalari"
            required
          />
          <FieldRow
            icon={User}
            type="text"
            label="Taxminiy investitsiya hajmi"
            value={values.budget ?? ""}
            onChange={set("budget")}
            placeholder="Masalan: $50,000"
            required
          />
        </>
      )}

      <SubmitButton loading={false} label="Davom etish" loadingLabel="…" />
    </form>
  );
}

function EmailSignUp({
  accountKind,
  anketa,
  onPending,
}: {
  accountKind: AccountKind;
  anketa: Anketa;
  onPending: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      // Contract: POST /auth/register/email returns 202 (pending email confirmation).
      // ADR-0007: accountKind/anketa travel with it; the account is created PENDING review.
      await authApi.registerEmail(email, password, name || undefined, accountKind, anketa);
      onPending();
    } catch (err) {
      setError(errorMessage(err, "Akkaunt yaratib bo'lmadi. Qayta urinib ko'ring."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-4">
      <FieldRow
        icon={User}
        type="text"
        label="To'liq ism"
        value={name}
        onChange={setName}
        placeholder="Ismingiz"
        autoComplete="name"
      />
      <FieldRow
        icon={Mail}
        type="email"
        label="Email"
        value={email}
        onChange={setEmail}
        placeholder="you@activehome.io"
        autoComplete="email"
        required
      />
      <FieldRow
        icon={Lock}
        type="password"
        label="Parol"
        value={password}
        onChange={setPassword}
        placeholder="Kamida 8 ta belgi"
        autoComplete="new-password"
        required
        toggleablePassword
      />
      {error && <ErrorBanner message={error} />}
      <SubmitButton loading={loading} label="Akkaunt yaratish" loadingLabel="Yaratilmoqda…" />
      <p className="text-[11px] text-muted-foreground">
        Akkaunt yaratish orqali siz{" "}
        <Link to="/privacy" className="underline">
          Maxfiylik siyosati
        </Link>
        ga rozilik bildirasiz.
      </p>
    </form>
  );
}

function PhoneOtpSignUp({
  accountKind,
  anketa,
  onDone,
}: {
  accountKind: AccountKind;
  anketa: Anketa;
  onDone: (account: import("@/lib/auth-client").Account) => void;
}) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phoneNumber, setPhoneNumber] = useState(String(anketa.phone ?? "+998"));
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.requestOtp(phoneNumber, "REGISTRATION");
      setStep("code");
    } catch (err) {
      setError(errorMessage(err, "Kod yuborilmadi. Telefon raqamini tekshiring."));
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      // ADR-0007: REGISTRATION + accountKind/anketa creates the account PENDING review,
      // but a phone-verified account gets a session immediately (unlike email, no confirm
      // step) -- the ReviewGate on the dashboard route shows the waiting screen instead.
      const result = await authApi.verifyOtp(
        phoneNumber,
        code,
        "REGISTRATION",
        accountKind,
        anketa,
      );
      onDone(result.account);
    } catch (err) {
      setError(errorMessage(err, "Kod noto'g'ri. Qayta urinib ko'ring."));
    } finally {
      setLoading(false);
    }
  };

  if (step === "phone") {
    return (
      <form onSubmit={requestCode} className="mt-8 space-y-4">
        <FieldRow
          icon={Phone}
          type="tel"
          label="Telefon raqami"
          value={phoneNumber}
          onChange={setPhoneNumber}
          placeholder="+998901234567"
          autoComplete="tel"
          required
        />
        {error && <ErrorBanner message={error} />}
        <SubmitButton loading={loading} label="Kod yuborish" loadingLabel="Yuborilmoqda…" />
      </form>
    );
  }

  return (
    <form onSubmit={verifyCode} className="mt-8 space-y-4">
      <p className="text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">{phoneNumber}</span> raqamiga kod yuborildi.
      </p>
      <FieldRow
        icon={KeyRound}
        type="text"
        label="Tasdiqlash kodi"
        value={code}
        onChange={setCode}
        placeholder="123456"
        autoComplete="one-time-code"
        required
      />
      {error && <ErrorBanner message={error} />}
      <SubmitButton loading={loading} label="Tasdiqlash" loadingLabel="Tekshirilmoqda…" />
      <button
        type="button"
        onClick={() => {
          setStep("phone");
          setCode("");
          setError(null);
        }}
        className="w-full text-center text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        Boshqa raqam
      </button>
    </form>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
      <AlertCircle className="size-4 shrink-0" /> {message}
    </div>
  );
}

function SubmitButton({
  loading,
  label,
  loadingLabel,
}: {
  loading: boolean;
  label: string;
  loadingLabel: string;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
      {loading ? loadingLabel : label}
    </button>
  );
}

function FieldRow({
  icon: Icon,
  type,
  label,
  value,
  onChange,
  toggleablePassword,
  ...rest
}: {
  icon: React.ComponentType<{ className?: string }>;
  type: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  autoComplete?: string;
  required?: boolean;
  /** Adds a show/hide toggle inside the field and flips `type` between "password" and "text"
   * locally -- purely a display affordance, never touches how the value itself is submitted. */
  toggleablePassword?: boolean;
}) {
  const [revealed, setRevealed] = useState(false);
  const resolvedType = toggleablePassword ? (revealed ? "text" : "password") : type;
  return (
    <label className="block">
      <span className="text-xs font-semibold text-foreground/80">{label}</span>
      <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 transition focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/30">
        <Icon className="size-4 shrink-0 text-muted-foreground" />
        <input
          {...rest}
          type={resolvedType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full min-w-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
        {toggleablePassword && (
          <button
            type="button"
            onClick={() => setRevealed((v) => !v)}
            aria-label={revealed ? "Parolni yashirish" : "Parolni ko'rsatish"}
            className="shrink-0 text-muted-foreground transition hover:text-foreground"
          >
            {revealed ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        )}
      </div>
    </label>
  );
}
