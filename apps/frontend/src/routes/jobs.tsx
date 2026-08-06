import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/jobs")({
  head: () => ({
    meta: [
      { title: "Jobs — ActiveHome" },
      {
        name: "description",
        content: "Find work across construction, design, real estate and hospitality.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Careers"
        title="Jobs"
        description="Find work across construction, design, real estate and hospitality."
      />
      <ComingSoon wave={3} page="Jobs" />
    </AppShell>
  );
}
