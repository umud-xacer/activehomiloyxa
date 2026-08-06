import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/compare")({
  head: () => ({
    meta: [
      { title: "Compare — ActiveHome" },
      {
        name: "description",
        content: "Compare properties side-by-side across price, area, amenities and AI score.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Compare"
        title="Compare"
        description="Compare properties side-by-side across price, area, amenities and AI score."
      />
      <ComingSoon wave={1} page="Compare" />
    </AppShell>
  );
}
