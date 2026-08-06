import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";

export const Route = createFileRoute("/landscape")({
  head: () => ({
    meta: [
      { title: "Landscape design — ActiveHome" },
      { name: "description", content: "Bring outdoor spaces to life with expert landscape designers." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Design" title="Landscape design" description="Bring outdoor spaces to life with expert landscape designers." />
      <CategoryListingsSection categoryPath="landscape" />
    </AppShell>
  );
}
