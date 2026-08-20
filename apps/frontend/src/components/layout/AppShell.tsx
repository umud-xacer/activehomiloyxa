import type { ReactNode } from "react";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Footer } from "@/components/site/Footer";
import { GlobalAdSidebars } from "@/components/site/GlobalAdSidebars";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* This wrapper is deliberately everything EXCEPT <Footer/> -- see GlobalAdSidebars'
       * own docstring for why that's what makes the sticky sidebars stop at the footer. */}
      <div className="relative">
        <Navbar />
        <GlobalAdSidebars />
        <main>{children}</main>
      </div>
      <Footer />
    </div>
  );
}
