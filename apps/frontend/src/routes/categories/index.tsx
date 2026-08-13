import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Loader2, Tag } from "lucide-react";
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
    // Mobile: dense vertical list (icon-left, chevron-right) instead of a centered icon-over-
    // label card grid -- the same responsive-classes-only pattern `ChildrenGrid` in
    // `categories/$.tsx` uses, so both category-navigation surfaces read consistently at every
    // size. `sm:` and up switches to the original centered card grid.
    <div className="flex flex-col gap-2 sm:grid sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
      {categories.map((cat) => {
        const childCount = allCategories.filter(
          (c) => c.status === "ACTIVE" && c.parentId === cat.id,
        ).length;
        return (
          <Link
            key={cat.id}
            to={categoryHref(cat.path)}
            className="group flex items-center gap-3 rounded-xl border border-border bg-card p-3 text-left shadow-soft transition hover:border-primary/40 hover:shadow-elevated sm:flex-col sm:gap-2.5 sm:rounded-2xl sm:p-5 sm:text-center sm:hover:-translate-y-0.5"
          >
            <div className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-primary/10 text-primary transition group-hover:scale-105 sm:size-14">
              {cat.iconUrl ? (
                <img src={cat.iconUrl} alt="" className="size-full object-cover" />
              ) : (
                <Tag className="size-4 sm:size-5" />
              )}
            </div>
            <div className="min-w-0 flex-1 sm:flex-none">
              <span className="block truncate font-display text-sm font-semibold text-foreground">
                {categoryLabel(cat.name, "uz")}
              </span>
              {childCount > 0 && (
                <span className="block text-[11px] text-muted-foreground">
                  {childCount} ta kichik kategoriya
                </span>
              )}
            </div>
            <ChevronRight className="size-4 shrink-0 text-muted-foreground/60 sm:hidden" />
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
