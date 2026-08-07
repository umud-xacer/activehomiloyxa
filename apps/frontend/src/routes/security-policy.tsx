import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/security-policy")({
  head: () => ({
    meta: [
      { title: "Xavfsizlik siyosati — ActiveHome" },
      {
        name: "description",
        content: "Foydalanuvchi va platforma xavfsizligini ta'minlash bo'yicha choralar.",
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
        title="Xavfsizlik siyosati"
        description="Foydalanuvchi va platforma xavfsizligini ta'minlash bo'yicha choralar."
      />
      <ComingSoon wave={5} page="Xavfsizlik siyosati" />
    </AppShell>
  );
}
