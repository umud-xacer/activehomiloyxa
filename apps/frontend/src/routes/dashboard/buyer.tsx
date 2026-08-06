import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/dashboard/buyer")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Buyer dashboard — ActiveHome" },
      { name: "description", content: "Track searches, viewings and offers." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Buyer"
        title="Buyer dashboard"
        description="Track searches, viewings and offers."
      />
      <ComingSoon wave={2} page="Buyer dashboard" />
    </AppShell>
  );
}
