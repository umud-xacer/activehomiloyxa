import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/landscape")({
  head: () => ({
    meta: [
      { title: "Landscape design — ActiveHome" },
      {
        name: "description",
        content: "Bring outdoor spaces to life with expert landscape designers.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Design"
        title="Landscape design"
        description="Bring outdoor spaces to life with expert landscape designers."
      />
      <ComingSoon wave={3} page="Landscape design" />
    </AppShell>
  );
}
