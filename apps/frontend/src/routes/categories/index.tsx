import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Tag } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { catalogClient, type CategorySummary } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
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

function CategoryGrid({
  categories,
  allCategories,
}: {
  categories: CategorySummary[];
  allCategories: CategorySummary[];
}) {
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {categories.map((cat) => {
        const childCount = allCategories.filter(
          (c) => c.status === "ACTIVE" && c.parentId === cat.id,
        ).length;
        return (
          <Link
            key={cat.id}
            to={categoryHref(cat.path)}
            className="group flex flex-col items-center gap-2.5 rounded-2xl border border-border bg-card p-5 text-center shadow-soft transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-elevated"
          >
            <div className="flex size-14 items-center justify-center overflow-hidden rounded-2xl bg-primary/10 text-primary transition group-hover:scale-105">
              {cat.iconUrl ? (
                <img src={cat.iconUrl} alt="" className="size-full object-cover" />
              ) : (
                <Tag className="size-5" />
              )}
            </div>
            <span className="font-display text-sm font-semibold text-foreground">
              {categoryLabel(cat.name, "uz")}
            </span>
            {childCount > 0 && (
              <span className="text-[11px] text-muted-foreground">
                {childCount} ta kichik kategoriya
              </span>
            )}
          </Link>
        );
      })}
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
          <CategoryGrid categories={topLevel} allCategories={allCategories} />
        )}
      </Container>
    </AppShell>
  );
}
