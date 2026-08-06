/**
 * Placeholder ad slot. Reserves layout space between homepage sections (and in the side gutters
 * on wide screens) for the real `ads` module (apps/backend/src/ads/ -- banner campaign creation +
 * serving already exists there). Swap point: once the frontend has an ads client, replace the
 * placeholder body with the served creative; every call site already just renders `<AdSlot />`.
 */
export function AdSlot({ variant = "horizontal" }: { variant?: "horizontal" | "sidebar" }) {
  if (variant === "sidebar") {
    return (
      <div className="flex h-[420px] w-[160px] flex-col items-center justify-center gap-1.5 rounded-2xl border border-dashed border-border/70 bg-card/30 text-center text-muted-foreground/70 backdrop-blur">
        <span className="text-[10px] font-medium uppercase tracking-widest">Reklama</span>
      </div>
    );
  }

  return (
    <div className="px-6">
      <div className="mx-auto flex h-24 max-w-7xl items-center justify-center rounded-2xl border border-dashed border-border/70 bg-card/30 text-center text-muted-foreground/70 sm:h-28">
        <span className="text-xs font-medium uppercase tracking-widest">Reklama joyi</span>
      </div>
    </div>
  );
}
