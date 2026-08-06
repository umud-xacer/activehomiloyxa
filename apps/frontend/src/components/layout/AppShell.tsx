import type { ReactNode } from "react";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Footer } from "@/components/site/Footer";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen bg-background text-foreground">
      <Navbar />
      <main>{children}</main>
      <Footer />
    </div>
  );
}
