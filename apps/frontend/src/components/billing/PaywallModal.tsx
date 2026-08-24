/**
 * Listing paywall (2026-08-23): opens when `createListing` returns `awaitingPayment: true` --
 * the listing already exists as a held `DRAFT` (`Listing.awaiting_payment`, catalog's own domain
 * field), so nothing is lost if the buyer closes this without paying; they just return to `/list`
 * to try again later, same listing waiting for them.
 *
 * Two purchase shapes, both real `createOrder` calls (`billing.domain.value_objects.TargetRef`'s
 * own invariant): the single-listing option targets `targetType: "LISTING"` with this exact
 * listing's id, the three credit packs target `targetType: "PROFILE"` (no `targetId` -- the
 * acting profile identifies it implicitly, same convention `subscriptions.tsx`'s own
 * `BuyPlanCard` already establishes). A credit pack purchase does NOT itself publish this
 * listing -- the buyer still needs to re-submit `/list` afterwards so the backend's own
 * `auto_compute_payment_requirement` consumes the now-available credit (Phase 4's own design);
 * this modal's copy says so rather than implying an automatic retry that doesn't exist.
 *
 * Real Payme/Click checkout buttons mirror `subscriptions.tsx`'s `GatewayCheckoutButtons`
 * exactly (same keyless-first "sozlanmagan" fallback). The demo button always works regardless
 * of real credentials -- it's the one place `POST /payments/mock/pay` is called from, gated
 * server-side on `PAYMENT_PROVIDER=mock` (a 404 here means demo payments are off, not a bug).
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CreditCard, Loader2, Sparkles } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/http";
import { billingApi, type Invoice, type Order, type Product } from "@/lib/billing-client";
import {
  buildClickCheckoutUrl,
  buildPaymeCheckoutUrl,
  getClickMerchantId,
  getClickServiceId,
  getPaymeMerchantId,
  mockPay,
} from "@/lib/payment-gateways";

function planName(product: Product): string {
  return product.name.uz_latn || product.name.ru || product.name.en || product.code;
}

function formatSom(product: Product): string {
  return `${Number(product.price.amount).toLocaleString("uz-UZ")} so'm`;
}

interface PaywallModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listingId: string;
  categoryId?: string;
  /** Called once the demo payment confirms — the caller navigates to the now-published listing. */
  onActivated: () => void;
}

type SelectedPlan = { product: Product; targetType: "LISTING" | "PROFILE" };

export function PaywallModal({
  open,
  onOpenChange,
  listingId,
  categoryId,
  onActivated,
}: PaywallModalProps) {
  const [selected, setSelected] = useState<SelectedPlan | null>(null);
  const [order, setOrder] = useState<{ order: Order; invoice: Invoice } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activated, setActivated] = useState(false);

  const { data: plans, isLoading } = useQuery({
    queryKey: ["billing", "pricing-plans", categoryId ?? null],
    queryFn: () => billingApi.getPricingPlans(categoryId),
    enabled: open,
  });

  const reset = () => {
    setSelected(null);
    setOrder(null);
    setError(null);
    setActivated(false);
  };

  const handleClose = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const choosePlan = async (plan: SelectedPlan) => {
    setSelected(plan);
    setError(null);
    setBusy(true);
    try {
      const createdOrder = await billingApi.createOrder({
        productId: plan.product.id,
        targetType: plan.targetType,
        targetId: plan.targetType === "LISTING" ? listingId : undefined,
      });
      const invoice = await billingApi.getOrderInvoice(createdOrder.id);
      setOrder({ order: createdOrder, invoice });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Buyurtma yaratib bo'lmadi.");
      setSelected(null);
    } finally {
      setBusy(false);
    }
  };

  const payWithDemo = async (providerLabel: string) => {
    if (!order) return;
    setBusy(true);
    setError(null);
    try {
      await mockPay(order.invoice.id, providerLabel);
      setActivated(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "To'lovni amalga oshirib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  if (activated) {
    const isListingTarget = selected?.targetType === "LISTING";
    return (
      <Dialog open={open} onOpenChange={handleClose}>
        <DialogContent className="max-w-md">
          <div className="flex flex-col items-center gap-3 py-4 text-center">
            <CheckCircle2 className="size-12 text-primary" />
            <p className="font-display text-lg font-semibold text-foreground">
              {isListingTarget
                ? "E'loningiz muvaffaqiyatli chop etildi!"
                : "To'lov muvaffaqiyatli qabul qilindi!"}
            </p>
            <p className="text-sm text-muted-foreground">
              {isListingTarget
                ? "Endi e'loningiz saytda barchaga ko'rinadi."
                : "Paketingiz balansingizga qo'shildi. E'loningizni chop etish uchun \"E'lonni chop etish\" tugmasini yana bosing."}
            </p>
            <button
              type="button"
              onClick={() => {
                handleClose(false);
                onActivated();
              }}
              className="mt-2 inline-flex items-center justify-center rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            >
              Davom etish
            </button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>E'lonni chop etish uchun to'lov</DialogTitle>
          <DialogDescription>
            E'loningiz tayyor — uni saytda ko'rsatish uchun bir martalik to'lov qiling yoki
            paketlardan birini sotib oling.
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Narxlar yuklanmoqda…
          </div>
        )}

        {!isLoading && plans && !order && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {plans.singleListing && (
              <PlanCard
                title="Bir martalik joylash"
                product={plans.singleListing}
                highlight={false}
                busy={busy}
                onSelect={() =>
                  plans.singleListing &&
                  choosePlan({ product: plans.singleListing, targetType: "LISTING" })
                }
              />
            )}
            {plans.creditPacks.map((pack) => (
              <PlanCard
                key={pack.id}
                title={planName(pack)}
                product={pack}
                highlight={pack.code === "listing-credit-pack-biznes"}
                busy={busy}
                onSelect={() => choosePlan({ product: pack, targetType: "PROFILE" })}
              />
            ))}
          </div>
        )}

        {order && (
          <div className="rounded-2xl border border-primary/30 bg-primary/5 p-5">
            <p className="text-sm text-muted-foreground">
              Hisob-faktura №{order.invoice.invoiceNumber} —{" "}
              <span className="font-semibold text-foreground">
                {Number(order.invoice.amount.amount).toLocaleString("uz-UZ")}{" "}
                {order.invoice.amount.currency}
              </span>
              . To'lov usulini tanlang.
            </p>
            <GatewayButtons invoice={order.invoice} busy={busy} onDemoPay={payWithDemo} />
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
      </DialogContent>
    </Dialog>
  );
}

function PlanCard({
  title,
  product,
  highlight,
  busy,
  onSelect,
}: {
  title: string;
  product: Product;
  highlight: boolean;
  busy: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onSelect}
      className={`flex flex-col items-start rounded-2xl border p-4 text-left transition disabled:opacity-60 ${
        highlight
          ? "border-primary/50 bg-primary/5 hover:bg-primary/10"
          : "border-border bg-background hover:bg-muted"
      }`}
    >
      {highlight && (
        <span className="mb-1.5 inline-flex items-center gap-1 rounded-full bg-primary px-2.5 py-0.5 text-[11px] font-semibold text-primary-foreground">
          <Sparkles className="size-3" /> Eng foydali
        </span>
      )}
      <p className="font-display text-sm font-semibold text-foreground">{title}</p>
      {product.description && (
        <p className="mt-1 text-xs text-muted-foreground">
          {product.description.uz_latn || product.description.ru || product.description.en}
        </p>
      )}
      <p className="mt-2 text-lg font-semibold text-foreground">{formatSom(product)}</p>
    </button>
  );
}

/** Mirrors `subscriptions.tsx`'s own `GatewayCheckoutButtons` for Payme/Click (real checkout URL
 * / "sozlanmagan" fallback, unmodified), plus the demo button this modal actually needs. */
function GatewayButtons({
  invoice,
  busy,
  onDemoPay,
}: {
  invoice: Invoice;
  busy: boolean;
  onDemoPay: (providerLabel: string) => void;
}) {
  const paymeMerchantId = getPaymeMerchantId();
  const clickServiceId = getClickServiceId();
  const clickMerchantId = getClickMerchantId();

  return (
    <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
      {paymeMerchantId ? (
        <a
          href={buildPaymeCheckoutUrl(paymeMerchantId, invoice)}
          className="inline-flex items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        >
          <CreditCard className="size-4" /> Payme orqali to'lash
        </a>
      ) : (
        <p className="rounded-full border border-dashed border-border px-4 py-2.5 text-center text-xs text-muted-foreground">
          Payme hali sozlanmagan
        </p>
      )}
      {clickServiceId && clickMerchantId ? (
        <a
          href={buildClickCheckoutUrl(clickServiceId, clickMerchantId, invoice)}
          className="inline-flex items-center justify-center gap-2 rounded-full border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted"
        >
          <CreditCard className="size-4" /> Click orqali to'lash
        </a>
      ) : (
        <p className="rounded-full border border-dashed border-border px-4 py-2.5 text-center text-xs text-muted-foreground">
          Click hali sozlanmagan
        </p>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => onDemoPay("UZUM")}
        className="inline-flex items-center justify-center gap-2 rounded-full border border-border bg-background px-4 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted disabled:opacity-60 sm:col-span-2"
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <CreditCard className="size-4" />}
        Uzum Pay orqali to'lash (Demo)
      </button>
    </div>
  );
}
