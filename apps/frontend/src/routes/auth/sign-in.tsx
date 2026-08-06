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
      <h1 className="font-display text-3xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-2 text-sm text-muted-foreground">Continue to your ActiveHome workspace.</p>

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
          Phone (OTP)
        </button>
      </div>

      {mode === "email" ? (
        <EmailSignIn onSuccess={onSuccess} />
      ) : (
        <PhoneOtpSignIn onSuccess={onSuccess} />
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        New here?{" "}
        <Link to="/auth/sign-up" className="font-semibold text-primary hover:underline">
          Create an account
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
      setError(errorMessage(err, "Unable to sign in. Check your email and password."));
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
        placeholder="you@activehome.io"
        autoComplete="email"
        required
      />
      <Field
        icon={Lock}
        type="password"
        label="Password"
        value={password}
        onChange={setPassword}
        placeholder="••••••••"
        autoComplete="current-password"
        required
      />
      {error && <ErrorBanner message={error} />}
      <SubmitButton loading={loading} label="Sign in" loadingLabel="Signing in…" />
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
      setError(errorMessage(err, "Unable to send the code. Check the phone number and try again."));
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
      setError(errorMessage(err, "That code didn't work. Check it and try again."));
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
          label="Phone number"
          value={phoneNumber}
          onChange={setPhoneNumber}
          placeholder="+998901234567"
          autoComplete="tel"
          required
        />
        {error && <ErrorBanner message={error} />}
        <SubmitButton loading={loading} label="Send code" loadingLabel="Sending…" />
      </form>
    );
  }

  return (
    <form onSubmit={verifyCode} className="mt-8 space-y-4">
      <p className="text-xs text-muted-foreground">
        We sent a code to <span className="font-semibold text-foreground">{phoneNumber}</span>.
      </p>
      <Field
        icon={KeyRound}
        type="text"
        label="Verification code"
        value={code}
        onChange={setCode}
        placeholder="123456"
        autoComplete="one-time-code"
        required
      />
      {error && <ErrorBanner message={error} />}
      <SubmitButton loading={loading} label="Verify & sign in" loadingLabel="Verifying…" />
      <button
        type="button"
        onClick={() => {
          setStep("phone");
          setCode("");
          setError(null);
        }}
        className="w-full text-center text-xs font-semibold text-muted-foreground hover:text-foreground"
      >
        Use a different number
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
}
function Field({ icon: Icon, type, label, value, onChange, ...rest }: FieldProps) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-foreground/80">{label}</span>
      <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 focus-within:ring-2 focus-within:ring-primary/30">
        <Icon className="size-4 text-muted-foreground" />
        <input
          {...rest}
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
    </label>
  );
}
