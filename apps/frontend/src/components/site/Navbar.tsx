import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link, useNavigate } from "@tanstack/react-router";
import { SearchResultsPanel } from "@/components/search/SearchResultsPanel";
import {
  Plus,
  Search,
  X,
  UserRound,
  LayoutDashboard,
  Heart,
  Settings,
  Building2,
  LogOut,
} from "lucide-react";
import { Logo } from "./Logo";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { SocialIconsRow } from "./SocialIcons";
import { ChatAssistant } from "./ChatAssistant";
import { MobileMenu } from "./MobileMenu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useMe, useInvalidateAuth } from "@/features/auth/useAuth";
import { authApi } from "@/lib/auth-client";
import { dashboardPathForAccount } from "@/lib/require-auth";

/* Amazon/OLX-style clean chrome: brand on the left, everything account-related collapses into a
 * single profile menu on the right instead of a row of loose links -- the previous layout put a
 * bare "dashboard" text link next to "sign in" with no real menu at all, which read as unfinished
 * next to any large marketplace's navbar. The one exception is "E'lon joylash" (post an ad),
 * which stays a standalone pill CTA for individual/investor accounts -- posting is the single
 * highest-value action on the whole site and deserves to stay one click away, not buried a menu
 * level deep, the same reasoning Amazon/OLX apply to "sell"/"e'lon joylash" buttons of their own.
 *
 * Always a soft frosted-glass strip, never fully invisible -- Navbar floats over whatever a page
 * puts at its very top (the homepage's dark Hero, or a plain light page background elsewhere via
 * AppShell), so every element here needs guaranteed contrast regardless of what's behind it. A
 * transparent-at-rest bar can't offer that; a permanent (if subtle) glass backdrop can, and reads
 * as the Apple/Airbnb "translucent bar" look rather than a bar that pops in only once scrolled. */

const EASE = [0.22, 1, 0.36, 1] as const;

export function Navbar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const { data: account } = useMe();
  const invalidateAuth = useInvalidateAuth();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const onLogout = async () => {
    await authApi.logout();
    invalidateAuth();
    navigate({ to: "/auth/sign-in" });
  };

  // ADR-0007: a LEGAL_ENTITY account advertises its own company rather than listing individual
  // items for sale, so the marketing-site navbar's headline action for them is editing that
  // company profile, not posting an ad -- the standalone "E'lon joylash" pill is reserved for
  // INDIVIDUAL/INVESTOR accounts (and signed-out visitors, who get routed through sign-in first).
  const isLegalEntity = account?.accountKind === "LEGAL_ENTITY";
  const initials = (account?.displayName || account?.email || "AH")
    .trim()
    .slice(0, 2)
    .toUpperCase();

  return (
    // Fragment, not a single root -- `ChatAssistant` renders its own `position: fixed` bubble
    // and panel, which MUST live outside `motion.header`: any CSS `transform` on an ancestor
    // (framer-motion keeps one applied on `motion.header` even at rest) creates a new containing
    // block for `fixed` descendants, so the widget would position itself relative to the ~70px
    // header bar instead of the real viewport -- confirmed live (the bubble rendered at
    // `top: -30px`, off-screen, instead of anywhere near the bottom-right corner it's styled for).
    <>
      <motion.header
        initial={{ y: -24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.7, ease: EASE }}
        className={`fixed inset-x-0 top-0 z-50 px-4 transition-[padding] duration-[400ms] ease-[cubic-bezier(0.22,1,0.36,1)] ${
          scrolled ? "pt-2.5" : "pt-4"
        }`}
      >
        <div
          className={`glass mx-auto flex max-w-7xl items-center justify-between rounded-full transition-all duration-[400ms] ease-[cubic-bezier(0.22,1,0.36,1)] ${
            scrolled ? "gap-1 px-3.5 py-2 shadow-elevated" : "gap-1.5 px-4 py-2.5 shadow-soft"
          }`}
        >
          <div className="flex shrink-0 items-center gap-0.5">
            <MobileMenu account={account} onLogout={onLogout} />
            <Link
              to="/"
              className="flex shrink-0 items-center gap-2 pl-1 transition-transform duration-300 hover:scale-[1.03] active:scale-[0.98]"
            >
              <Logo
                className={`w-auto transition-all duration-[400ms] ${scrolled ? "h-7" : "h-8"}`}
              />
            </Link>
          </div>

          <div className="flex items-center gap-1">
            <SocialIconsRow className="hidden xl:flex" />
            <Divider className="hidden xl:block" />

            {/* `lg:` (not `md:`) on purpose -- tablet (768-1023px) has the same "no room for a
              full chrome row" constraint as mobile and gets the same MobileMenu drawer for
              secondary functions; only small-laptop-and-up (1024px+) shows the full row inline. */}
            <div className="hidden items-center gap-1.5 lg:flex">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>

            <Divider className="hidden lg:block" />

            <motion.div layout className="relative flex shrink-0 items-center">
              {searchOpen ? (
                <motion.div
                  initial={{ width: 36, opacity: 0 }}
                  animate={{ width: "auto", opacity: 1 }}
                  transition={{ duration: 0.25, ease: EASE }}
                  className="flex items-center gap-1.5 overflow-hidden rounded-full bg-secondary/70 py-1.5 pl-3 pr-1.5"
                >
                  <Search className="size-4 shrink-0 text-foreground/60" />
                  <input
                    autoFocus
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setSearchOpen(false);
                      if (e.key === "Enter" && searchQuery.trim()) {
                        setSearchOpen(false);
                        navigate({ to: "/search", search: { q: searchQuery.trim() } });
                      }
                    }}
                    placeholder={t("nav.search", "Qidiruv")}
                    className="w-36 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/70 sm:w-56"
                  />
                  <button
                    type="button"
                    onClick={() => setSearchOpen(false)}
                    aria-label="Yopish"
                    className="flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition hover:bg-background hover:text-foreground"
                  >
                    <X className="size-3.5" />
                  </button>
                </motion.div>
              ) : (
                <button
                  type="button"
                  onClick={() => setSearchOpen(true)}
                  aria-label={t("nav.search", "Qidiruv")}
                  className="flex size-9 shrink-0 items-center justify-center rounded-full text-foreground/75 transition hover:bg-secondary hover:text-foreground"
                >
                  <Search className="size-4.5" />
                </button>
              )}
              {/* Controlled mode -- the inline input above IS the search box; this renders
                  results only, attached directly under it (no second embedded input, and no
                  detached-looking floating card the way a modal's own input used to). */}
              <SearchResultsPanel
                open={searchOpen}
                onOpenChange={setSearchOpen}
                externalQuery={searchQuery}
                onExternalQueryChange={setSearchQuery}
                className="absolute right-0 top-full z-50 mt-2 w-[calc(100vw-2rem)] max-w-md overflow-hidden rounded-2xl border border-slate-100 bg-card shadow-xl sm:w-[420px]"
              />
            </motion.div>

            {!isLegalEntity && (
              <Link
                to="/list"
                className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:px-3.5"
              >
                <Plus className="size-3.5" />
                <span className="hidden sm:inline">{t("nav.postAd", "E'lon joylash")}</span>
              </Link>
            )}

            {account ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    aria-label={t("nav.account", "Mening hisobim")}
                    className="ml-0.5 flex items-center justify-center rounded-full transition hover:scale-[1.05] active:scale-[0.97]"
                  >
                    <Avatar className="size-9 ring-2 ring-transparent transition hover:ring-primary/40">
                      <AvatarFallback className="bg-primary text-xs font-semibold text-primary-foreground">
                        {initials}
                      </AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuLabel className="flex items-center gap-2">
                    <UserRound className="size-3.5" />
                    <span className="truncate">{account.displayName || account.email}</span>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {isLegalEntity ? (
                    <>
                      <DropdownMenuItem asChild>
                        <Link to="/dashboard/business-profile">
                          <Building2 className="mr-2 size-4" />
                          Kompaniya ma'lumotlarini tahrirlash
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to={dashboardPathForAccount(account)}>
                          <LayoutDashboard className="mr-2 size-4" />
                          Boshqaruv paneli
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to="/list">
                          <Plus className="mr-2 size-4" />
                          E'lon joylash
                        </Link>
                      </DropdownMenuItem>
                    </>
                  ) : (
                    <>
                      <DropdownMenuItem asChild>
                        <Link to={dashboardPathForAccount(account)}>
                          <LayoutDashboard className="mr-2 size-4" />
                          Boshqaruv paneli
                        </Link>
                      </DropdownMenuItem>
                      <DropdownMenuItem asChild>
                        <Link to="/favorites">
                          <Heart className="mr-2 size-4" />
                          Saqlanganlar
                        </Link>
                      </DropdownMenuItem>
                    </>
                  )}
                  <DropdownMenuItem asChild>
                    <Link to="/settings">
                      <Settings className="mr-2 size-4" />
                      Sozlamalar
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={onLogout}
                    className="text-destructive focus:text-destructive"
                  >
                    <LogOut className="mr-2 size-4" />
                    Chiqish
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link
                to="/auth/sign-in"
                aria-label={t("nav.signin")}
                className="group relative inline-flex items-center rounded-full px-2.5 py-1.5 text-sm font-medium text-foreground/75 transition-colors duration-200 hover:text-foreground sm:px-3.5"
              >
                <UserRound className="size-4 sm:hidden" />
                <span className="hidden sm:inline">{t("nav.signin")}</span>
                <span className="pointer-events-none absolute inset-x-3.5 bottom-1.5 hidden h-px origin-center scale-x-0 bg-foreground/40 transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-x-100 sm:block" />
              </Link>
            )}
          </div>
        </div>
      </motion.header>

      <ChatAssistant />
    </>
  );
}

function Divider({ className = "" }: { className?: string }) {
  return (
    <span
      className={`mx-1.5 h-5 w-px shrink-0 bg-gradient-to-b from-transparent via-border to-transparent ${className}`}
      aria-hidden
    />
  );
}
