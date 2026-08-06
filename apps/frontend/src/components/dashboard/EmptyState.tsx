import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
  compact?: boolean;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-background/40 text-center ${
        compact ? "px-6 py-8" : "px-6 py-16"
      }`}
    >
      <div className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </div>
      <div>
        <div className="font-display text-sm font-semibold text-foreground">{title}</div>
        {description && (
          <p className="mx-auto mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
