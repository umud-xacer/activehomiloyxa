import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, Building2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { profilesApi } from "@/lib/profiles-api";

const profilesOptions = { queryKey: ["businessProfiles"], queryFn: () => profilesApi.listBusinessProfiles() };

export const Route = createFileRoute("/agents/")({
  head: () => ({
    meta: [
      { title: "Agents — ActiveHome" },
      { name: "description", content: "Discover top-rated agents and companies across the network." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: profiles, isLoading } = useQuery(profilesOptions);

  return (
    <AppShell>
      <PageHeader eyebrow="People" title="Agents" description="Discover top-rated agents and companies across the network." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        {isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-32 animate-pulse rounded-3xl bg-muted" />
            ))}
          </div>
        ) : !profiles || profiles.length === 0 ? (
          <EmptyState
            icon={Building2}
            title="Agentlar yo'q"
            description="Hozircha ro'yxatdan o'tgan biznes-profil yo'q."
          />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {profiles.map((profile) => (
              <Link
                key={profile.id}
                to="/agents/$id"
                params={{ id: profile.id }}
                className="group rounded-3xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-elevated"
              >
                <div className="flex items-center gap-3">
                  <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-sm font-semibold text-primary">
                    {(profile.name.uz_latn ?? "?").slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <h3 className="truncate text-sm font-semibold text-foreground">
                        {profile.name.uz_latn ?? profile.slug}
                      </h3>
                      {profile.badge && <ShieldCheck className="size-3.5 shrink-0 text-success" />}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {profile.profileType.replace(/_/g, " ")}
                    </p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
