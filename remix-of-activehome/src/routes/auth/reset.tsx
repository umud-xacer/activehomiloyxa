import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Mail, Loader2, ArrowRight, CheckCircle2 } from "lucide-react";
import { authApi } from "@/lib/auth-api";
import { AuthShell } from "./sign-in";

export const Route = createFileRoute("/auth/reset")({
  head: () => ({
    meta: [
      { title: "Reset password — ActiveHome" },
      { name: "description", content: "Recover access to your ActiveHome account." },
    ],
  }),
  component: Page,
});

function Page() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await authApi.startRecovery({ email });
      setDone(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell side="Account recovery">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Reset password</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Enter your email and we'll send recovery instructions.
      </p>

      {done ? (
        <div className="mt-8 flex items-center gap-3 rounded-2xl border border-success/30 bg-success/10 p-4 text-success">
          <CheckCircle2 className="size-5" />
          <div className="text-sm">
            Agar bu email ro'yxatdan o'tgan bo'lsa, tiklash yo'riqnomasi yuborildi.
          </div>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Email</span>
            <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 focus-within:ring-2 focus-within:ring-primary/30">
              <Mail className="size-4 text-muted-foreground" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@activehome.io"
                className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>
          </label>
          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {loading ? "Yuborilmoqda…" : "Yuborish"}
          </button>
        </form>
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        <Link to="/auth/sign-in" className="font-semibold text-primary hover:underline">
          Back to sign in
        </Link>
      </p>
    </AuthShell>
  );
}
