import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { authApi } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { billingApi, type Invoice, type Order, type Product } from "@/lib/billing-client";

export const Route = createFileRoute("/subscriptions")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Obuna boshqaruvi — ActiveHome" },
      { name: "description", content: "Obuna holatingiz, tariflar va to'lovlar tarixi." },
    ],
  }),
  component: Page,
});

function productName(product: Product): string {
  return product.name.uz_latn || product.name.ru || product.name.en || product.code;
}

function termLabel(termDays: number | null | undefined): string {
  if (termDays === 7) return "Haftalik";
  if (termDays === 30) return "Oylik";
  return termDays ? `${termDays} kunlik` : "Obuna";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("uz-UZ", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

const ORDER_STATUS_LABEL: Record<Order["status"], string> = {
  PENDING: "Kutilmoqda",
  INVOICED: "Hisob-faktura chiqarildi",
  PAID: "To'langan",
  FULFILLED: "Faollashtirildi",
  CANCELLED: "Bekor qilindi",
};

const INVOICE_STATUS_LABEL: Record<Invoice["status"], string> = {
  ISSUED: "To'lov kutilmoqda",
  PAID: "To'langan",
  VOID: "Bekor qilingan",
};

function StatusBanner({ ownedProfileId }: { ownedProfileId: string }) {
  const { data: entitlement, isLoading } = useQuery({
    queryKey: ["billing", "my-subscription", ownedProfileId],
    queryFn: () => billingApi.getSubscriptionEntitlement(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-3xl border border-border bg-card p-6 text-sm text-muted-foreground shadow-soft">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  const active =
    entitlement &&
    entitlement.activationState === "ACTIVE" &&
    new Date(entitlement.validUntil) > new Date();

  if (active && entitlement) {
    return (
      <div className="flex items-center gap-4 rounded-3xl border border-success/30 bg-success/5 p-6 shadow-soft">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-success/15 text-success">
          <ShieldCheck className="size-6" />
        </div>
        <div>
          <p className="font-display text-lg font-semibold text-foreground">Obuna faol</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {formatDate(entitlement.validUntil)} sanasigacha amal qiladi.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-4 rounded-3xl border border-warning/30 bg-warning/5 p-6 shadow-soft">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-warning/15 text-warning">
        <ShieldAlert className="size-6" />
      </div>
      <div>
        <p className="font-display text-lg font-semibold text-foreground">
          {entitlement ? "Obuna muddati tugagan" : "Obuna mavjud emas"}
        </p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {entitlement
            ? `${formatDate(entitlement.validUntil)} sanasida tugagan. Biznes profilingiz va e'lonlaringiz ommaviy katalogda ko'rinmaydi.`
            : "Biznes profilingiz va xizmatlaringizni faol saqlash uchun tarif tanlang."}
        </p>
      </div>
    </div>
  );
}

function BuyPlanCard({
  product,
  ownedProfileId,
  onBought,
}: {
  product: Product;
  ownedProfileId: string;
  onBought: (order: Order) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buy = async () => {
    setBusy(true);
    setError(null);
    try {
      await authApi.switchActingProfile(ownedProfileId);
      // PROFILE-targeted orders must NOT carry a targetId -- the acting profile switched to
      // above already identifies it implicitly (billing.domain.value_objects.TargetRef's own
      // invariant: "PROFILE targets must not carry a target_id").
      const order = await billingApi.createOrder({ productId: product.id, targetType: "PROFILE" });
      onBought(order);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Buyurtma yaratib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col rounded-2xl border border-border bg-background p-5">
      <span className="inline-flex w-fit items-center gap-1 rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
        {termLabel(product.termDays)}
      </span>
      <p className="mt-2 font-display text-lg font-semibold text-foreground">
        {productName(product)}
      </p>
      <p className="mt-1 text-2xl font-semibold text-foreground">
        {Number(product.price.amount).toLocaleString("uz-UZ")}{" "}
        <span className="text-sm font-normal text-muted-foreground">{product.price.currency}</span>
      </p>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      <button
        type="button"
        onClick={buy}
        disabled={busy}
        className="mt-4 inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
      >
        {busy && <Loader2 className="size-4 animate-spin" />}
        Sotib olish
      </button>
    </div>
  );
}

function PlanPicker({ ownedProfileId }: { ownedProfileId: string }) {
  const queryClient = useQueryClient();
  const [justOrdered, setJustOrdered] = useState<{ order: Order; invoice: Invoice } | null>(null);
  const { data: products, isLoading } = useQuery({
    queryKey: ["billing", "products", "SUBSCRIPTION"],
    queryFn: () => billingApi.listProducts("SUBSCRIPTION"),
  });

  const handleBought = async (order: Order) => {
    const invoice = await billingApi.getOrderInvoice(order.id);
    setJustOrdered({ order, invoice });
    queryClient.invalidateQueries({ queryKey: ["billing"] });
  };

  if (justOrdered) {
    return (
      <div className="rounded-2xl border border-primary/30 bg-primary/5 p-6">
        <div className="flex items-center gap-2 text-primary">
          <CheckCircle2 className="size-5" />
          <p className="font-display text-base font-semibold">So'rovingiz qabul qilindi</p>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Hisob-faktura №{justOrdered.invoice.invoiceNumber} —{" "}
          {Number(justOrdered.invoice.amount.amount).toLocaleString("uz-UZ")}{" "}
          {justOrdered.invoice.amount.currency}. To'lovni amalga oshiring va admin tasdiqlagach
          obunangiz avtomatik faollashadi.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  if (!products || products.length === 0) {
    return (
      <EmptyState
        icon={CalendarClock}
        title="Tariflar hali sozlanmagan"
        description="Tez orada qo'shiladi."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {products
        .slice()
        .sort((a, b) => (a.termDays ?? 0) - (b.termDays ?? 0))
        .map((product) => (
          <BuyPlanCard
            key={product.id}
            product={product}
            ownedProfileId={ownedProfileId}
            onBought={handleBought}
          />
        ))}
    </div>
  );
}

function HistorySection() {
  const { data: orders, isLoading } = useQuery({
    queryKey: ["billing", "my-orders"],
    queryFn: () => billingApi.listMyOrders(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-6 py-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }

  if (!orders || orders.length === 0) {
    return (
      <div className="px-6 py-8">
        <EmptyState
          icon={Clock}
          title="Buyurtmalar tarixi bo'sh"
          description="Hali obuna sotib olinmagan."
        />
      </div>
    );
  }

  return (
    <div className="divide-y divide-border/70">
      {orders.map((order) => (
        <div key={order.id} className="flex items-center justify-between gap-4 px-6 py-4">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {Number(order.amount.amount).toLocaleString("uz-UZ")} {order.amount.currency}
            </p>
            <p className="text-xs text-muted-foreground">{formatDate(order.createdAt)}</p>
          </div>
          <span
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              order.status === "FULFILLED"
                ? "bg-success/10 text-success"
                : order.status === "CANCELLED"
                  ? "bg-destructive/10 text-destructive"
                  : "bg-muted text-muted-foreground"
            }`}
          >
            {ORDER_STATUS_LABEL[order.status]}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Every billing call here is scoped to the session's acting profile (`_acting_profile` in
 * `billing/interfaces/routers.py`) -- switches into it once on mount so the status/history
 * queries below don't 422 with `NoActingProfileError` before the buy flow's own switch runs. */
function useActingProfileReady(ownedProfileId: string | undefined): boolean {
  const { data, isFetched } = useQuery({
    queryKey: ["auth", "switch-acting-profile", ownedProfileId],
    queryFn: () => authApi.switchActingProfile(ownedProfileId ?? null),
    enabled: !!ownedProfileId,
  });
  return !ownedProfileId || (isFetched && data?.actingProfileId === ownedProfileId);
}

function Page() {
  const { data: account } = useMe();
  const ownedProfileId = (account?.ownedProfileIds ?? [])[0];
  const ready = useActingProfileReady(ownedProfileId);
  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <h1 className="font-display text-3xl font-semibold tracking-tight">Obuna boshqaruvi</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Biznes profilingiz va e'lonlaringizni faol saqlash uchun obunangizni shu yerdan
            boshqaring.
          </p>
        </motion.div>

        {!ownedProfileId ? (
          <SectionCard title="Biznes profil topilmadi" icon={ShieldAlert} index={0}>
            <p className="text-sm text-muted-foreground">
              Obuna sotib olish uchun avval biznes profilingizni yarating.
            </p>
          </SectionCard>
        ) : !ready ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        ) : (
          <>
            <StatusBanner ownedProfileId={ownedProfileId} />
            <SectionCard title="Tarif tanlash" icon={CalendarClock} index={1}>
              <PlanPicker ownedProfileId={ownedProfileId} />
            </SectionCard>
            <SectionCard title="Buyurtmalar tarixi" icon={Clock} index={2} noPadding>
              <HistorySection />
            </SectionCard>
          </>
        )}
      </div>
    </DashboardShell>
  );
}
