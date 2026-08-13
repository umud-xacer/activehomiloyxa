import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/blog")({
  head: () => ({
    meta: [
      { title: "Blog — Real estate insights | ActiveHome" },
      {
        name: "description",
        content:
          "Market analysis, product updates and stories from the ActiveHome team and partner network.",
      },
      { property: "og:title", content: "Blog — Real estate insights | ActiveHome" },
      {
        property: "og:description",
        content: "Market analysis, product updates and stories from the ActiveHome team.",
      },
      { property: "og:type", content: "article" },
      { property: "og:url", content: "https://activehome.uz/blog" },
    ],
    links: [{ rel: "canonical", href: "https://activehome.uz/blog" }],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Writing"
        title="Blog"
        description="Insights from the ActiveHome team and partners."
      />
      <ComingSoon wave={5} page="Blog" />
    </AppShell>
  );
}
