import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";

export const Route = createFileRoute("/materials")({
  head: () => ({
    meta: [
      { title: "Construction materials — ActiveHome" },
      { name: "description", content: "Order materials from verified suppliers." },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Shop" title="Construction materials" description="Order materials from verified suppliers." />
      <CategoryListingsSection categoryPath="materials" />
    </AppShell>
  );
}
