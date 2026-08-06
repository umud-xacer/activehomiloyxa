import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, Building2 } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { authApi } from "@/lib/auth-api";
import { verificationApi } from "@/lib/verification-api";

export const Route = createFileRoute("/verification")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Verification — ActiveHome" },
      { name: "description", content: "Become a verified buyer, seller or agent." },
    ],
  }),
  component: Page,
});

const meOptions = { queryKey: ["me"], queryFn: () => authApi.getMe() };

const STATUS_LABEL: Record<string, string> = {
  REQUESTED: "Ko'rib chiqilmoqda",
  IN_REVIEW: "Tekshiruvda",
  APPROVED: "Tasdiqlangan",
  REJECTED: "Rad etilgan",
};

function ProfileVerification({ profileId }: { profileId: string }) {
  const { data: verificationCase, isLoading } = useQuery({
    queryKey: ["verification", profileId],
    queryFn: () => verificationApi.getCase(profileId),
    retry: false,
  });

  if (isLoading) return <div className="h-24 animate-pulse rounded-2xl bg-muted" />;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">Profil #{profileId.slice(0, 8)}</span>
        {verificationCase ? (
          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            {STATUS_LABEL[verificationCase.status] ?? verificationCase.status}
          </span>
        ) : (
          <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground">
            Tasdiqlanmagan
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Tasdiqlash uchun avval "Verification" tarifini sotib olishingiz kerak (Subscriptions), so'ngra
        hujjatlaringizni yuklaysiz.
      </p>
      <Link to="/subscriptions" className="mt-3 inline-block text-xs font-semibold text-primary hover:underline">
        Tariflarni ko'rish →
      </Link>
    </div>
  );
}

function Page() {
  const { data: account, isLoading } = useQuery(meOptions);
  const ownedProfileIds = account?.ownedProfileIds ?? [];

  return (
    <AppShell>
      <PageHeader eyebrow="Trust" title="Verification" description="Become a verified buyer, seller or agent." />
      <div className="mx-auto max-w-2xl space-y-4 px-6 py-12">
        {isLoading ? (
          <div className="h-24 animate-pulse rounded-2xl bg-muted" />
        ) : ownedProfileIds.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="Biznes-profil topilmadi"
            description="Tasdiqlash faqat biznes-profillar uchun mavjud. Avval biznes-profil yarating."
            action={
              <Link
                to="/subscriptions"
                className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
              >
                <Building2 className="size-4" /> Profil yaratish
              </Link>
            }
          />
        ) : (
          ownedProfileIds.map((id) => <ProfileVerification key={id} profileId={id} />)
        )}
      </div>
    </AppShell>
  );
}
