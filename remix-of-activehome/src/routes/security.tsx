import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/security")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Security — ActiveHome" },
      { name: "description", content: "Two-factor auth, sessions and security alerts." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Account" title="Security" description="Two-factor auth, sessions and security alerts." />
      <ComingSoon wave={2} page="Security" />
    </AppShell>
  );
}
