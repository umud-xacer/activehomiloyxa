import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, ShieldCheck, ShieldX, Clock, Loader2, Upload, X, Info } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { businessProfilesApi, type SubmittedDocument } from "@/lib/business-profiles-client";
import { billingApi } from "@/lib/billing-client";
import { uploadMedia } from "@/lib/media-client";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/verification")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Tasdiqlash — ActiveHome" },
      { name: "description", content: "Biznes profilingizni tasdiqlang." },
    ],
  }),
  component: Page,
});

const STATUS_INFO: Record<
  "REQUESTED" | "IN_REVIEW" | "APPROVED" | "REJECTED",
  { label: string; icon: typeof Clock; tone: string }
> = {
  REQUESTED: { label: "Yuborildi, navbatda", icon: Clock, tone: "text-amber-600 bg-amber-500/10" },
  IN_REVIEW: { label: "Ko'rib chiqilmoqda", icon: Clock, tone: "text-amber-600 bg-amber-500/10" },
  APPROVED: { label: "Tasdiqlangan", icon: ShieldCheck, tone: "text-success bg-success/10" },
  REJECTED: { label: "Rad etilgan", icon: ShieldX, tone: "text-destructive bg-destructive/10" },
};

function Page() {
  const { data: account } = useMe();
  if (!account) return null;

  const profileId = (account.ownedProfileIds ?? [])[0] ?? null;
  const notApplicable = account.accountKind !== "LEGAL_ENTITY" || !profileId;

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 lg:px-8">
        <SectionCard title="Tasdiqlash" icon={Shield}>
          {notApplicable ? (
            <EmptyState
              icon={Info}
              title="Sizning hisob turingizga tegishli emas"
              description="Biznes tasdiqlash faqat yuridik shaxs profillari uchun mavjud."
            />
          ) : (
            <VerificationPanel profileId={profileId} />
          )}
        </SectionCard>
      </div>
    </DashboardShell>
  );
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message || fallback : fallback;
}

function VerificationPanel({ profileId }: { profileId: string }) {
  const queryClient = useQueryClient();

  const { data: verification, isLoading: caseLoading } = useQuery({
    queryKey: ["verification", profileId],
    queryFn: () => businessProfilesApi.getVerification(profileId),
  });

  const { data: entitlements = [], isLoading: entitlementsLoading } = useQuery({
    queryKey: ["entitlements"],
    queryFn: () => billingApi.listMyEntitlements(),
    enabled: !verification,
  });

  if (caseLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  if (verification) {
    const info = STATUS_INFO[verification.status];
    const Icon = info.icon;
    return (
      <div className="space-y-4">
        <div
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold ${info.tone}`}
        >
          <Icon className="size-4" /> {info.label}
        </div>
        {verification.status === "REJECTED" && verification.decision?.reason && (
          <p className="text-sm text-muted-foreground">Sabab: {verification.decision.reason}</p>
        )}
        <p className="text-xs text-muted-foreground">
          Yuborilgan:{" "}
          {verification.createdAt ? new Date(verification.createdAt).toLocaleString() : "—"}
        </p>
      </div>
    );
  }

  if (entitlementsLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  const eligibility = entitlements.find(
    (e) => e.entitlementType === "VERIFICATION_ELIGIBILITY" && e.activationState === "ACTIVE",
  );

  if (!eligibility) {
    return (
      <EmptyState
        icon={Shield}
        title="Tasdiqlash uchun obuna kerak"
        description="Biznes profilingizni tasdiqlash uchun avval tegishli xizmatni sotib oling."
        action={
          <Link
            to="/subscriptions"
            className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
          >
            Xizmatlarni ko'rish
          </Link>
        }
      />
    );
  }

  return (
    <VerificationForm
      profileId={profileId}
      entitlementId={eligibility.id}
      onSubmitted={() => queryClient.invalidateQueries({ queryKey: ["verification", profileId] })}
    />
  );
}

interface DraftDocument extends SubmittedDocument {
  fileName: string;
}

function VerificationForm({
  profileId,
  entitlementId,
  onSubmitted,
}: {
  profileId: string;
  entitlementId: string;
  onSubmitted: () => void;
}) {
  const [documentKind, setDocumentKind] = useState("passport");
  const [docs, setDocs] = useState<DraftDocument[]>([]);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadMedia(file, "VERIFICATION_DOCUMENT");
      setDocs((prev) => [
        ...prev,
        {
          mediaAssetId: uploaded.mediaAssetId,
          documentKind,
          fileName: file.name,
          position: prev.length + 1,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklashda xatolik.");
    } finally {
      setUploading(false);
    }
  };

  const removeDoc = (mediaAssetId: string) => {
    setDocs((prev) => prev.filter((d) => d.mediaAssetId !== mediaAssetId));
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await businessProfilesApi.requestVerification(profileId, {
        entitlementId,
        documents: docs.map(({ fileName: _fileName, ...rest }) => rest),
      });
      onSubmitted();
    } catch (err) {
      setError(errorMessage(err, "Yuborib bo'lmadi."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Biznesingizni tasdiqlash uchun hujjat(lar) yuklang (pasport, litsenziya yoki guvohnoma).
      </p>

      <label className="block">
        <span className="text-xs font-semibold text-foreground/80">Hujjat turi</span>
        <select
          value={documentKind}
          onChange={(e) => setDocumentKind(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
        >
          <option value="passport">Pasport</option>
          <option value="license">Litsenziya</option>
          <option value="certificate">Guvohnoma</option>
        </select>
      </label>

      {docs.length > 0 && (
        <ul className="space-y-2">
          {docs.map((d) => (
            <li
              key={d.mediaAssetId}
              className="flex items-center justify-between rounded-xl border border-border/70 bg-background/50 px-3 py-2.5 text-sm"
            >
              <span className="truncate text-foreground">
                {d.fileName} <span className="text-muted-foreground">({d.documentKind})</span>
              </span>
              <button
                type="button"
                onClick={() => removeDoc(d.mediaAssetId)}
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-muted">
        {uploading ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}
        Fayl yuklash
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          disabled={uploading}
          onChange={onFileSelected}
        />
      </label>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div>
        <button
          type="button"
          onClick={submit}
          disabled={submitting || docs.length === 0}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {submitting ? <Loader2 className="size-4 animate-spin" /> : <Shield className="size-4" />}
          Tasdiqlashga yuborish
        </button>
      </div>
    </div>
  );
}
