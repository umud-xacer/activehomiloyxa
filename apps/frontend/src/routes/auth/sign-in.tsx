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
  Home,
  Hammer,
  Wrench,
  TrendingUp,
  CalendarCheck,
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
import {
  getGoogleClientId,
  getAppleClientId,
  buildGoogleAuthorizeUrl,
  buildAppleAuthorizeUrl,
} from "@/lib/social-auth";

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

function GoogleGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.52 12.27c0-.85-.08-1.67-.22-2.45H12v4.64h6.47a5.53 5.53 0 0 1-2.4 3.63v3h3.88c2.27-2.09 3.57-5.17 3.57-8.82Z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.96-1.07 7.95-2.91l-3.88-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.26v3.11A12 12 0 0 0 12 24Z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.28A7.2 7.2 0 0 1 4.89 12c0-.79.14-1.56.38-2.28V6.61H1.26A12 12 0 0 0 0 12c0 1.94.46 3.77 1.26 5.39l4.01-3.11Z"
      />
      <path
        fill="#EA4335"
        d="M12 4.76c1.77 0 3.35.61 4.6 1.8l3.44-3.44C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.26 6.61l4.01 3.11C6.22 6.87 8.87 4.76 12 4.76Z"
      />
    </svg>
  );
}

function AppleGlyph() {
  return (
    <svg viewBox="0 0 24 24" className="size-4 fill-current" aria-hidden>
      <path d="M16.36 1.43c0 1.14-.42 2.2-1.24 3.05-.86.9-2.13 1.6-3.28 1.5-.14-1.1.42-2.28 1.2-3.06.85-.87 2.24-1.53 3.32-1.49Zm3.6 16.6c-.5 1.14-.74 1.65-1.38 2.66-.9 1.4-2.16 3.15-3.73 3.16-1.39.02-1.75-.9-3.64-.89-1.88.01-2.28.9-3.68.88-1.57-.02-2.76-1.6-3.66-3-2.5-3.9-2.77-8.48-1.22-10.92 1.1-1.74 2.84-2.76 4.47-2.76 1.67 0 2.72.92 4.1.92 1.34 0 2.15-.92 4.09-.92 1.45 0 3 .8 4.09 2.17-3.6 1.98-3.01 7.13.56 8.7Z" />
    </svg>
  );
}

export function SocialSignInButtons() {
  const [notice, setNotice] = useState<"google" | "apple" | null>(null);
  const googleClientId = getGoogleClientId();
  const appleClientId = getAppleClientId();

  return (
    <div className="mt-6">
      <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <span className="h-px flex-1 bg-border" /> yoki
        <span className="h-px flex-1 bg-border" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() =>
            googleClientId
              ? (window.location.href = buildGoogleAuthorizeUrl(googleClientId))
              : setNotice("google")
          }
          className="inline-flex items-center justify-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground shadow-soft transition hover:bg-muted"
        >
          <GoogleGlyph /> Google
        </button>
        <button
          type="button"
          onClick={() =>
            appleClientId
              ? (window.location.href = buildAppleAuthorizeUrl(appleClientId))
              : setNotice("apple")
          }
          className="inline-flex items-center justify-center gap-2 rounded-full border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground shadow-soft transition hover:bg-muted"
        >
          <AppleGlyph /> Apple
        </button>
      </div>
      {notice && (
        <p className="mt-3 text-center text-[11px] text-muted-foreground">
          {notice === "google" ? "Google" : "Apple"} bilan kirish hali sozlanmagan.
        </p>
      )}
    </div>
  );
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

      <SocialSignInButtons />

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
        <span className="font-semibold text-foreground">{phoneNumber}</span> raqamiga kod yuborildi.
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

const BRAND_PILLARS = [
  { Icon: Home, label: "Ko'chmas mulk" },
  { Icon: TrendingUp, label: "Investorlar" },
  { Icon: Hammer, label: "Qurilish" },
  { Icon: Wrench, label: "Xizmatlar" },
  { Icon: CalendarCheck, label: "Bron qilish" },
];

const shellFadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.07, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function AuthShell({ children, side }: { children: React.ReactNode; side: string }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Visual panel -- brand first impression, icon-led, no long copy */}
      <div className="relative hidden overflow-hidden lg:block">
        <div className="absolute inset-0 gradient-brand" />
        <div className="gradient-mesh absolute inset-0 opacity-60" />
        <div className="absolute inset-x-0 top-0 h-[55%] bg-[radial-gradient(ellipse_at_top,oklch(0.8_0.14_275_/_0.3),transparent_65%)]" />

        <motion.div
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.07 } } }}
          className="relative flex h-full flex-col p-10 text-primary-foreground"
        >
          <motion.div variants={shellFadeUp} custom={0}>
            <Link to="/" className="inline-flex items-center gap-2">
              <Logo className="h-8 brightness-0 invert" />
            </Link>
          </motion.div>

          <div className="my-auto max-w-md">
            <motion.div
              variants={shellFadeUp}
              custom={1}
              className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-medium backdrop-blur"
            >
              <Sparkles className="size-3" />
              {side}
            </motion.div>

            <motion.h2
              variants={shellFadeUp}
              custom={2}
              className="font-display mt-4 text-4xl font-semibold leading-[1.1] tracking-tight"
            >
              Uy va qurilish bilan bog'liq hamma narsa — bitta platformada.
            </motion.h2>

            <motion.div variants={shellFadeUp} custom={3} className="mt-8 grid grid-cols-2 gap-3">
              {BRAND_PILLARS.map(({ Icon, label }, i) => (
                <div
                  key={label}
                  className={`flex items-center gap-3 rounded-2xl border border-white/15 bg-white/10 p-3.5 backdrop-blur transition-colors hover:bg-white/15 ${
                    i === 4 ? "col-span-2" : ""
                  }`}
                >
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/15">
                    <Icon className="size-[18px]" />
                  </div>
                  <div className="font-display text-sm font-semibold">{label}</div>
                </div>
              ))}
            </motion.div>

            <motion.div
              variants={shellFadeUp}
              custom={4}
              className="mt-8 flex flex-wrap items-baseline gap-x-8 gap-y-2 border-t border-white/15 pt-6"
            >
              {[
                { value: "1,240,000+", label: "e'lon" },
                { value: "380+", label: "shahar" },
                { value: "12,500+", label: "hamkor" },
              ].map((s) => (
                <div key={s.label} className="flex items-baseline gap-1.5">
                  <span className="font-display text-lg font-semibold tracking-tight">
                    {s.value}
                  </span>
                  <span className="text-[11px] uppercase tracking-wider opacity-70">{s.label}</span>
                </div>
              ))}
            </motion.div>
          </div>

          <motion.div variants={shellFadeUp} custom={5} className="text-[11px] opacity-70">
            © ActiveHome — Uy va bino super-ilovasi
          </motion.div>
        </motion.div>
      </div>

      {/* Form panel */}
      <div className="relative flex min-h-screen items-center justify-center bg-background px-6 py-12">
        <div className="absolute right-6 top-6 flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="w-full max-w-sm rounded-3xl border border-border bg-card/60 p-8 shadow-elevated backdrop-blur-xl lg:bg-card/40"
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
