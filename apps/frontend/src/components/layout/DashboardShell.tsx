import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Heart,
  Bookmark,
  Wallet,
  CreditCard,
  Bell,
  Shield,
  Sparkles,
  Settings,
  MessageSquare,
  Building2,
  TrendingUp,
  Search,
  ChevronsLeft,
  ChevronsRight,
  LogOut,
  UserRound,
  Plus,
  Home,
} from "lucide-react";
import { Logo } from "@/components/site/Logo";
import { LanguageSwitcher } from "@/components/site/LanguageSwitcher";
import { ThemeToggle } from "@/components/site/ThemeToggle";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  CommandPalette,
  useCommandPaletteHint,
  type CommandAction,
} from "@/components/dashboard/CommandPalette";
import { authApi, type Account, type AccountKind } from "@/lib/auth-client";
import { useInvalidateAuth } from "@/features/auth/useAuth";
import "@/lib/i18n";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}
interface NavGroup {
  label: string;
  items: NavItem[];
}

/** ADR-0007: each account role gets its own nav, grouped by intent rather than one shared flat
 * menu -- a legal-entity workspace is about listings/verification, an investor's is about
 * opportunities/wallet. */
const NAV_BY_ROLE: Record<AccountKind, NavGroup[]> = {
  INDIVIDUAL: [
    {
      label: "Asosiy",
      items: [
        { to: "/dashboard", label: "Umumiy ko'rinish", icon: LayoutDashboard },
        { to: "/favorites", label: "Saqlanganlar", icon: Heart },
        { to: "/saved", label: "Saqlangan qidiruvlar", icon: Bookmark },
        { to: "/messages", label: "Xabarlar", icon: MessageSquare },
      ],
    },
    {
      label: "Hisob",
      items: [
        { to: "/verification", label: "Tasdiqlash", icon: Shield },
        { to: "/notifications", label: "Bildirishnomalar", icon: Bell },
        { to: "/settings", label: "Sozlamalar", icon: Settings },
      ],
    },
  ],
  LEGAL_ENTITY: [
    {
      label: "Biznes",
      items: [
        { to: "/dashboard/seller", label: "Umumiy ko'rinish", icon: LayoutDashboard },
        { to: "/properties", label: "Mening e'lonlarim", icon: Building2 },
        { to: "/verification", label: "Tasdiqlash", icon: Shield },
      ],
    },
    {
      label: "Aloqa",
      items: [
        { to: "/messages", label: "Xabarlar", icon: MessageSquare },
        { to: "/subscriptions", label: "Obunalar", icon: CreditCard },
      ],
    },
    {
      label: "Hisob",
      items: [
        { to: "/notifications", label: "Bildirishnomalar", icon: Bell },
        { to: "/settings", label: "Sozlamalar", icon: Settings },
      ],
    },
  ],
  INVESTOR: [
    {
      label: "Portfel",
      items: [
        { to: "/dashboard/investor", label: "Imkoniyatlar", icon: TrendingUp },
        { to: "/wallet", label: "Hamyon", icon: Wallet },
      ],
    },
    {
      label: "Hisob",
      items: [
        { to: "/messages", label: "Xabarlar", icon: MessageSquare },
        { to: "/notifications", label: "Bildirishnomalar", icon: Bell },
        { to: "/settings", label: "Sozlamalar", icon: Settings },
      ],
    },
  ],
};

const ROLE_LABEL: Record<AccountKind, string> = {
  INDIVIDUAL: "Jismoniy shaxs",
  LEGAL_ENTITY: "Yuridik shaxs",
  INVESTOR: "Investor",
};

const ROLE_CREATE_CTA: Record<AccountKind, { label: string; to: string }> = {
  INDIVIDUAL: { label: "E'lon joylash", to: "/list" },
  LEGAL_ENTITY: { label: "E'lon qo'shish", to: "/list" },
  INVESTOR: { label: "Imkoniyat ko'rish", to: "/dashboard/investor" },
};

const SIDEBAR_COLLAPSE_KEY = "ah:sidebar-collapsed";

export function DashboardShell({
  children,
  account,
}: {
  children: ReactNode;
  /** ADR-0007: picks the nav set, workspace label and CTA. Falls back to the individual nav +
   * "Demo user" when omitted (rare -- callers should always resolve `useMe()` first). */
  account?: Account | null;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const invalidateAuth = useInvalidateAuth();
  const cmdHint = useCommandPaletteHint();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1");
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((v) => {
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, v ? "0" : "1");
      return !v;
    });
  };

  const accountKind = account?.accountKind ?? "INDIVIDUAL";
  const isReviewer = (account?.roles ?? []).some(
    (r) => r === "super-admin" || r === "administrator",
  );
  const groups: NavGroup[] = isReviewer
    ? [
        ...NAV_BY_ROLE[accountKind],
        { label: "Admin", items: [{ to: "/admin", label: "Admin panel", icon: Shield }] },
      ]
    : NAV_BY_ROLE[accountKind];
  const initials = (account?.displayName || account?.email || "AH")
    .trim()
    .slice(0, 2)
    .toUpperCase();
  const createCta = ROLE_CREATE_CTA[accountKind];

  const paletteActions: CommandAction[] = [
    ...groups.flatMap((g) => g.items.map((item) => ({ ...item, group: g.label }))),
    { label: "Bosh sahifaga o'tish", to: "/", icon: Home, group: "Umumiy" },
  ];

  const onLogout = async () => {
    await authApi.logout();
    invalidateAuth();
    navigate({ to: "/auth/sign-in" });
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div className="relative min-h-screen bg-background text-foreground">
        <CommandPalette actions={paletteActions} />

        {/* Top bar */}
        <header className="fixed inset-x-0 top-0 z-40 border-b border-border bg-background/85 backdrop-blur-xl">
          <div className="flex h-16 items-center justify-between gap-3 px-4 lg:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                onClick={() => setMobileOpen(true)}
                className="flex size-8 items-center justify-center rounded-lg text-foreground/70 hover:bg-muted lg:hidden"
                aria-label="Menyu"
              >
                <LayoutDashboard className="size-4" />
              </button>
              <Link to="/" className="flex shrink-0 items-center gap-2">
                <Logo className="h-6" />
              </Link>
              <Badge
                variant="secondary"
                className="hidden shrink-0 rounded-full font-medium sm:inline-flex"
              >
                {ROLE_LABEL[accountKind]}
              </Badge>
            </div>

            <button
              onClick={() =>
                document.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))
              }
              className="group hidden max-w-sm flex-1 items-center gap-2 rounded-full border border-border bg-card px-3.5 py-1.5 text-sm text-muted-foreground shadow-soft transition hover:border-primary/30 hover:text-foreground md:flex"
            >
              <Search className="size-3.5" />
              <span className="flex-1 text-left">Qidirish yoki buyruq...</span>
              <kbd className="rounded-md border border-border bg-muted px-1.5 py-0.5 text-[10px] font-semibold">
                {cmdHint}
              </kbd>
            </button>

            <div className="flex shrink-0 items-center gap-1.5">
              <Link
                to={createCta.to}
                className="hidden items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:inline-flex"
              >
                <Plus className="size-3.5" /> {createCta.label}
              </Link>
              <LanguageSwitcher />
              <ThemeToggle />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="relative flex size-8 items-center justify-center rounded-full text-foreground/70 transition hover:bg-muted">
                    <Bell className="size-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-72">
                  <DropdownMenuLabel>Bildirishnomalar</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <div className="px-2 py-6 text-center text-xs text-muted-foreground">
                    Hozircha yangi bildirishnoma yo'q.
                  </div>
                </DropdownMenuContent>
              </DropdownMenu>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="ml-1 flex items-center gap-2 rounded-full border border-border bg-card py-1 pl-1 pr-2.5 shadow-soft transition hover:border-primary/30">
                    <Avatar className="size-6">
                      <AvatarFallback className="bg-primary text-[10px] font-semibold text-primary-foreground">
                        {initials}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden max-w-[9rem] truncate text-xs font-medium text-foreground sm:inline">
                      {account?.displayName || account?.email || "Demo user"}
                    </span>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="flex items-center gap-2">
                    <UserRound className="size-3.5" /> {account?.displayName || "Foydalanuvchi"}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link to="/settings">
                      <Settings className="mr-2 size-4" /> Sozlamalar
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link to="/subscriptions">
                      <Sparkles className="mr-2 size-4" /> Obuna rejasi
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={onLogout}
                    className="text-destructive focus:text-destructive"
                  >
                    <LogOut className="mr-2 size-4" /> Chiqish
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <div className="flex pt-16">
          {/* Sidebar (desktop) */}
          <aside
            className={`fixed bottom-0 left-0 top-16 z-30 hidden flex-col border-r border-border bg-card/40 transition-[width] duration-200 lg:flex ${
              collapsed ? "w-[4.5rem]" : "w-64"
            }`}
          >
            <nav className="flex-1 space-y-5 overflow-y-auto p-3">
              {groups.map((group) => (
                <div key={group.label}>
                  {!collapsed && (
                    <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                      {group.label}
                    </div>
                  )}
                  <div className="space-y-0.5">
                    {group.items.map(({ to, label, icon: Icon }) => {
                      const active =
                        pathname === to ||
                        (to !== "/dashboard" &&
                          to !== "/dashboard/seller" &&
                          to !== "/dashboard/investor" &&
                          pathname.startsWith(to));
                      return (
                        <Link
                          key={to}
                          to={to}
                          title={collapsed ? label : undefined}
                          className={`group relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-all ${
                            active
                              ? "bg-primary/10 text-primary"
                              : "text-foreground/70 hover:bg-muted hover:text-foreground"
                          } ${collapsed ? "justify-center" : ""}`}
                        >
                          {active && (
                            <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-primary" />
                          )}
                          <Icon className="size-4 shrink-0" />
                          {!collapsed && <span className="truncate">{label}</span>}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>

            {!collapsed && (
              <div className="m-3 rounded-2xl border border-border bg-card p-4 shadow-soft">
                <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                  <Sparkles className="size-3.5 text-primary" /> Pro'ga yangilang
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                  AI baholash, cheksiz saqlangan qidiruvlar va ustuvor qo'llab-quvvatlash.
                </p>
                <Link
                  to="/subscriptions"
                  className="mt-3 inline-flex w-full items-center justify-center rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:shadow-glow"
                >
                  Rejalarni ko'rish
                </Link>
              </div>
            )}

            <button
              onClick={toggleCollapsed}
              className="m-3 mt-0 flex items-center justify-center gap-2 rounded-xl border border-border/70 py-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
            >
              {collapsed ? (
                <ChevronsRight className="size-3.5" />
              ) : (
                <ChevronsLeft className="size-3.5" />
              )}
              {!collapsed && "Yig'ish"}
            </button>
          </aside>

          {/* Sidebar (mobile overlay) */}
          {mobileOpen && (
            <div className="fixed inset-0 z-40 lg:hidden">
              <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
              <aside className="absolute bottom-0 left-0 top-16 w-72 overflow-y-auto border-r border-border bg-card p-3 shadow-elevated">
                {groups.map((group) => (
                  <div key={group.label} className="mb-5">
                    <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                      {group.label}
                    </div>
                    <div className="space-y-0.5">
                      {group.items.map(({ to, label, icon: Icon }) => (
                        <Link
                          key={to}
                          to={to}
                          onClick={() => setMobileOpen(false)}
                          className={`flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
                            pathname === to
                              ? "bg-primary/10 text-primary"
                              : "text-foreground/70 hover:bg-muted"
                          }`}
                        >
                          <Icon className="size-4" />
                          {label}
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
              </aside>
            </div>
          )}

          <main
            className={`min-w-0 flex-1 transition-[padding] duration-200 ${collapsed ? "lg:pl-[4.5rem]" : "lg:pl-64"}`}
          >
            {children}
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
