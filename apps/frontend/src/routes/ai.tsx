import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/ai")({
  head: () => ({
    meta: [
      { title: "AI assistant — ActiveHome" },
      {
        name: "description",
        content: "Your personal real-estate AI — search, valuation and negotiation.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Intelligence"
        title="AI assistant"
        description="Your personal real-estate AI — search, valuation and negotiation."
      />
      <ComingSoon wave={4} page="AI assistant" />
    </AppShell>
  );
}
