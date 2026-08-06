import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { Logo } from "./Logo";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { ThemeToggle } from "./ThemeToggle";
import { ArrowUpRight } from "lucide-react";

const LINKS = [
  { key: "buy", to: "/properties", search: { listing: "sale" as const } },
  { key: "rent", to: "/properties", search: { listing: "rent" as const } },
  { key: "map", to: "/map" },
  { key: "stays", to: "/hotels" },
  { key: "build", to: "/construction" },
  { key: "shop", to: "/furniture" },
] as const;

export function Navbar() {
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="fixed inset-x-0 top-0 z-50 px-4 pt-4"
    >
      <div
        className={`mx-auto flex max-w-7xl items-center justify-between rounded-full border px-3 py-2 transition-all duration-300 ${
          scrolled
            ? "glass border-glass-border shadow-soft"
            : "border-transparent bg-transparent"
        }`}
      >
        <Link to="/" className="flex items-center gap-2 pl-1">
          <Logo className="h-8" />
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <Link
              key={l.key}
              to={l.to}
              className="relative rounded-full px-3.5 py-1.5 text-sm font-medium text-foreground/75 transition hover:text-foreground"
              activeProps={{ className: "text-foreground" }}
            >
              {t(`nav.${l.key}`)}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
          <Link
            to="/auth/sign-in"
            className="hidden rounded-full px-3 py-1.5 text-sm font-medium text-foreground/75 transition hover:text-foreground sm:inline-flex"
          >
            {t("nav.signin")}
          </Link>
          <Link
            to="/list"
            className="group inline-flex items-center gap-1 rounded-full bg-primary px-3.5 py-1.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            {t("nav.list")}
            <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>
      </div>
    </motion.header>
  );
}

