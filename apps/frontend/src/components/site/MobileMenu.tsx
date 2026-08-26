import { Link } from "@tanstack/react-router";
import {
  Menu,
  Plus,
  Home,
  Building2,
  LayoutGrid,
  Landmark,
  TrendingUp,
  MapPin,
  Bot,
  LayoutDashboard,
  Heart,
  Settings,
  UserRound,
  LogOut,
} from "lucide-react";
import { useState } from "react";
import { Sheet, SheetClose, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Logo } from "./Logo";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import type { useMe } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";

type Account = NonNullable<ReturnType<typeof useMe>["data"]>;

interface Props {
  account: Account | null | undefined;
  onLogout: () => void;
}

const PRIMARY_LINKS = [
  { to: "/", label: "Bosh sahifa", icon: Home },
  { to: "/properties", label: "Ko'chmas mulk", icon: Building2 },
  { to: "/categories", label: "Barcha kategoriyalar", icon: LayoutGrid },
  { to: "/organizations", label: "Tashkilotlar", icon: Landmark },
  { to: "/invest", label: "Investorlar", icon: TrendingUp },
  { to: "/map", label: "Xarita", icon: MapPin },
] as const;

/**
 * Mobile + tablet portrait (< lg, i.e. < 1024px) site navigation drawer. The main Navbar is
 * deliberately account/profile-focused (Amazon/OLX pattern, see Navbar.tsx) and has no general
 * "browse the site" affordance at all -- fine on desktop where CategoryCarousel/EcosystemGrid on
 * the homepage cover discovery, but a real gap below 1024px once a visitor has scrolled past the
 * homepage or landed on any other page. This adds exactly that, plus relocates Language/Theme
 * switching here below `lg` to keep the floating pill navbar from overflowing on small screens.
 */
export function MobileMenu({ account, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  // Same ADR-0007 rule Navbar.tsx applies to its own standalone "E'lon joylash" pill -- a
  // LEGAL_ENTITY account edits its company profile instead of posting individual listings, so it
  // gets no post-ad entry point here either (it already has one in the profile dropdown).
  const isLegalEntity = account?.accountKind === "LEGAL_ENTITY";

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <button
        type="button"
        aria-label="Menyu"
        onClick={() => setOpen(true)}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-1.5 text-sm font-medium text-foreground/75 transition hover:bg-secondary hover:text-foreground active:scale-[0.97] sm:px-2.5 lg:hidden"
      >
        <Menu className="size-4.5" />
        <span className="hidden text-xs font-semibold sm:inline">Menyu</span>
      </button>
      <SheetContent side="left" className="flex w-[85vw] max-w-xs flex-col gap-0 p-0">
        <SheetHeader className="shrink-0 border-b border-border px-5 py-4 text-left">
          <SheetTitle asChild>
            <Logo className="h-7 w-auto" />
          </SheetTitle>
        </SheetHeader>

        <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {/* The standalone "E'lon joylash" pill in `Navbar.tsx` hides below `sm:` to keep the
              floating header from overflowing on narrow phones -- this is its replacement entry
              point there, kept as a real primary-styled CTA (not just another list row) since
              posting stays the single highest-value action on the site. */}
          {!isLegalEntity && (
            <SheetClose asChild>
              <Link
                to="/list"
                className="mb-2 flex items-center justify-center gap-2 rounded-xl bg-primary px-3 py-3 text-[15px] font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:hidden"
              >
                <Plus className="size-5 shrink-0" />
                E'lon joylash
              </Link>
            </SheetClose>
          )}
          <ul className="flex flex-col gap-1">
            {PRIMARY_LINKS.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <SheetClose asChild>
                  <Link
                    to={to}
                    className="flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium text-foreground transition hover:bg-secondary [&.active]:bg-primary/10 [&.active]:text-primary"
                  >
                    <Icon className="size-5 shrink-0 text-muted-foreground" />
                    {label}
                  </Link>
                </SheetClose>
              </li>
            ))}
            <li>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  window.dispatchEvent(new Event("activehome:open-chat"));
                }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] font-medium text-foreground transition hover:bg-secondary"
              >
                <Bot className="size-5 shrink-0 text-muted-foreground" />
                AI Yordamchi
              </button>
            </li>
          </ul>

          <div className="my-3 h-px bg-border" />

          <ul className="flex flex-col gap-1">
            {account ? (
              <>
                <li>
                  <SheetClose asChild>
                    <Link
                      to={dashboardPathForAccount(account)}
                      className="flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium text-foreground transition hover:bg-secondary"
                    >
                      <LayoutDashboard className="size-5 shrink-0 text-muted-foreground" />
                      Boshqaruv paneli
                    </Link>
                  </SheetClose>
                </li>
                <li>
                  <SheetClose asChild>
                    <Link
                      to="/favorites"
                      className="flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium text-foreground transition hover:bg-secondary"
                    >
                      <Heart className="size-5 shrink-0 text-muted-foreground" />
                      Saqlanganlar
                    </Link>
                  </SheetClose>
                </li>
                <li>
                  <SheetClose asChild>
                    <Link
                      to="/settings"
                      className="flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium text-foreground transition hover:bg-secondary"
                    >
                      <Settings className="size-5 shrink-0 text-muted-foreground" />
                      Sozlamalar
                    </Link>
                  </SheetClose>
                </li>
                <li>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      onLogout();
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[15px] font-medium text-destructive transition hover:bg-destructive/10"
                  >
                    <LogOut className="size-5 shrink-0" />
                    Chiqish
                  </button>
                </li>
              </>
            ) : (
              <li>
                <SheetClose asChild>
                  <Link
                    to="/auth/sign-in"
                    className="flex items-center gap-3 rounded-xl px-3 py-3 text-[15px] font-medium text-foreground transition hover:bg-secondary"
                  >
                    <UserRound className="size-5 shrink-0 text-muted-foreground" />
                    Kirish
                  </Link>
                </SheetClose>
              </li>
            )}
          </ul>
        </nav>

        <div className="flex shrink-0 items-center gap-2 border-t border-border px-5 py-3.5">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </SheetContent>
    </Sheet>
  );
}
