import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/hostels")({
  head: () => ({
    meta: [
      { title: "Hostels — ActiveHome" },
      { name: "description", content: "Affordable beds in the world's best cities." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Stays"
        title="Hostels"
        description="Affordable beds in the world's best cities."
      />
      <ComingSoon wave={3} page="Hostels" />
    </AppShell>
  );
}
