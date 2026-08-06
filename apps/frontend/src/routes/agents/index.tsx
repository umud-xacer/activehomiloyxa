import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/agents/")({
  head: () => ({
    meta: [
      { title: "Agents — ActiveHome" },
      { name: "description", content: "Discover top-rated agents across the network." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="People"
        title="Agents"
        description="Discover top-rated agents across the network."
      />
      <ComingSoon wave={2} page="Agents" />
    </AppShell>
  );
}
