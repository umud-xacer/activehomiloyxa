import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";

export const Route = createFileRoute("/construction")({
  head: () => ({
    meta: [
      { title: "Construction companies — ActiveHome" },
      { name: "description", content: "Hire vetted construction crews and architects." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Build" title="Construction companies" description="Hire vetted construction crews and architects." />
      <CategoryListingsSection categoryPath="construction" />
    </AppShell>
  );
}
