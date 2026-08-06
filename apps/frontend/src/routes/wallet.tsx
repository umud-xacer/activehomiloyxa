import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/wallet")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Wallet — ActiveHome" },
      { name: "description", content: "Manage balances, cards and rewards." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Money"
        title="Wallet"
        description="Manage balances, cards and rewards."
      />
      <ComingSoon wave={4} page="Wallet" />
    </AppShell>
  );
}
