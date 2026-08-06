import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";

export const Route = createFileRoute("/furniture")({
  head: () => ({
    meta: [
      { title: "Furniture — ActiveHome" },
      { name: "description", content: "Furnish your home from designer brands and local makers." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Shop" title="Furniture" description="Furnish your home from designer brands and local makers." />
      <CategoryListingsSection categoryPath="furniture" />
    </AppShell>
  );
}
