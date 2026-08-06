import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { Mail, Lock, Loader2, ArrowRight, AlertCircle } from "lucide-react";
import { authApi } from "@/lib/auth-api";
import { ApiError } from "@/lib/http";
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

function SignInPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.loginEmail({ email, password });
      navigate({ to: "/dashboard" });
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell side="Welcome back">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Continue to your ActiveHome workspace.
      </p>

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
        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            <AlertCircle className="size-4 shrink-0" /> {error}
          </div>
        )}
        <button
          type="submit"
          disabled={loading}
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-muted-foreground">
        New here?{" "}
        <Link to="/auth/sign-up" className="font-semibold text-primary hover:underline">
          Create an account
        </Link>
      </p>
    </AuthShell>
  );
}

export function AuthShell({ children, side }: { children: React.ReactNode; side: string }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Visual panel */}
      <div className="relative hidden overflow-hidden lg:block">
        <div className="absolute inset-0 gradient-brand" />
        <div className="gradient-mesh absolute inset-0 opacity-60" />
        <div className="relative flex h-full flex-col p-10 text-primary-foreground">
          <Link to="/" className="inline-flex items-center gap-2">
            <Logo className="h-8" />
          </Link>
          <div className="my-auto max-w-md">
            <div className="text-xs font-medium uppercase tracking-widest opacity-80">{side}</div>
            <h2 className="font-display mt-3 text-4xl font-semibold leading-tight">
              The home & building super app.
            </h2>
            <p className="mt-4 text-sm opacity-80">
              Buy, rent, build, furnish and book — one AI-powered ecosystem across borders.
            </p>
            <div className="mt-8 grid grid-cols-3 gap-3 text-sm">
              {[
                ["120K+", "Listings"],
                ["48", "Countries"],
                ["4.9", "Avg. rating"],
              ].map(([v, l]) => (
                <div key={l} className="rounded-2xl bg-white/10 p-3 backdrop-blur">
                  <div className="font-display text-xl font-semibold">{v}</div>
                  <div className="text-[11px] opacity-80">{l}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="text-[11px] opacity-70">© ActiveHome — Premium PropTech</div>
        </div>
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
          className="w-full max-w-sm"
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
