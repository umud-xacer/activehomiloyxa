import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Check, Loader2, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { billingApi, type Product } from "@/lib/billing-client";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Tariflar — ActiveHome" },
      {
        name: "description",
        content: "Yuridik shaxslar uchun obuna tariflari — biznes profilingizni faol saqlang.",
      },
    ],
  }),
  component: Page,
});

function productName(product: Product): string {
  return product.name.uz_latn || product.name.ru || product.name.en || product.code;
}

function termLabel(termDays: number | null | undefined): string {
  if (termDays === 7) return "haftalik";
  if (termDays === 30) return "oylik";
  return termDays ? `${termDays} kunlik` : "";
}

const BENEFITS = [
  "Biznes profilingiz (landing page) ommaviy katalogda faol bo'ladi",
  "Xizmatlar va e'lonlaringiz qidiruvda ko'rinadi",
  "Mijozlar siz bilan to'g'ridan-to'g'ri bog'lanishi mumkin",
];

function PlanCard({ product, index }: { product: Product; index: number }) {
  const term = termLabel(product.termDays);
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.08, ease: [0.22, 1, 0.36, 1] }}
      className="relative flex flex-col overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
    >
      <div className="mb-2 inline-flex w-fit items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
        <ShieldCheck className="size-3.5" /> {term || "Obuna"}
      </div>
      <h2 className="font-display text-2xl font-semibold text-foreground">
        {productName(product)}
      </h2>
      {product.description && (
        <p className="mt-2 text-sm text-muted-foreground">
          {product.description.uz_latn || product.description.ru || product.description.en}
        </p>
      )}
      <div className="mt-6 flex items-baseline gap-1.5">
        <span className="font-display text-4xl font-semibold text-foreground">
          {Number(product.price.amount).toLocaleString("uz-UZ")}
        </span>
        <span className="text-sm font-medium text-muted-foreground">{product.price.currency}</span>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {product.termDays ? `${product.termDays} kun uchun` : ""}
      </p>
      <ul className="mt-6 space-y-2.5">
        {BENEFITS.map((b) => (
          <li key={b} className="flex items-start gap-2 text-sm text-foreground/80">
            <Check className="mt-0.5 size-4 shrink-0 text-primary" />
            {b}
          </li>
        ))}
      </ul>
      <Link
        to="/subscriptions"
        className="mt-8 inline-flex items-center justify-center rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
      >
        Sotib olish
      </Link>
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const {
    data: products,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["billing", "products", "SUBSCRIPTION"],
    queryFn: () => billingApi.listProducts("SUBSCRIPTION"),
  });

  return (
    <AppShell>
      <PageHeader
        eyebrow="Yuridik shaxslar uchun"
        title="Obuna tariflari"
        description="Biznes profilingiz va xizmatlaringiz platformada faol bo'lishi uchun tarif tanlang. To'lov admin tomonidan tasdiqlangach obuna faollashadi."
      />
      <div className="mx-auto max-w-5xl px-6 py-16">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {error && (
          <p className="py-16 text-center text-sm text-destructive">
            Tariflarni yuklab bo'lmadi. Birozdan so'ng qayta urinib ko'ring.
          </p>
        )}
        {products && products.length === 0 && (
          <p className="py-16 text-center text-sm text-muted-foreground">
            Hozircha tariflar sozlanmagan. Tez orada qo'shiladi.
          </p>
        )}
        {products && products.length > 0 && (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {products
              .slice()
              .sort((a, b) => (a.termDays ?? 0) - (b.termDays ?? 0))
              .map((product, i) => (
                <PlanCard key={product.id} product={product} index={i} />
              ))}
          </div>
        )}
        {!account && !isLoading && (
          <p className="mt-10 text-center text-sm text-muted-foreground">
            Obuna sotib olish uchun avval{" "}
            <Link to="/auth/sign-up" className="font-medium text-primary hover:underline">
              yuridik shaxs sifatida ro'yxatdan o'ting
            </Link>
            .
          </p>
        )}
      </div>
    </AppShell>
  );
}
