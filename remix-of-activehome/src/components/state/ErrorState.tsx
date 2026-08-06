import { AlertTriangle } from "lucide-react";
import { useRouter } from "@tanstack/react-router";

export function ErrorState({ error, reset }: { error: Error; reset?: () => void }) {
  const router = useRouter();
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center rounded-3xl border border-destructive/20 bg-destructive/5 px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-destructive/15 text-destructive">
        <AlertTriangle className="size-5" />
      </div>
      <h3 className="font-display mt-4 text-lg font-semibold text-foreground">
        Something didn't load
      </h3>
      <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>
      <button
        onClick={() => {
          router.invalidate();
          reset?.();
        }}
        className="mt-6 inline-flex items-center rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
      >
        Try again
      </button>
    </div>
  );
}
