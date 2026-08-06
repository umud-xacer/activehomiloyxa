import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/payments")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Payments — ActiveHome" },
      { name: "description", content: "Your transactions, invoices and payout settings." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Money"
        title="Payments"
        description="Your transactions, invoices and payout settings."
      />
      <ComingSoon wave={4} page="Payments" />
    </AppShell>
  );
}
