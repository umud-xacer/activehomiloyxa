import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Contact — ActiveHome" },
      { name: "description", content: "Reach the ActiveHome team." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Talk to us" title="Contact" description="Reach the ActiveHome team." />
      <ComingSoon wave={5} page="Contact" />
    </AppShell>
  );
}
