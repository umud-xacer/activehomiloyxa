import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import {
  Mail,
  Lock,
  Phone,
  KeyRound,
  Loader2,
  ArrowRight,
  AlertCircle,
  Sparkles,
  Eye,
  EyeOff,
} from "lucide-react";
import { authApi, type Account } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";
import { Logo } from "@/components/site/Logo";
import { LanguageSwitcher } from "@/components/site/LanguageSwitcher";
import { ThemeToggle } from "@/components/site/ThemeToggle";

export const Route = createFileRoute("/auth/sign-in")({
  head: () => ({
    meta: [
      { title: "Sign in — ActiveHome" },
      { name: "description", content: "Sign in to your ActiveHome account." },
    ],
  }),
  component: SignInPage,
});

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message || fallback;
  return fallback;
}

function SignInPage() {
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const [mode, setMode] = useState<"email" | "phone">("email");

  const onSuccess = (account: Account) => {
    invalidateAuth();
    navigate({ to: dashboardPathForAccount(account) });
  };

  return (
    <AuthShell side="Xush kelibsiz">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Xush kelibsiz</h1>
      <p className="mt-2 text-sm text-muted-foreground">Active Home hisobingizga kiring.</p>

      <div className="mt-6 inline-flex rounded-full border border-border bg-card p-1 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setMode("email")}
          className={`rounded-full px-4 py-1.5 transition ${
            mode === "email" ? "bg-primary text-primary-foreground" : "text-foreground/70"
          }`}
        >
          Email
        </button>
        <button
          type="button"
          onClick={() => setMode("phone")}
          className={`rounded-full px-4 py-1.5 transition ${
            mode === "phone" ? "bg-primary text-primary-foreground" : "text-foreground/70"
          }`}
        >
          Telefon (OTP)
        </button>
      </div>

      {mode === "email" ? (
        <EmailSignIn onSuccess={onSuccess} />
      ) : (
        <PhoneOtpSignIn onSuccess={onSuccess} />
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Hisobingiz yo'qmi?{" "}
        <Link to="/auth/sign-up" className="font-semibold text-primary hover:underline">
          Ro'yxatdan o'ting
        </Link>
      </p>
    </AuthShell>
  );
}

function EmailSignIn({ onSuccess }: { onSuccess: (account: Account) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await authApi.loginEmail(email, password);
      onSuccess(result.account);
    } catch (err) {
      setError(errorMessage(err, "Kirib bo'lmadi. Email va parolni tekshiring."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-4">
      <Field
        icon={Mail}
        type="email"
        label="Email"
        value={email}
        onChange={setEmail}
        placeholder="siz@activehome.uz"
        autoComplete="email"
        required
      />
      <div>
        <Field
          icon={Lock}
          type="password"
          label="Parol"
          value={password}
          onChange={setPassword}
          placeholder="••••••••"
          autoComplete="current-password"
          required
          toggleablePassword
        />
        <div className="mt-1.5 text-right">
          <Link
            to="/auth/reset"
            className="text-xs font-semibold text-muted-foreground hover:text-primary"
          >
            Parolni unutdingizmi?
          </Link>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      <SubmitButton loading={loading} label="Kirish" loadingLabel="Kirilmoqda…" />
    </form>
  );
}

function PhoneOtpSignIn({ onSuccess }: { onSuccess: (account: Account) => void }) {
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phoneNumber, setPhoneNumber] = useState("+998");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.requestOtp(phoneNumber, "LOGIN");
      setStep("code");
    } catch (err) {
      setError(errorMessage(err, "Kod yuborilmadi. Telefon raqamini tekshirib qayta urining."));
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await authApi.verifyOtp(phoneNumber, code, "LOGIN");
      onSuccess(result.account);
    } catch (err) {
      setError(errorMessage(err, "Kod noto'g'ri. Tekshirib qayta urining."));
    } finally {
      setLoading(false);
    }
  };

  if (step === "phone") {
    return (
      <form onSubmit={requestCode} className="mt-8 space-y-4">
        <Field
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
        <span className="font-semibold text-foreground">{phoneNumber}</span> raqamiga kod
        yuborildi.
      </p>
      <Field
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
      <SubmitButton loading={loading} label="Tasdiqlash va kirish" loadingLabel="Tekshirilmoqda…" />
      <button
        type="button"
        onClick={() => {
          setStep("phone");
          setCode("");
          setError(null);
        }}
        className="w-full text-center text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        Boshqa raqam ishlatish
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

/** Real, keyless architecture/residential photo -- same loremflickr convention already used for
 * per-category hero backgrounds (see `__root.tsx`'s preconnect hint, which already warms this
 * connection up site-wide). `lock` pins one specific photo instead of a new random one per
 * visit/reload, which would otherwise make the "slow zoom" animation jarring on navigation. */
const AUTH_VISUAL_URL =
  "https://loremflickr.com/1600/2000/architecture,modernbuilding,residential/all?lock=8823";

function AuthVisual({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={`hero-dark relative isolate overflow-hidden ${compact ? "h-56 sm:h-64" : "h-full"}`}
    >
      <motion.div
        className="absolute inset-0 -z-20 bg-cover bg-center"
        style={{ backgroundImage: `url(${AUTH_VISUAL_URL})` }}
        initial={{ scale: 1 }}
        animate={{ scale: 1.08 }}
        transition={{ duration: 24, ease: "linear", repeat: Infinity, repeatType: "reverse" }}
        aria-hidden
      />
      {/* Same dark-overlay-for-legibility treatment as PageHeader's category hero photos --
          strong enough for white text/logo to sit on any photo, not so strong the building
          disappears. */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/85 via-black/45 to-black/20" />
      <div className="gradient-mesh absolute inset-0 -z-10 opacity-30" />

      <div
        className={`relative flex h-full flex-col text-primary-foreground ${compact ? "justify-between p-6" : "justify-between p-10"}`}
      >
        <Link to="/" className="inline-flex w-fit items-center gap-2">
          <Logo className={`w-auto brightness-0 invert ${compact ? "h-7" : "h-8"}`} />
        </Link>

        {!compact && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="inline-flex w-fit items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3.5 py-1.5 text-sm font-medium backdrop-blur"
          >
            <Sparkles className="size-3.5" />
            Yashash joyingiz uchun barchasi.
          </motion.div>
        )}
      </div>
    </div>
  );
}

export function AuthShell({ children, side }: { children: React.ReactNode; side: string }) {
  void side; // kept for call-site compatibility; the visual panel now speaks for itself via photo + tagline
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[45%_55%]">
      {/* Mobile/tablet (< lg): compact visual band on top, form below -- not the desktop split
          squeezed down, its own composition. Desktop (lg+): full-height visual panel. */}
      <div className="lg:hidden">
        <AuthVisual compact />
      </div>
      <div className="relative hidden lg:block">
        <AuthVisual />
      </div>

      {/* Form panel */}
      <div className="relative flex min-h-[calc(100vh-14rem)] items-center justify-center bg-background px-6 py-10 sm:px-10 lg:min-h-screen lg:py-12">
        <div className="absolute right-4 top-4 flex items-center gap-2 sm:right-6 sm:top-6">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-sm rounded-3xl border border-border bg-card p-6 shadow-elevated sm:p-8"
        >
          {children}
        </motion.div>
      </div>
    </div>
  );
}

interface FieldProps {
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
}
function Field({
  icon: Icon,
  type,
  label,
  value,
  onChange,
  toggleablePassword,
  ...rest
}: FieldProps) {
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
