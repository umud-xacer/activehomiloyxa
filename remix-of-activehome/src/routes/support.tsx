import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/support")({
  head: () => ({
    meta: [
      { title: "Support center — ActiveHome" },
      { name: "description", content: "Get help with your account, bookings or listings." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Help" title="Support center" description="Get help with your account, bookings or listings." />
      <ComingSoon wave={5} page="Support center" />
    </AppShell>
  );
}
