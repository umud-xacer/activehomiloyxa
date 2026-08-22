import type { ReactNode } from "react";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Footer } from "@/components/site/Footer";
import { GlobalAdSidebars } from "@/components/site/GlobalAdSidebars";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* This wrapper is deliberately everything EXCEPT <Footer/> -- see GlobalAdSidebars'
       * own docstring for why that's what makes the sticky sidebars stop at the footer.
       * `2xl:grid-cols-[200px_minmax(0,1fr)_200px]` reserves real column space for the sidebar
       * ad slots instead of overlaying them -- see GlobalAdSidebars.tsx for why. */}
      <div className="relative grid grid-cols-1 2xl:grid-cols-[200px_minmax(0,1fr)_200px]">
        <Navbar />
        <GlobalAdSidebars />
        <main className="min-w-0 col-start-1 row-start-1 2xl:col-start-2">{children}</main>
      </div>
      <Footer />
    </div>
  );
}
