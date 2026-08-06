import { useTranslation } from "react-i18next";
import { Link } from "@tanstack/react-router";
import { Logo } from "./Logo";
import { SocialIconsExpanded } from "./SocialIcons";
import footerBg from "@/assets/bg-worldmap-logo.png.asset.json";

/** Every link points at a real route. `null` means no page exists yet for that label (Terms,
 * Cookies) -- left unlinked rather than wired to `#` or a fabricated legal page. */
const FOOTER_LINK_TO: Record<string, string | null> = {
  Buy: "/properties",
  Rent: "/properties",
  Hotels: "/hotels",
  Build: "/construction",
  Shop: "/materials",
  "AI Search": "/ai",
  About: "/about",
  Careers: "/jobs",
  Press: "/news",
  Partners: "/list",
  Contact: "/contact",
  Terms: null,
  Privacy: "/privacy",
  Cookies: null,
  Security: "/security",
};

export function Footer() {
  const { t } = useTranslation();
  const cols = [
    { title: t("footer.product"), links: ["Buy", "Rent", "Hotels", "Build", "Shop", "AI Search"] },
    { title: t("footer.company"), links: ["About", "Careers", "Press", "Partners", "Contact"] },
    { title: t("footer.legal"), links: ["Terms", "Privacy", "Cookies", "Security"] },
  ];
  return (
    <footer className="relative isolate overflow-hidden border-t border-border bg-surface/60">
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center opacity-10"
        style={{ backgroundImage: `url(${footerBg.url})` }}
        aria-hidden
      />
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-12 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div>
            <Logo className="h-9" />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">{t("footer.tagline")}</p>
            <SocialIconsExpanded className="mt-5" />
          </div>
          {cols.map((c) => (
            <div key={c.title}>
              <div className="text-xs font-semibold uppercase tracking-wider text-foreground">
                {c.title}
              </div>
              <ul className="mt-4 space-y-2.5">
                {c.links.map((l) => {
                  const to = FOOTER_LINK_TO[l];
                  return (
                    <li key={l}>
                      {to ? (
                        <Link
                          to={to}
                          className="text-sm text-muted-foreground transition hover:text-foreground"
                        >
                          {l}
                        </Link>
                      ) : (
                        <span className="text-sm text-muted-foreground/50">{l}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center">
          <div>
            © {new Date().getFullYear()} ActiveHome. {t("footer.rights")}
          </div>
        </div>
      </div>
    </footer>
  );
}
