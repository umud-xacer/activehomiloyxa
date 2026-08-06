import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { ComingSoon } from "@/components/layout/ComingSoon";

const faqEntries = [
  { q: "What is ActiveHome?", a: "ActiveHome is an AI-powered global super app for buying, renting, building, furnishing and booking homes." },
  { q: "In which countries is ActiveHome available?", a: "ActiveHome aggregates verified listings and partners across 10+ countries and is expanding globally." },
  { q: "How does the AI valuation work?", a: "Our AI models estimate property value using comparable sales, location signals and market trends." },
  { q: "Is it free to browse properties?", a: "Yes, browsing verified properties on ActiveHome is free. Professional plans unlock advanced tools." },
];

export const Route = createFileRoute("/faq")({
  head: () => ({
    meta: [
      { title: "FAQ — Answers about ActiveHome" },
      { name: "description", content: "Common questions about ActiveHome's property marketplace, AI tools, bookings and services." },
      { property: "og:title", content: "FAQ — Answers about ActiveHome" },
      { property: "og:description", content: "Common questions about ActiveHome's property marketplace, AI tools and services." },
      { property: "og:type", content: "website" },
      { property: "og:url", content: "https://active-home.lovable.app/faq" },
    ],
    links: [{ rel: "canonical", href: "https://active-home.lovable.app/faq" }],
    scripts: [
      {
        type: "application/ld+json",
        children: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: faqEntries.map((e) => ({
            "@type": "Question",
            name: e.q,
            acceptedAnswer: { "@type": "Answer", text: e.a },
          })),
        }),
      },
    ],
  }),
  component: Page,
});


function Page() {
  return (
    <AppShell>
      <PageHeader eyebrow="Help" title="FAQ" description="Answers to the most common questions." />
      <ComingSoon wave={5} page="FAQ" />
    </AppShell>
  );
}
