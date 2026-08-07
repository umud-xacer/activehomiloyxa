import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/offer")({
  head: () => ({
    meta: [
      { title: "Ommaviy oferta — ActiveHome" },
      {
        name: "description",
        content: "Xizmatlardan foydalanish yuzasidan ommaviy taklif (oferta) shartlari.",
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
        title="Ommaviy oferta"
        description="Xizmatlardan foydalanish yuzasidan ommaviy taklif (oferta) shartlari."
      />
      <ComingSoon wave={5} page="Ommaviy oferta" />
    </AppShell>
  );
}
