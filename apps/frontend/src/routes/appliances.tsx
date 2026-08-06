import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/appliances")({
  head: () => ({
    meta: [
      { title: "Home appliances — ActiveHome" },
      { name: "description", content: "Premium appliances for every room." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Shop"
        title="Home appliances"
        description="Premium appliances for every room."
      />
      <ComingSoon wave={3} page="Home appliances" />
    </AppShell>
  );
}
