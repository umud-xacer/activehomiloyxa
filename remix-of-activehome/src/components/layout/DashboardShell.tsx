import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Heart,
  Wallet,
  CreditCard,
  Bell,
  Shield,
  Sparkles,
  Trophy,
  Settings,
  MessageSquare,
  Building2,
} from "lucide-react";
import { Logo } from "@/components/site/Logo";
import { LanguageSwitcher } from "@/components/site/LanguageSwitcher";
import { ThemeToggle } from "@/components/site/ThemeToggle";
import "@/lib/i18n";

const NAV = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { to: "/favorites", label: "Favorites", icon: Heart },
  { to: "/properties", label: "My listings", icon: Building2 },
  { to: "/messages", label: "Messages", icon: MessageSquare },
  { to: "/wallet", label: "Wallet", icon: Wallet },
  { to: "/subscriptions", label: "Subscriptions", icon: CreditCard },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/verification", label: "Verification", icon: Shield },
  { to: "/dashboard/seller", label: "Achievements", icon: Trophy },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      {/* Top bar */}
      <header className="fixed inset-x-0 top-0 z-40 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="flex h-16 items-center justify-between px-4 lg:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Logo className="h-7" />
            <span className="hidden text-xs font-medium uppercase tracking-widest text-muted-foreground sm:inline">
              Workspace
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <ThemeToggle />
            <div className="ml-2 flex items-center gap-2 rounded-full border border-border bg-card px-2 py-1 pr-3">
              <span className="grid size-7 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                AH
              </span>
              <span className="hidden text-xs font-medium text-foreground sm:inline">
                Demo user
              </span>
            </div>
          </div>
        </div>
      </header>

      <div className="flex pt-16">
        {/* Sidebar */}
        <aside className="fixed bottom-0 left-0 top-16 hidden w-64 overflow-y-auto border-r border-border bg-card/40 lg:block">
          <nav className="space-y-1 p-4">
            {NAV.map(({ to, label, icon: Icon }) => {
              const active = pathname === to || (to !== "/dashboard" && pathname.startsWith(to));
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "bg-primary text-primary-foreground shadow-soft"
                      : "text-foreground/75 hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <Icon className="size-4" />
                  {label}
                </Link>
              );
            })}
          </nav>

          <div className="m-4 rounded-2xl border border-border bg-card p-4 shadow-soft">
            <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <Sparkles className="size-3.5 text-primary" /> Upgrade to Pro
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Unlock more active listings, featured placement and priority support.
            </p>
            <Link
              to="/subscriptions"
              className="mt-3 inline-flex w-full items-center justify-center rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:shadow-glow"
            >
              See plans
            </Link>
          </div>
        </aside>

        <main className="min-w-0 flex-1 lg:pl-64">{children}</main>
      </div>
    </div>
  );
}
