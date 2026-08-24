/**
 * ADR-0010: blocks a LEGAL_ENTITY account's dashboard content once its trial has lapsed and no
 * paid subscription is active, mirroring `ReviewGate.tsx`'s own "centered blocking screen, not a
 * redirect" shape -- `/subscriptions` itself must stay reachable so the account can actually pay,
 * which a `beforeLoad` redirect loop would fight against. Real enforcement is backend/read-model
 * driven regardless (`BusinessProfile.subscriptionStatus`, the public slug endpoint's 404,
 * catalog's suspended listings) -- this is the one place a client-side gate is appropriate, the
 * same "backend is the real boundary" posture `ReviewGate` and every `require-auth.ts` guard
 * documents.
 */
import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { CalendarClock, Loader2, ShieldAlert } from "lucide-react";
import type { Account } from "@/lib/auth-client";
import { businessProfilesApi } from "@/lib/business-profiles-client";

export function SubscriptionGate({ account, children }: { account: Account; children: ReactNode }) {
  const isSuperAdmin = account.roles.includes("super-admin");
  const ownedProfileId = (account.ownedProfileIds ?? [])[0];
  const { data: profile, isLoading } = useQuery({
    queryKey: ["business-profiles", "mine", ownedProfileId],
    queryFn: () => businessProfilesApi.get(ownedProfileId as string),
    enabled: !isSuperAdmin && account.accountKind === "LEGAL_ENTITY" && !!ownedProfileId,
  });

  // Same reasoning as `ReviewGate.tsx`'s own `super-admin` bypass: ADR-0010's subscription
  // requirement exists to gate a paying LEGAL_ENTITY tenant's dashboard, not the platform
  // operator's own account -- bypass unconditionally, regardless of subscriptionStatus. Checked
  // after the hook (Rules of Hooks: every hook must run on every render), not before.
  if (isSuperAdmin) return <>{children}</>;

  if (account.accountKind !== "LEGAL_ENTITY") return <>{children}</>;
  if (!ownedProfileId || isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
      </div>
    );
  }
  if (profile && profile.subscriptionStatus !== "ACTIVE") {
    return (
      <div className="relative mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-6 py-16 text-center">
        <div className="gradient-mesh pointer-events-none absolute inset-0 -z-10 opacity-40" />
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="flex size-16 items-center justify-center rounded-2xl bg-warning/10 text-warning shadow-soft"
        >
          <ShieldAlert className="size-7" />
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="font-display mt-6 text-2xl font-semibold tracking-tight"
        >
          Obunani faollashtiring
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mt-3 text-sm text-muted-foreground"
        >
          {profile.subscriptionStatus === "EXPIRED"
            ? "Bepul sinov muddati yoki obunangiz tugadi."
            : "Sinov muddati hali boshlanmagan."}{" "}
          Landing sahifangiz va e'lonlaringiz obuna faollashtirilguncha saytda ko'rinmaydi.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Link
            to="/subscriptions"
            className="mt-7 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            <CalendarClock className="size-4" /> Tarif tanlash
          </Link>
        </motion.div>
      </div>
    );
  }

  return <>{children}</>;
}
