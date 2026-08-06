import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/saved")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Saved searches — ActiveHome" },
      {
        name: "description",
        content: "Re-run searches in one tap and get instant alerts when prices change.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Saved"
        title="Saved searches"
        description="Re-run searches in one tap and get instant alerts when prices change."
      />
      <ComingSoon wave={1} page="Saved searches" />
    </AppShell>
  );
}
