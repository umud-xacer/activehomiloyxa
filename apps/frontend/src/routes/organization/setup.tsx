/**
 * ADR-0010: the mandatory onboarding wizard a LEGAL_ENTITY account is redirected to
 * (`requireOnboardedLegalEntity`, `lib/require-auth.ts`) until `BusinessProfile.
 * onboarding_completed_at` is set. Collects the mandatory landing-page fields (name, phone,
 * logo, description, portfolio, address), then calls `completeOnboarding`, which starts the
 * 5-day free trial server-side.
 *
 * Reuses `TextListField`/`BrandingFields`/`PortfolioFields` (`components/business-profile/`) --
 * the same building blocks the edit form (`dashboard/business-profile.tsx`) uses, so this wizard
 * and that form never drift apart on how a phone/logo/portfolio item is captured.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, Check, Film, ImageIcon, Loader2, MapPin, Phone, Sparkles } from "lucide-react";
import { requireAuth, dashboardPathForAccount } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { TextListField } from "@/components/business-profile/TextListField";
import { BrandingFields } from "@/components/business-profile/BrandingSection";
import { PortfolioFields } from "@/components/business-profile/PortfolioGallery";
import { PromoVideoFields } from "@/components/business-profile/PromoVideoUpload";
import { useMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";
import {
  businessProfilesApi,
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABEL,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
  type MainCategory,
  type ProfileType,
} from "@/lib/business-profiles-client";

export const Route = createFileRoute("/organization/setup")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Kompaniyani sozlash — ActiveHome" },
      {
        name: "description",
        content: "Kompaniya profilingizni to'ldiring va 5 kunlik bepul sinov muddatini boshlang.",
      },
    ],
  }),
  component: Page,
});

type Step = "basics" | "branding" | "portfolio" | "review";
const STEPS: { id: Step; label: string }[] = [
  { id: "basics", label: "Asosiy ma'lumot" },
  { id: "branding", label: "Logotip" },
  { id: "portfolio", label: "Portfolio" },
  { id: "review", label: "Tasdiqlash" },
];

function StepIndicator({ current }: { current: Step }) {
  const currentIndex = STEPS.findIndex((s) => s.id === current);
  return (
    <div className="mb-8 flex items-center gap-2">
      {STEPS.map((step, i) => (
        <div key={step.id} className="flex flex-1 items-center gap-2">
          <div
            className={`flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition ${
              i < currentIndex
                ? "bg-success text-success-foreground"
                : i === currentIndex
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
            }`}
          >
            {i < currentIndex ? <Check className="size-3.5" /> : i + 1}
          </div>
          <span
            className={`hidden text-xs font-medium sm:inline ${
              i <= currentIndex ? "text-foreground" : "text-muted-foreground"
            }`}
          >
            {step.label}
          </span>
          {i < STEPS.length - 1 && <div className="h-px flex-1 bg-border" />}
        </div>
      ))}
    </div>
  );
}

function WizardCard({ children }: { children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className="rounded-3xl border border-border bg-card p-6 shadow-soft sm:p-8"
    >
      {children}
    </motion.div>
  );
}

function BasicsStep({
  account,
  existingProfile,
  onCreated,
}: {
  account: NonNullable<ReturnType<typeof useMe>["data"]>;
  existingProfile: BusinessProfile | null;
  onCreated: (profile: BusinessProfile) => void;
}) {
  const [name, setName] = useState(existingProfile?.name.uz_latn || "");
  const [profileType, setProfileType] = useState<ProfileType>(
    existingProfile?.profileType || "MANUFACTURER",
  );
  const [description, setDescription] = useState(existingProfile?.description?.uz_latn || "");
  const [phones, setPhones] = useState<string[]>(existingProfile?.contacts?.phones ?? []);
  const [address, setAddress] = useState(existingProfile?.address || "");
  const [mainCategory, setMainCategory] = useState<MainCategory | "">(
    existingProfile?.mainCategory || "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canContinue = name.trim() && phones.some((p) => p.trim()) && address.trim() && mainCategory;

  const onSubmit = async () => {
    setSaving(true);
    setError(null);
    try {
      const cleanPhones = phones.map((p) => p.trim()).filter(Boolean);
      const profile = existingProfile
        ? await businessProfilesApi.update(existingProfile.id, {
            name,
            description,
            address,
            contacts: { phones: cleanPhones },
            mainCategory: mainCategory || undefined,
          })
        : await businessProfilesApi.create({
            profileType,
            name,
            description,
            contacts: { phones: cleanPhones },
            address,
            mainCategory: mainCategory || undefined,
          });
      onCreated(profile);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <WizardCard>
      <h2 className="font-display text-xl font-semibold text-foreground">Kompaniyangiz haqida</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Bu ma'lumotlar ommaviy landing sahifangizda ko'rinadi.
      </p>
      <div className="mt-6 space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Kompaniya nomi *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Masalan, Oq Oltin MChJ"
              className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Yo'nalishi</label>
            <select
              value={profileType}
              disabled={!!existingProfile}
              onChange={(e) => setProfileType(e.target.value as ProfileType)}
              className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30 disabled:opacity-60"
            >
              {Object.entries(PROFILE_TYPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground">Asosiy kategoriya *</label>
          <select
            value={mainCategory}
            onChange={(e) => setMainCategory(e.target.value as MainCategory)}
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          >
            <option value="" disabled>
              Tanlang
            </option>
            {MAIN_CATEGORIES.map((value) => (
              <option key={value} value={value}>
                {MAIN_CATEGORY_LABEL[value]}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-muted-foreground/70">
            Tashkilotingiz Tashkilotlar katalogida shu bo'lim ostida ko'rinadi.
          </p>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground">Kompaniya haqida *</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Nima bilan shug'ullanasiz, qanday xizmat/mahsulot taklif qilasiz"
            className="mt-1 w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        <TextListField
          icon={Phone}
          label="Telefon raqami *"
          placeholder="+998 90 123 45 67"
          values={phones}
          onChange={setPhones}
        />

        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <MapPin className="size-3.5" /> Manzil *
          </label>
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Shahar, tuman, ko'cha"
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <button
          type="button"
          onClick={onSubmit}
          disabled={saving || !canContinue}
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50 sm:w-auto"
        >
          {saving && <Loader2 className="size-4 animate-spin" />}
          Davom etish
        </button>
      </div>
    </WizardCard>
  );
}

function BrandingStep({
  profile,
  onNext,
  onBack,
}: {
  profile: BusinessProfile;
  onNext: () => void;
  onBack: () => void;
}) {
  return (
    <WizardCard>
      <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-foreground">
        <ImageIcon className="size-5 text-primary" /> Logotip va muqova rasmi
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Logotip majburiy — u landing sahifangiz va e'lonlaringizda ko'rinadi. Muqova rasmi
        ixtiyoriy.
      </p>
      <div className="mt-6">
        <BrandingFields profile={profile} />
      </div>
      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-full border border-border px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
        >
          Orqaga
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!profile.logoMediaAssetId}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50"
        >
          Davom etish
        </button>
      </div>
    </WizardCard>
  );
}

function PortfolioStep({
  profile,
  onNext,
  onBack,
}: {
  profile: BusinessProfile;
  onNext: () => void;
  onBack: () => void;
}) {
  // `profile.portfolio` is never populated by the profile-read endpoint (only the dedicated
  // listPortfolio call returns items) -- track the live count via PortfolioFields' own callback
  // instead of trusting the wire field, or this gate never unlocks.
  const [itemCount, setItemCount] = useState((profile.portfolio ?? []).length);
  const hasItems = itemCount > 0;
  return (
    <WizardCard>
      <h2 className="font-display text-xl font-semibold text-foreground">
        Qilgan ishlaringiz portfoliosi
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Kamida bitta rasm yoki video qo'shing — bu potentsial mijozlarga ishonch beradi.
      </p>
      <div className="mt-6">
        <PortfolioFields profile={profile} onItemsChange={(items) => setItemCount(items.length)} />
      </div>

      <div className="mt-8 border-t border-border/70 pt-6">
        <h3 className="flex items-center gap-2 font-display text-base font-semibold text-foreground">
          <Film className="size-4 text-primary" /> Promo videolar (ixtiyoriy)
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Kompaniyangiz haqida qisqa (maks. 30 soniya) tanishtiruv video qo'shing — ko'pi bilan 2
          ta.
        </p>
        <div className="mt-4">
          <PromoVideoFields profile={profile} />
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-full border border-border px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
        >
          Orqaga
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={!hasItems}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-50"
        >
          Davom etish
        </button>
      </div>
    </WizardCard>
  );
}

function ReviewStep({ profile, onBack }: { profile: BusinessProfile; onBack: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await businessProfilesApi.completeOnboarding(profile.id);
      await queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
      await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
      await navigate({ to: "/dashboard/seller" });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Boshlab bo'lmadi. Barcha majburiy maydonlar to'ldirilganini tekshiring.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <WizardCard>
      <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-foreground">
        <Sparkles className="size-5 text-primary" /> Deyarli tayyor
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Tasdiqlaganingizdan so'ng 5 kunlik bepul sinov muddati boshlanadi — shu davrda landing
        sahifangiz va e'lonlaringiz saytda hamma uchun ochiq bo'ladi.
      </p>

      <div className="mt-6 space-y-2 rounded-2xl border border-border bg-muted/40 p-4 text-sm">
        <div className="flex items-center gap-2">
          <Building2 className="size-4 text-muted-foreground" />
          <span className="font-medium text-foreground">{profile.name.uz_latn}</span>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Phone className="size-4" /> {profile.contacts?.phones?.[0]}
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <MapPin className="size-4" /> {profile.address}
        </div>
      </div>

      {error && <p className="mt-4 text-xs text-destructive">{error}</p>}

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-full border border-border px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-muted"
        >
          Orqaga
        </button>
        <button
          type="button"
          onClick={onFinish}
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-60"
        >
          {submitting ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Sparkles className="size-4" />
          )}
          5 kunlik sinovni boshlash
        </button>
      </div>
    </WizardCard>
  );
}

function SetupWizardContent({
  account,
}: {
  account: NonNullable<ReturnType<typeof useMe>["data"]>;
}) {
  const navigate = useNavigate();
  const ownedProfileId = (account.ownedProfileIds ?? [])[0] ?? null;

  const { data: existingProfile, isLoading } = useQuery({
    queryKey: ["business-profiles", "mine", ownedProfileId],
    queryFn: () => businessProfilesApi.get(ownedProfileId as string),
    enabled: !!ownedProfileId,
  });

  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [step, setStep] = useState<Step>("basics");

  useEffect(() => {
    if (existingProfile) setProfile(existingProfile);
  }, [existingProfile]);

  // Resume at the right step after a refresh instead of always bouncing back to "basics" --
  // every step's own data (name/phones, logo, portfolio items) is already saved server-side as
  // soon as its "Davom etish" unlocks (BasicsStep calls create/update immediately, Branding/
  // Portfolio upload straight to the media API), so the only thing a refresh used to lose was
  // which step was showing, forcing a needless re-click through already-done steps. Runs once,
  // guarded by a ref, so it doesn't fight the user's own back/forward clicks during the session.
  const hasResumedRef = useRef(false);
  useEffect(() => {
    if (hasResumedRef.current || isLoading) return;
    hasResumedRef.current = true;
    if (!existingProfile) return;
    setStep(existingProfile.logoMediaAssetId ? "portfolio" : "branding");
  }, [existingProfile, isLoading]);

  useEffect(() => {
    if (account.accountKind !== "LEGAL_ENTITY") {
      navigate({ to: dashboardPathForAccount(account) });
      return;
    }
    if (existingProfile?.onboardingCompletedAt) {
      navigate({ to: "/dashboard/seller" });
    }
  }, [account, existingProfile, navigate]);

  const effectiveProfile = profile ?? existingProfile ?? null;

  if (account.accountKind !== "LEGAL_ENTITY") return null;
  if (ownedProfileId && isLoading) {
    return (
      <div className="flex items-center gap-2 py-16 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 lg:px-8">
      <div className="mb-8 text-center">
        <h1 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">
          Kompaniyangizni sozlang
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Bir necha qadamda tayyor — so'ng 5 kunlik bepul sinov boshlanadi.
        </p>
      </div>

      <StepIndicator current={step} />

      {step === "basics" && (
        <BasicsStep
          account={account}
          existingProfile={effectiveProfile}
          onCreated={(p) => {
            setProfile(p);
            setStep("branding");
          }}
        />
      )}
      {step === "branding" && effectiveProfile && (
        <BrandingStep
          profile={effectiveProfile}
          onBack={() => setStep("basics")}
          onNext={() => setStep("portfolio")}
        />
      )}
      {step === "portfolio" && effectiveProfile && (
        <PortfolioStep
          profile={effectiveProfile}
          onBack={() => setStep("branding")}
          onNext={() => setStep("review")}
        />
      )}
      {step === "review" && effectiveProfile && (
        <ReviewStep profile={effectiveProfile} onBack={() => setStep("portfolio")} />
      )}
    </div>
  );
}

function Page() {
  const { data: account } = useMe();
  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <SetupWizardContent account={account} />
    </DashboardShell>
  );
}
