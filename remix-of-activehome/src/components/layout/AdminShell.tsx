import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { LayoutDashboard, Settings2, Receipt, ShieldCheck, Flag, Megaphone, FolderTree, Building2, Users, ScrollText, ClipboardList, SlidersHorizontal, BarChart3, ToggleLeft } from "lucide-react";
import { Logo } from "@/components/site/Logo";
import "@/lib/i18n";

const NAV = [
  { to: "/admin", label: "Overview", icon: LayoutDashboard },
  { to: "/admin/analytics", label: "Analitika", icon: BarChart3 },
  { to: "/admin/users", label: "Foydalanuvchilar", icon: Users },
  { to: "/admin/categories", label: "Kategoriyalar", icon: FolderTree },
  { to: "/admin/forms", label: "Formalar", icon: ClipboardList },
  { to: "/admin/search-config", label: "Qidiruv sozlamalari", icon: SlidersHorizontal },
  { to: "/admin/listings", label: "E'lonlar", icon: Building2 },
  { to: "/admin/config", label: "Konfiguratsiya", icon: Settings2 },
  { to: "/admin/feature-flags", label: "Imkoniyatlar", icon: ToggleLeft },
  { to: "/admin/verification", label: "Tasdiqlash navbati", icon: ShieldCheck },
  { to: "/admin/moderation", label: "Moderatsiya", icon: Flag },
  { to: "/admin/billing", label: "Invoyslar", icon: Receipt },
  { to: "/admin/ads", label: "Reklama kampaniyalari", icon: Megaphone },
  { to: "/admin/audit-log", label: "Audit log", icon: ScrollText },
] as const;

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      <header className="fixed inset-x-0 top-0 z-40 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="flex h-16 items-center justify-between px-4 lg:px-6">
          <Link to="/" className="flex items-center gap-2">
            <Logo className="h-7" />
            <span className="hidden text-xs font-semibold uppercase tracking-widest text-destructive sm:inline">
              Admin
            </span>
          </Link>
          <Link to="/dashboard" className="text-xs font-medium text-muted-foreground hover:text-foreground">
            Foydalanuvchi paneliga qaytish
          </Link>
        </div>
      </header>

      <div className="flex pt-16">
        <aside className="fixed bottom-0 left-0 top-16 hidden w-64 overflow-y-auto border-r border-border bg-card/40 lg:block">
          <nav className="space-y-1 p-4">
            {NAV.map(({ to, label, icon: Icon }) => {
              const active = pathname === to || (to !== "/admin" && pathname.startsWith(to));
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
        </aside>

        <main className="min-w-0 flex-1 p-6 lg:pl-64 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
