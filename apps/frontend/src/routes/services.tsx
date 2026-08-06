import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/services")({
  head: () => ({
    meta: [
      { title: "Home services — ActiveHome" },
      { name: "description", content: "Hire vetted professionals for any home task." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Services"
        title="Home services"
        description="Hire vetted professionals for any home task."
      />
      <ComingSoon wave={3} page="Home services" />
    </AppShell>
  );
}
