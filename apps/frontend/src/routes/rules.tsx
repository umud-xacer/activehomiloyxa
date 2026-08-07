import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/rules")({
  head: () => ({
    meta: [
      { title: "E'lon qoidalari — ActiveHome" },
      {
        name: "description",
        content: "E'lon joylashtirish, tahrirlash va nazorat qilish tartib-qoidalari.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Huquqiy"
        title="E'lon qoidalari"
        description="E'lon joylashtirish, tahrirlash va nazorat qilish tartib-qoidalari."
      />
      <ComingSoon wave={5} page="E'lon qoidalari" />
    </AppShell>
  );
}
