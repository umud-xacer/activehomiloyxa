import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle2, Sparkles, Building2 } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { billingApi } from "@/lib/billing-api";
import { profilesApi, type ProfileType } from "@/lib/profiles-api";
import { authApi } from "@/lib/auth-api";
import { ApiError } from "@/lib/http";
import { formatCurrency } from "@/lib/format";
import type { Currency } from "@/features/properties/types";

export const Route = createFileRoute("/subscriptions")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Subscriptions — ActiveHome" },
      { name: "description", content: "Manage your active subscriptions and plans." },
    ],
  }),
  component: Page,
});

const productsOptions = { queryKey: ["products"], queryFn: () => billingApi.listProducts() };
const meOptions = { queryKey: ["me"], queryFn: () => authApi.getMe() };

const PROFILE_TYPES: { value: ProfileType; label: string }[] = [
  { value: "SERVICE_PROVIDER", label: "Xizmat ko'rsatuvchi" },
  { value: "CONSTRUCTION_COMPANY", label: "Qurilish kompaniyasi" },
  { value: "BUILDER", label: "Quruvchi" },
  { value: "MANUFACTURER", label: "Ishlab chiqaruvchi" },
  { value: "SUPPLIER", label: "Yetkazib beruvchi" },
  { value: "CONTRACTOR", label: "Pudratchi" },
  { value: "ARCHITECT", label: "Arxitektor" },
  { value: "INTERIOR_DESIGNER", label: "Interyer dizayneri" },
];

function CreateProfilePrompt({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [profileType, setProfileType] = useState<ProfileType>("SERVICE_PROVIDER");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onCreate = async () => {
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const profile = await profilesApi.createBusinessProfile({ profileType, name: name.trim() });
      // The account's owned-profiles projection updates asynchronously (identity_worker.py
      // drains profiles' outbox, ~1s poll interval) -- switch-profile can 403 with
      // WRONG_ACTING_PROFILE for a brief moment right after create. Retry a few times before
      // giving up instead of failing immediately on that expected race.
      let lastErr: unknown;
      for (let attempt = 0; attempt < 6; attempt++) {
        try {
          await profilesApi.switchActingProfile(profile.id);
          onCreated();
          return;
        } catch (switchErr) {
          lastErr = switchErr;
          if (switchErr instanceof ApiError && switchErr.problem.code === "WRONG_ACTING_PROFILE") {
            await new Promise((r) => setTimeout(r, 700));
            continue;
          }
          throw switchErr;
        }
      }
      throw lastErr;
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.detail ?? err.problem.title : "Xatolik");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-md rounded-3xl border border-border bg-card p-6 text-center shadow-soft">
      <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Building2 className="size-6" />
      </div>
      <h2 className="font-display mt-4 text-lg font-semibold text-foreground">Biznes-profil kerak</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Reja sotib olish uchun avval biznes-profil yaratishingiz kerak.
      </p>
      <div className="mt-5 space-y-3 text-left">
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Kompaniya nomi</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold text-foreground/80">Turi</span>
          <select
            value={profileType}
            onChange={(e) => setProfileType(e.target.value as ProfileType)}
            className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground"
          >
            {PROFILE_TYPES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
      <button
        onClick={onCreate}
        disabled={loading || !name.trim()}
        className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-60"
      >
        {loading && <Loader2 className="size-4 animate-spin" />}
        Yaratish va davom etish
      </button>
    </div>
  );
}

function Page() {
  const queryClient = useQueryClient();
  const { data: products, isLoading } = useQuery(productsOptions);
  const { data: account } = useQuery(meOptions);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [purchasedId, setPurchasedId] = useState<string | null>(null);
  const [buying, setBuying] = useState<string | null>(null);

  const onBuy = async (productId: string) => {
    setBuying(productId);
    try {
      const order = await billingApi.createOrder({ productId, targetType: "PROFILE" });
      setPurchasedId(order.id);
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["entitlements"] });
    } catch (err) {
      if (err instanceof ApiError && err.problem.title === "An acting business profile is required") {
        setNeedsProfile(true);
      }
    } finally {
      setBuying(null);
    }
  };

  return (
    <AppShell>
      <PageHeader eyebrow="Plans" title="Subscriptions" description="Manage your active subscriptions and plans." />
      <div className="mx-auto max-w-5xl px-6 py-12">
        {needsProfile ? (
          <CreateProfilePrompt onCreated={() => setNeedsProfile(false)} />
        ) : purchasedId ? (
          <div className="mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-success/30 bg-success/10 p-4 text-success">
            <CheckCircle2 className="size-5" />
            <div className="text-sm">Buyurtma yaratildi! Hisob-faktura #{purchasedId.slice(0, 8)}</div>
          </div>
        ) : isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-48 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        ) : !products || products.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground">Hozircha reja mavjud emas.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((p) => (
              <div key={p.id} className="flex flex-col rounded-3xl border border-border bg-card p-5 shadow-soft">
                <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Sparkles className="size-5" />
                </div>
                <h3 className="font-display mt-3 text-base font-semibold text-foreground">
                  {p.name.uz_latn ?? p.code}
                </h3>
                {p.description?.uz_latn && (
                  <p className="mt-1 text-xs text-muted-foreground">{p.description.uz_latn}</p>
                )}
                <div className="mt-4 font-display text-xl font-semibold text-foreground">
                  {formatCurrency(Number(p.price.amount), p.price.currency as Currency)}
                  {p.termDays && <span className="text-xs text-muted-foreground"> / {p.termDays} kun</span>}
                </div>
                <button
                  onClick={() => onBuy(p.id)}
                  disabled={buying === p.id}
                  className="mt-4 inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-60"
                >
                  {buying === p.id && <Loader2 className="size-4 animate-spin" />}
                  Sotib olish
                </button>
              </div>
            ))}
          </div>
        )}
        {account && (
          <p className="mt-8 text-center text-xs text-muted-foreground">Hisob: {account.email}</p>
        )}
      </div>
    </AppShell>
  );
}
