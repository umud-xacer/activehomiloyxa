import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/auth/reset")({
  head: () => ({
    meta: [
      { title: "Reset password — ActiveHome" },
      { name: "description", content: "Recover access to your ActiveHome account." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Account recovery"
        title="Reset password"
        description="Recover access to your ActiveHome account."
      />
      <ComingSoon wave={2} page="Reset password" />
    </AppShell>
  );
}
