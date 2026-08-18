import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { zodValidator } from "@tanstack/zod-adapter";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { z } from "zod";
import { Search as SearchIcon, Loader2, Package, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { searchApi, type SearchHit } from "@/lib/search-client";
import { formatUzs } from "@/lib/catalog-client";

const searchSchema = z.object({
  q: z.string().optional().catch(undefined),
});

export const Route = createFileRoute("/search")({
  validateSearch: zodValidator(searchSchema),
  head: () => ({
    meta: [
      { title: "Qidiruv — ActiveHome" },
      {
        name: "description",
        content: "Mahsulot, xizmat va tashkilotlarni butun ActiveHome bo'ylab qidiring.",
      },
    ],
  }),
  component: Page,
});

function ResultCard({ hit, index }: { hit: SearchHit; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.04, 0.3), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/listing/$listingId"
        params={{ listingId: hit.listingId }}
        className="group flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
      >
        <div className="aspect-[4/3] w-full overflow-hidden bg-muted">
          {hit.thumbnailUrl ? (
            <img
              src={hit.thumbnailUrl}
              alt={hit.title}
              className="size-full object-cover transition duration-300 group-hover:scale-105"
            />
          ) : (
            <div className="flex size-full items-center justify-center">
              <Package className="size-8 text-muted-foreground/50" />
            </div>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-1.5 p-4">
          {hit.categoryPath && (
            <p className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {hit.categoryPath.replace(/^\//, "").replace(/\//g, " / ")}
            </p>
          )}
          <p className="line-clamp-2 font-display text-sm font-semibold text-foreground">
            {hit.title}
          </p>
          <div className="mt-auto flex items-center justify-between pt-1">
            {hit.price ? (
              <span className="text-sm font-semibold text-primary">
                {formatUzs(hit.price.amount)}
              </span>
            ) : (
              <span />
            )}
            {hit.verifiedBadge && (
              <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success">
                <ShieldCheck className="size-3" /> Tasdiqlangan
              </span>
            )}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

function Page() {
  const { q } = Route.useSearch();
  const navigate = Route.useNavigate();
  const [inputValue, setInputValue] = useState(q ?? "");

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => searchApi.search({ q, limit: 24 }),
    enabled: !!q && q.trim().length > 0,
  });

  function submit() {
    const trimmed = inputValue.trim();
    navigate({ search: { q: trimmed || undefined } });
  }

  return (
    <AppShell>
      <PageHeader
        eyebrow="Qidiruv"
        title={q ? `"${q}" bo'yicha natijalar` : "Qidiruv"}
        description="Mahsulot, xizmat va tashkilotlarni butun ActiveHome bo'ylab qidiring."
      />
      <div className="mx-auto max-w-6xl px-6 py-10">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="glass mx-auto mb-10 flex max-w-xl items-center gap-2 rounded-2xl px-4 py-2.5 shadow-soft"
        >
          <SearchIcon className="size-4 shrink-0 text-muted-foreground" />
          <input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Mahsulot, xizmat yoki kategoriya nomini kiriting…"
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
          />
          <button
            type="submit"
            className="shrink-0 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            Qidirish
          </button>
        </form>

        {!q && (
          <EmptyState
            icon={SearchIcon}
            title="Qidiruvni boshlang"
            description="Yuqoridagi qutiga mahsulot, xizmat yoki kategoriya nomini kiriting."
          />
        )}

        {q && isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" /> Qidirilmoqda…
          </div>
        )}

        {q && !isLoading && data && data.items.length === 0 && (
          <EmptyState
            icon={SearchIcon}
            title="Hech narsa topilmadi"
            description="Boshqa so'z bilan qayta urinib ko'ring yoki kategoriyalar bo'yicha ko'rib chiqing."
          />
        )}

        {q && data && data.items.length > 0 && (
          <>
            {data.degraded && (
              <p className="mb-4 rounded-xl bg-warning/10 px-3 py-2 text-xs text-warning">
                Qidiruv tizimi vaqtincha cheklangan rejimda ishlayapti — natijalar to'liq
                bo'lmasligi mumkin.
              </p>
            )}
            <div
              className={`grid grid-cols-1 gap-5 transition-opacity sm:grid-cols-2 lg:grid-cols-4 ${isFetching ? "opacity-60" : ""}`}
            >
              {data.items.map((hit, i) => (
                <ResultCard key={hit.listingId} hit={hit} index={i} />
              ))}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
