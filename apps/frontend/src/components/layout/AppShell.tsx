import type { ReactNode } from "react";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Footer } from "@/components/site/Footer";
import { GlobalAdSidebars } from "@/components/site/GlobalAdSidebars";
import { useSkyscraperAdsEnabled } from "@/lib/use-skyscraper-ads-enabled";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: ReactNode }) {
  // The 200px side gutters (`2xl:grid-cols-[200px_minmax(0,1fr)_200px]`) are only reserved once
  // skyscraper ads are explicitly re-enabled (default OFF) -- otherwise the grid stays a plain
  // single column instead of leaving dead whitespace where the ad columns used to sit. See
  // `GlobalAdSidebars.tsx` for why real grid columns (not an overlay) are used at all.
  // `max-w-[1920px] mx-auto` caps the whole shell so that even when re-enabled, the ad columns
  // sit just past a real content edge rather than camping at the literal viewport edge on an
  // ultrawide monitor.
  const skyscraperAdsEnabled = useSkyscraperAdsEnabled();
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* This wrapper is deliberately everything EXCEPT <Footer/> -- see GlobalAdSidebars'
       * own docstring for why that's what makes the sticky sidebars stop at the footer. */}
      <div
        className={cn(
          "relative mx-auto max-w-[1920px] grid grid-cols-1",
          skyscraperAdsEnabled && "2xl:grid-cols-[200px_minmax(0,1fr)_200px]",
        )}
      >
        <Navbar />
        <GlobalAdSidebars />
        <main
          className={cn(
            "min-w-0 col-start-1 row-start-1",
            skyscraperAdsEnabled && "2xl:col-start-2",
          )}
        >
          {children}
        </main>
      </div>
      <Footer />
    </div>
  );
}
