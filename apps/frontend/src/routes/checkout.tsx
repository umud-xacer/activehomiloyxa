import { createFileRoute } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/checkout")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Checkout — ActiveHome" },
      { name: "description", content: "Secure global checkout with multi-currency support." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Payments"
        title="Checkout"
        description="Secure global checkout with multi-currency support."
      />
      <ComingSoon wave={4} page="Checkout" />
    </AppShell>
  );
}
