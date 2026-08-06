import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { Plus, UserRound } from "lucide-react";
import { Logo } from "./Logo";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { SocialIconsRow } from "./SocialIcons";
import { ChatAssistant } from "./ChatAssistant";
import { useMe } from "@/features/auth/useAuth";
import { dashboardPathForAccount } from "@/lib/require-auth";

/* No category-style or section links here by design -- Categories, Organizations and Investors
 * are all one scroll (or one tap) away on the home page itself. The navbar's only job is global
 * chrome: brand, channel presence, locale/theme, and the two account actions.
 *
 * Always a soft frosted-glass strip, never fully invisible -- Navbar floats over whatever a page
 * puts at its very top (the homepage's dark Hero, or a plain light page background elsewhere via
 * AppShell), so every element here needs guaranteed contrast regardless of what's behind it. A
 * transparent-at-rest bar can't offer that; a permanent (if subtle) glass backdrop can, and reads
 * as the Apple/Airbnb "translucent bar" look rather than a bar that pops in only once scrolled. */

const EASE = [0.22, 1, 0.36, 1] as const;

export function Navbar() {
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);
  const { data: account } = useMe();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
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
        <Link
          to="/"
          className="flex shrink-0 items-center gap-2 pl-1 transition-transform duration-300 hover:scale-[1.03] active:scale-[0.98]"
        >
          <Logo className={`w-auto transition-all duration-[400ms] ${scrolled ? "h-7" : "h-8"}`} />
        </Link>

        <div className="flex items-center gap-1">
          <SocialIconsRow className="hidden xl:flex" />
          <Divider className="hidden xl:block" />

          <div className="flex items-center gap-1.5">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>

          <Divider className="hidden sm:block" />

          <Link
            to="/list"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow sm:px-3.5"
          >
            <Plus className="size-3.5" />
            <span className="hidden sm:inline">{t("nav.postAd", "E'lon joylash")}</span>
          </Link>

          {account ? (
            <Link
              to={dashboardPathForAccount(account)}
              aria-label={t("nav.dashboard", "Boshqaruv paneli")}
              className="inline-flex items-center gap-2 rounded-full py-1 pl-1 pr-1 text-sm font-medium text-foreground/75 transition-colors duration-200 hover:text-foreground sm:pr-3.5"
            >
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                {(account.displayName || account.email || "AH").trim().slice(0, 2).toUpperCase()}
              </span>
              <span className="hidden sm:inline">{t("nav.dashboard", "Boshqaruv paneli")}</span>
            </Link>
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
          <ChatAssistant />
        </div>
      </div>
    </motion.header>
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
