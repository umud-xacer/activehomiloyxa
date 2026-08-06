import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";

export const Route = createFileRoute("/interior")({
  head: () => ({
    meta: [
      { title: "Interior design — ActiveHome" },
      { name: "description", content: "Work with interior designers and preview rooms with AI." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Design" title="Interior design" description="Work with interior designers and preview rooms with AI." />
      <CategoryListingsSection categoryPath="interior" />
    </AppShell>
  );
}
