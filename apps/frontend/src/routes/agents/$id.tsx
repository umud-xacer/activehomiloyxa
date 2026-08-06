import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/agents/$id")({
  head: () => ({ meta: [{ title: "Agent — ActiveHome" }] }),
  component: AgentPage,
});

function AgentPage() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Agent"
        title="Agent profile"
        description="Listings, reviews and verification status."
      />
      <ComingSoon wave={2} page="Agent profile" />
    </AppShell>
  );
}
