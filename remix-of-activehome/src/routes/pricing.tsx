import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — ActiveHome" },
      { name: "description", content: "Transparent plans for individuals, agents and agencies." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Plans" title="Pricing" description="Transparent plans for individuals, agents and agencies." />
      <ComingSoon wave={5} page="Pricing" />
    </AppShell>
  );
}
