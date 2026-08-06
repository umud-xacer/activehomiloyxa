import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/news")({
  head: () => ({
    meta: [
      { title: "News — ActiveHome" },
      { name: "description", content: "Market news, releases and product updates." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Updates"
        title="News"
        description="Market news, releases and product updates."
      />
      <ComingSoon wave={5} page="News" />
    </AppShell>
  );
}
