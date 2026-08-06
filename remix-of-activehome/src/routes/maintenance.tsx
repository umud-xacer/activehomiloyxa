import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/maintenance")({
  head: () => ({
    meta: [
      { title: "Maintenance — ActiveHome" },
      { name: "description", content: "ActiveHome is undergoing scheduled maintenance." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="System" title="Maintenance" description="ActiveHome is undergoing scheduled maintenance." />
      <ComingSoon wave={5} page="Maintenance" />
    </AppShell>
  );
}
