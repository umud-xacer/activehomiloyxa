import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/terms")({
  head: () => ({
    meta: [
      { title: "Foydalanish shartlari — ActiveHome" },
      { name: "description", content: "Platformadan foydalanish qoidalari va shartlari." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Huquqiy"
        title="Foydalanish shartlari"
        description="Platformadan foydalanish qoidalari va shartlari."
      />
      <ComingSoon wave={5} page="Foydalanish shartlari" />
    </AppShell>
  );
}
