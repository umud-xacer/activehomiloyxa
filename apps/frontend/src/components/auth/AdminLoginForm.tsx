import { useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { Lock, Mail, Loader2, ArrowRight, AlertCircle, ShieldAlert } from "lucide-react";
import { authApi } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";

/**
 * Deliberately not a re-skinned `/auth/sign-in` -- no public nav/footer, no marketing panel, no
 * "create an account" link. A non-admin who successfully authenticates here is still signed out
 * and shown the same generic failure as a wrong password, so this page never confirms or denies
 * whether an email belongs to an admin account.
 */
export function AdminLoginForm({ onSuccess }: { onSuccess: () => void }) {
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
      const isAdmin = (result.account.roles ?? []).some(
        (r) => r === "super-admin" || r === "administrator",
      );
      if (!isAdmin) {
        await authApi.logout();
        setError("Login yoki parol noto'g'ri.");
        return;
      }
      onSuccess();
    } catch (err) {
      const fallback = "Login yoki parol noto'g'ri.";
      setError(err instanceof ApiError ? err.message || fallback : fallback);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-sm rounded-3xl border border-border bg-card p-8 shadow-elevated"
      >
        <div className="mb-6 flex items-center gap-2 text-foreground/70">
          <ShieldAlert className="size-4" />
          <span className="text-xs font-semibold uppercase tracking-wider">Restricted</span>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Login</span>
            <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-background px-3 py-2.5 focus-within:ring-2 focus-within:ring-primary/30">
              <Mail className="size-4 text-muted-foreground" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                required
                className="w-full bg-transparent text-sm text-foreground outline-none"
              />
            </div>
          </label>

          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Parol</span>
            <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-background px-3 py-2.5 focus-within:ring-2 focus-within:ring-primary/30">
              <Lock className="size-4 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                className="w-full bg-transparent text-sm text-foreground outline-none"
              />
            </div>
          </label>

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
            {loading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <ArrowRight className="size-4" />
            )}
            {loading ? "Tekshirilmoqda…" : "Kirish"}
          </button>
        </form>
      </motion.div>
    </div>
  );
}
