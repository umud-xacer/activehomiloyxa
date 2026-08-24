/**
 * ADR-0007: gates a role-specific workspace on `account.reviewStatus`. Login itself is never
 * blocked (that's `AccountStatus`, unchanged) -- this only decides whether the dashboard's own
 * content renders, or a waiting/rejected screen does instead, for an otherwise-authenticated
 * visitor.
 */
import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Clock3, XCircle, Mail, ShieldCheck } from "lucide-react";
import type { Account } from "@/lib/auth-client";

/** Renders inside `DashboardShell`'s own header/sidebar chrome -- just the centered message,
 * no second header (DashboardShell already provides one). */
function GateShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative mx-auto flex min-h-[70vh] max-w-lg flex-col items-center justify-center px-6 py-16 text-center">
      <div className="gradient-mesh pointer-events-none absolute inset-0 -z-10 opacity-40" />
      {children}
    </div>
  );
}

export function ReviewGate({ account, children }: { account: Account; children: ReactNode }) {
  // `reviewStatus` (ADR-0007) exists to vet a LEGAL_ENTITY/INVESTOR signup for fraud before its
  // workspace unlocks -- a `super-admin`-rolled account already holds the platform's highest
  // trust level (RBAC, granted only via `bootstrap_admin.py`/`assignRole`'s own maker-checker
  // gate), so re-vetting it here would be nonsensical, not protective. Bypass unconditionally,
  // regardless of `accountKind`/`reviewStatus` -- a super-admin should never be blocked out of
  // any dashboard.
  if (account.roles.includes("super-admin")) {
    return <>{children}</>;
  }

  if (account.reviewStatus === "REJECTED") {
    return (
      <GateShell>
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="flex size-16 items-center justify-center rounded-2xl bg-destructive/10 text-destructive shadow-soft"
        >
          <XCircle className="size-7" />
        </motion.div>
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="font-display mt-6 text-2xl font-semibold tracking-tight"
        >
          So'rovingiz rad etildi
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mt-3 text-sm text-muted-foreground"
        >
          {account.reviewReason ||
            "Anketangiz ko'rib chiqildi, lekin hozircha tasdiqlanmadi. Qo'shimcha ma'lumot uchun qo'llab-quvvatlash xizmatiga murojaat qiling."}
        </motion.p>
        <Link
          to="/contact"
          className="mt-7 inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
        >
          <Mail className="size-4" /> Qo'llab-quvvatlash bilan bog'lanish
        </Link>
      </GateShell>
    );
  }

  if (account.reviewStatus === "PENDING") {
    return (
      <GateShell>
        <div className="relative flex size-16 items-center justify-center">
          <motion.span
            animate={{ scale: [1, 1.5], opacity: [0.35, 0] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
            className="absolute inset-0 rounded-2xl bg-primary/30"
          />
          <div className="relative flex size-16 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-soft">
            <Clock3 className="size-7" />
          </div>
        </div>
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="font-display mt-6 text-2xl font-semibold tracking-tight"
        >
          So'rovingiz ko'rib chiqilmoqda
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mt-3 text-sm text-muted-foreground"
        >
          Anketangiz qabul qilindi. Admin uni tasdiqlagach, sizga tegishli panel avtomatik ochiladi
          — bu odatda tez orada bajariladi.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mt-8 flex w-full items-start gap-3 rounded-2xl border border-border bg-card p-4 text-left shadow-soft"
        >
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" />
          <div>
            <div className="text-xs font-semibold text-foreground">Nima uchun kutish kerak?</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Yuridik shaxs va investor akkauntlari firibgarlikning oldini olish uchun admin
              tomonidan qo'lda tasdiqlanadi. (Jismoniy shaxslar bu bosqichni o'tkazib yuboradi.)
            </p>
          </div>
        </motion.div>
      </GateShell>
    );
  }

  return <>{children}</>;
}
