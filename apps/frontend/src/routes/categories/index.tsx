import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { catalogClient, type CategorySummary } from "@/lib/catalog-client";
import { CategoryChip } from "@/components/catalog/CategoryChip";
import { Container } from "@/components/layout/Container";

function categoryHref(path: string): string {
  return `/categories/${path.replace(/^\//, "")}`;
}

export const Route = createFileRoute("/categories/")({
  head: () => ({
    meta: [
      { title: "Kategoriyalar — ActiveHome" },
      { name: "description", content: "ActiveHome platformasidagi barcha kategoriyalar." },
    ],
  }),
  component: Page,
});

function CategoryGrid({ categories }: { categories: CategorySummary[] }) {
  // Compact real-photo pills, same at every width -- see CategoryChip's own docstring for why
  // this replaced the old centered icon-over-label card grid.
  return (
    <div className="flex flex-wrap gap-2">
      {categories.map((cat, i) => (
        <CategoryChip key={cat.id} category={cat} href={categoryHref(cat.path)} index={i} />
      ))}
    </div>
  );
}

function Page() {
  const { data: allCategories = [], isLoading } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });

  const topLevel = allCategories.filter((c) => c.status === "ACTIVE" && c.parentId === null);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Bo'limlar"
        title="Kategoriyalar"
        description="ActiveHome platformasidagi barcha kategoriyalar — har birining ichida kichik kategoriyalar bo'lishi mumkin."
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "Kategoriyalar" }]}
      />

      <Container wide className="py-10">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Kategoriyalar yuklanmoqda…
          </div>
        ) : topLevel.length === 0 ? (
          <EmptyState title="Kategoriyalar topilmadi" />
        ) : (
          <CategoryGrid categories={topLevel} />
        )}
      </Container>
    </AppShell>
  );
}
