import { createFileRoute, redirect } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";

// Same data as /wallet (orders + invoices, billing module) -- kept as a redirect rather than a
// duplicate page so there is one place that renders order/invoice history, not two.
export const Route = createFileRoute("/payments")({
  beforeLoad: async (ctx) => {
    await requireAuth(ctx);
    throw redirect({ to: "/wallet" });
  },
});
