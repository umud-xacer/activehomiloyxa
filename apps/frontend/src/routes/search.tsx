import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/search")({
  head: () => ({
    meta: [
      { title: "Search — ActiveHome" },
      {
        name: "description",
        content: "Search properties, hotels, materials and services across the world.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Discovery"
        title="Search"
        description="Search properties, hotels, materials and services across the world."
      />
      <ComingSoon wave={1} page="Search" />
    </AppShell>
  );
}
