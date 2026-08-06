import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/hotels")({
  head: () => ({
    meta: [
      { title: "Hotels — ActiveHome" },
      { name: "description", content: "Book premium stays worldwide with instant confirmation." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Stays"
        title="Hotels"
        description="Book premium stays worldwide with instant confirmation."
      />
      <ComingSoon wave={3} page="Hotels" />
    </AppShell>
  );
}
