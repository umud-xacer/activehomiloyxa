import type { LucideIcon } from "lucide-react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { motion } from "framer-motion";
import { AreaChart, Area, ResponsiveContainer } from "recharts";

export interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: string | number;
  suffix?: string;
  /** e.g. "+12.4%" or "-3 today" -- sign determines tone; omit for neutral */
  delta?: string;
  deltaTone?: "up" | "down" | "neutral";
  /** Optional inline sparkline data (last N points) for a premium Stripe-style trend hint. */
  spark?: number[];
  index?: number;
  accent?: "primary" | "success" | "warning" | "info";
}

const ACCENTS = {
  primary: { icon: "bg-primary/10 text-primary", spark: "var(--primary)" },
  success: { icon: "bg-success/10 text-success", spark: "oklch(0.72 0.16 155)" },
  warning: { icon: "bg-amber-500/10 text-amber-600", spark: "oklch(0.75 0.16 80)" },
  info: { icon: "bg-sky-500/10 text-sky-600", spark: "oklch(0.7 0.14 220)" },
} as const;

export function StatCard({
  icon: Icon,
  label,
  value,
  suffix,
  delta,
  deltaTone = "neutral",
  spark,
  index = 0,
  accent = "primary",
}: StatCardProps) {
  const tones = ACCENTS[accent];
  const DeltaIcon = deltaTone === "up" ? TrendingUp : deltaTone === "down" ? TrendingDown : Minus;
  const deltaClass =
    deltaTone === "up"
      ? "bg-success/10 text-success"
      : deltaTone === "down"
        ? "bg-destructive/10 text-destructive"
        : "bg-muted text-muted-foreground";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
      className="group relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-elevated"
    >
      {spark && spark.length > 1 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 opacity-40 transition-opacity group-hover:opacity-70">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark.map((v, i) => ({ i, v }))}>
              <defs>
                <linearGradient id={`spark-${label}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tones.spark} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={tones.spark} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={tones.spark}
                strokeWidth={1.5}
                fill={`url(#spark-${label})`}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="relative flex items-start justify-between">
        <div
          className={`flex size-9 items-center justify-center rounded-xl shadow-soft ${tones.icon}`}
        >
          <Icon className="size-4" />
        </div>
        {delta && (
          <span
            className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ${deltaClass}`}
          >
            <DeltaIcon className="size-3" /> {delta}
          </span>
        )}
      </div>
      <div className="relative font-display mt-4 text-3xl font-semibold tracking-tight text-foreground">
        {value}
        {suffix && <span className="text-base text-muted-foreground">{suffix}</span>}
      </div>
      <div className="relative mt-1 text-xs text-muted-foreground">{label}</div>
    </motion.div>
  );
}
