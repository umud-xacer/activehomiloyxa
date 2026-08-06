import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [
      { title: "About ActiveHome — Our mission and team" },
      { name: "description", content: "Meet the team building ActiveHome, the AI-powered global super app for homes and buildings." },
      { property: "og:title", content: "About ActiveHome — Our mission and team" },
      { property: "og:description", content: "The people and vision behind the world's home & building super app." },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://active-home.lovable.app/about" },
    ],
    links: [{ rel: "canonical", href: "https://active-home.lovable.app/about" }],
  }),
  component: Page,
});


function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Company" title="About" description="The team and vision behind ActiveHome." />
      <ComingSoon wave={5} page="About" />
    </AppShell>
  );
}
