import { createFileRoute, redirect } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";

// No cart/multi-item concept exists in the backend (billing.OrderCreateRequest is a single
// product purchase) -- /subscriptions is that single-product "buy" flow, so this redirects
// there rather than duplicating it behind a second, empty "checkout" page.
export const Route = createFileRoute("/checkout")({
  beforeLoad: async (ctx) => {
    await requireAuth(ctx);
    throw redirect({ to: "/subscriptions" });
  },
});
