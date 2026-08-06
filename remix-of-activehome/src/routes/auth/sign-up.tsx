import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Mail, Lock, User, Loader2, ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { authApi } from "@/lib/auth-api";
import { ApiError } from "@/lib/http";
import { AuthShell } from "./sign-in";

export const Route = createFileRoute("/auth/sign-up")({
  head: () => ({
    meta: [
      { title: "Create account — ActiveHome" },
      { name: "description", content: "Create your ActiveHome account." },
    ],
  }),
  component: SignUpPage,
});

function SignUpPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.registerEmail({ email, password, displayName: name });
      // registerEmail returns 202 with no session -- the account is active immediately, so
      // log in right away with the same credentials to keep the original one-step UX.
      await authApi.loginEmail({ email, password });
      setDone(true);
      setTimeout(() => navigate({ to: "/dashboard" }), 1200);
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Sign up failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell side="Join ActiveHome">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Create your account</h1>
      <p className="mt-2 text-sm text-muted-foreground">Start exploring the global ecosystem.</p>

      {done ? (
        <div className="mt-8 flex items-center gap-3 rounded-2xl border border-success/30 bg-success/10 p-4 text-success">
          <CheckCircle2 className="size-5" />
          <div className="text-sm">Account created. Redirecting to your dashboard…</div>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <FieldRow icon={User} type="text" label="Full name" value={name} onChange={setName} placeholder="Your name" autoComplete="name" required />
          <FieldRow icon={Mail} type="email" label="Email" value={email} onChange={setEmail} placeholder="you@activehome.io" autoComplete="email" required />
          <FieldRow icon={Lock} type="password" label="Password" value={password} onChange={setPassword} placeholder="At least 8 characters" autoComplete="new-password" required />
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
            {loading ? "Creating…" : "Create account"}
          </button>
          <p className="text-[11px] text-muted-foreground">
            By creating an account you agree to our{" "}
            <Link to="/privacy" className="underline">Privacy Policy</Link>.
          </p>
        </form>
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Already have an account?{" "}
        <Link to="/auth/sign-in" className="font-semibold text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}

function FieldRow({
  icon: Icon,
  type,
  label,
  value,
  onChange,
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
}) {
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
