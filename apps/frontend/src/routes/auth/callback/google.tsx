import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { z } from "zod";
import { useEffect, useRef, useState } from "react";
import { Loader2, AlertCircle } from "lucide-react";
import { authApi } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { getGoogleRedirectUri } from "@/lib/social-auth";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";

const searchSchema = z.object({
  code: fallback(z.string(), "").default(""),
  error: fallback(z.string(), "").default(""),
});

export const Route = createFileRoute("/auth/callback/google")({
  validateSearch: zodValidator(searchSchema),
  head: () => ({ meta: [{ title: "Google — ActiveHome" }] }),
  component: Page,
});

function Page() {
  const { code, error: oauthError } = Route.useSearch();
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (oauthError) {
      setError("Google bilan kirish bekor qilindi.");
      return;
    }
    if (!code) {
      setError("Google javobida kod topilmadi.");
      return;
    }
    authApi
      .loginGoogle(code, getGoogleRedirectUri())
      .then(({ account }) => {
        invalidateAuth();
        navigate({ to: dashboardPathForAccount(account) });
      })
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError
            ? err.message || "Google bilan kirib bo'lmadi."
            : "Google bilan kirib bo'lmadi.",
        );
      });
  }, [code, oauthError, navigate, invalidateAuth]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      {error ? (
        <>
          <AlertCircle className="size-8 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
          <Link to="/auth/sign-in" className="text-sm font-semibold text-primary hover:underline">
            Kirish sahifasiga qaytish
          </Link>
        </>
      ) : (
        <>
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Google bilan tekshirilmoqda…</p>
        </>
      )}
    </div>
  );
}
