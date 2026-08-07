import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/refund")({
  head: () => ({
    meta: [
      { title: "To'lovni qaytarish — ActiveHome" },
      { name: "description", content: "To'lovlarni bekor qilish va mablag'ni qaytarish tartibi." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Huquqiy"
        title="To'lovni qaytarish"
        description="To'lovlarni bekor qilish va mablag'ni qaytarish tartibi."
      />
      <ComingSoon wave={5} page="To'lovni qaytarish" />
    </AppShell>
  );
}
