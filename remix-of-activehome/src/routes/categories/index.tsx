import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { categoriesOptions } from "@/features/properties/queries";

export const Route = createFileRoute("/categories/")({
  head: () => ({
    meta: [
      { title: "Categories — ActiveHome" },
      { name: "description", content: "Every category in the ActiveHome ecosystem." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: categories, isLoading } = useQuery(categoriesOptions());

  return (
    <AppShell>
      <PageHeader eyebrow="Browse" title="Categories" description="Every category in the ActiveHome ecosystem." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-32 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {categories?.map((c) => (
              <Link
                key={c.id}
                to="/categories/$slug"
                params={{ slug: c.path }}
                className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-card p-6 text-center shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated"
              >
                <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Building2 className="size-6" />
                </div>
                <span className="text-sm font-semibold text-foreground">{c.name.uz_latn ?? c.path}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
