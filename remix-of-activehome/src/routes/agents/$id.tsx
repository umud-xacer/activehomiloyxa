import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, Phone, Mail, MapPin, Building2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorState } from "@/components/state/ErrorState";
import { profilesApi } from "@/lib/profiles-api";

export const Route = createFileRoute("/agents/$id")({
  head: () => ({ meta: [{ title: "Agent — ActiveHome" }] }),
  component: AgentPage,
});

function AgentPage() {
  const { id } = Route.useParams();
  const { data: profile, isLoading, error } = useQuery({
    queryKey: ["businessProfile", id],
    queryFn: () => profilesApi.getBusinessProfile(id),
  });

  if (error) return <ErrorState error={error as Error} reset={() => location.reload()} />;

  return (
    <AppShell>
      <PageHeader eyebrow="Agent" title={profile?.name.uz_latn ?? "Agent profile"} description="Listings, contact and verification status." />
      <div className="mx-auto max-w-2xl px-6 py-12">
        {isLoading || !profile ? (
          <div className="h-64 animate-pulse rounded-3xl bg-muted" />
        ) : (
          <div className="rounded-3xl border border-border bg-card p-6 shadow-soft">
            <div className="flex items-center gap-4">
              <div className="flex size-16 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-lg font-semibold text-primary">
                {(profile.name.uz_latn ?? "?").slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <h2 className="font-display text-lg font-semibold text-foreground">{profile.name.uz_latn}</h2>
                  {profile.badge && <ShieldCheck className="size-4 shrink-0 text-success" />}
                </div>
                <div className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Building2 className="size-3.5" /> {profile.profileType.replace(/_/g, " ")}
                </div>
              </div>
            </div>

            {profile.description?.uz_latn && (
              <p className="mt-4 text-sm text-muted-foreground">{profile.description.uz_latn}</p>
            )}

            <div className="mt-5 space-y-2 border-t border-border pt-4 text-sm text-foreground">
              {profile.address && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <MapPin className="size-4" /> {profile.address}
                </div>
              )}
              {typeof profile.contacts?.phone === "string" && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Phone className="size-4" /> {profile.contacts.phone}
                </div>
              )}
              {typeof profile.contacts?.email === "string" && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Mail className="size-4" /> {profile.contacts.email}
                </div>
              )}
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
              <span
                className={`rounded-full px-2 py-0.5 font-semibold ${
                  profile.status === "ACTIVE" ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                }`}
              >
                {profile.status}
              </span>
              <span>@{profile.slug}</span>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
