import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Phone, KeyRound, Loader2, ArrowRight, AlertCircle } from "lucide-react";
import { authApi, type Account } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";
import { AuthShell } from "./sign-in";

export const Route = createFileRoute("/auth/reset")({
  head: () => ({
    meta: [
      { title: "Parolni tiklash — ActiveHome" },
      { name: "description", content: "Telefon raqamingiz orqali hisobingizga qayta kiring." },
    ],
  }),
  component: Page,
});

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message || fallback;
  return fallback;
}

function Page() {
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("+998");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSuccess = (account: Account) => {
    invalidateAuth();
    navigate({ to: dashboardPathForAccount(account) });
  };

  const requestCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.startRecovery({ phoneNumber: phone });
      setStep("code");
    } catch (err) {
      setError(errorMessage(err, "So'rov yuborilmadi. Raqamni tekshiring."));
    } finally {
      setLoading(false);
    }
  };

  const verifyCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await authApi.verifyOtp(phone, code, "RECOVERY");
      onSuccess(result.account);
    } catch (err) {
      setError(errorMessage(err, "Kod noto'g'ri yoki bu raqamga hisob biriktirilmagan."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell side="Parolni tikladingizmi?">
      <h1 className="font-display text-3xl font-semibold tracking-tight">Parolni tiklash</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {step === "phone"
          ? "Hisobingizga biriktirilgan telefon raqamini kiriting — tasdiqlash kodi orqali to'g'ridan-to'g'ri tizimga kirasiz."
          : "Yuborilgan kodni kiriting."}
      </p>

      {step === "phone" ? (
        <form onSubmit={requestCode} className="mt-8 space-y-4">
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Telefon raqami</span>
            <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 transition focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/30">
              <Phone className="size-4 shrink-0 text-muted-foreground" />
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+998901234567"
                required
                className="w-full min-w-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
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
            {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {loading ? "Yuborilmoqda…" : "Kod yuborish"}
          </button>
        </form>
      ) : (
        <form onSubmit={verifyCode} className="mt-8 space-y-4">
          <p className="text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">{phone}</span> raqamiga kod yuborildi.
          </p>
          <label className="block">
            <span className="text-xs font-semibold text-foreground/80">Tasdiqlash kodi</span>
            <div className="mt-1.5 flex items-center gap-2 rounded-2xl border border-border bg-card px-3 py-2.5 transition focus-within:border-primary/50 focus-within:ring-2 focus-within:ring-primary/30">
              <KeyRound className="size-4 shrink-0 text-muted-foreground" />
              <input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                required
                className="w-full min-w-0 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
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
            {loading ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            {loading ? "Tekshirilmoqda…" : "Tasdiqlash va kirish"}
          </button>
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
      )}

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Parolingizni eslaysizmi?{" "}
        <Link to="/auth/sign-in" className="font-semibold text-primary hover:underline">
          Kirish
        </Link>
      </p>
    </AuthShell>
  );
}
