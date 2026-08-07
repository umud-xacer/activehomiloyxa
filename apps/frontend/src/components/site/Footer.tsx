import { useTranslation } from "react-i18next";
import { Link } from "@tanstack/react-router";
import { QRCodeSVG } from "qrcode.react";
import { QrCode } from "lucide-react";
import { Logo } from "./Logo";
import { SocialIconsExpanded } from "./SocialIcons";
import footerBg from "@/assets/bg-worldmap-logo.png.asset.json";
import logoMark from "@/assets/logo-mark.png";

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
};

/** Public site URL the footer QR code points visitors to on their phone. */
const SITE_URL = "https://activehome.uz";

/** Legal/info links, split into two short, clearly-labeled groups (mirrors how every real
 * marketplace footer organizes this -- one glance answers "where are the rules" vs "where are
 * the policies"). Every entry links to a real route; the 5 that had no page yet (Terms, Rules,
 * Refund, Public Offer, Security Policy) got honest "coming soon" stubs rather than fabricated
 * legal text, same convention as the pre-existing Privacy/FAQ stubs. */
const LEGAL_GROUPS: { title: string; links: { label: string; to: string }[] }[] = [
  {
    title: "Yordam va qoidalar",
    links: [
      { label: "Foydalanish shartlari", to: "/terms" },
      { label: "Tez-tez so'raladigan savollar", to: "/faq" },
      { label: "E'lon qoidalari", to: "/rules" },
      { label: "To'lovni qaytarish", to: "/refund" },
    ],
  },
  {
    title: "Siyosat va hujjatlar",
    links: [
      { label: "Ommaviy oferta", to: "/offer" },
      { label: "Maxfiylik siyosati", to: "/privacy" },
      { label: "Xavfsizlik siyosati", to: "/security-policy" },
    ],
  },
];

export function Footer() {
  const { t } = useTranslation();
  const navCols = [
    { title: t("footer.product"), links: ["Buy", "Rent", "Hotels", "Build", "Shop", "AI Search"] },
    { title: t("footer.company"), links: ["About", "Careers", "Press", "Partners", "Contact"] },
  ];
  return (
    <footer className="relative isolate overflow-hidden border-t border-border bg-surface/60">
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center opacity-10"
        style={{ backgroundImage: `url(${footerBg.url})` }}
        aria-hidden
      />
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-x-8 gap-y-12 md:grid-cols-[1.3fr_0.8fr_0.8fr_0.9fr_0.9fr]">
          <div>
            <Logo className="h-9" />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">{t("footer.tagline")}</p>
            <SocialIconsExpanded className="mt-5" />

            {/* Scan-to-open card: branded QR (logo excavated into the center, same trick the
                reference site used with its Taplink badge) pointing at the live production
                domain -- a real mobile-handoff affordance, not decoration. */}
            <div className="mt-6 flex max-w-xs items-center gap-4 rounded-2xl border border-border bg-card p-4 shadow-soft">
              <div className="shrink-0 rounded-xl bg-white p-2">
                <QRCodeSVG
                  value={SITE_URL}
                  size={84}
                  level="H"
                  bgColor="#ffffff"
                  fgColor="#0a0a0a"
                  imageSettings={{
                    src: logoMark,
                    height: 20,
                    width: 20,
                    excavate: true,
                  }}
                />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  <QrCode className="size-3.5 text-primary" />
                  Mobilda oching
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  Kamerangiz bilan skanerlang va{" "}
                  <span className="font-medium text-foreground">activehome.uz</span>ni telefoningizda
                  oching.
                </p>
              </div>
            </div>
          </div>

          {navCols.map((c) => (
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

          {LEGAL_GROUPS.map((g) => (
            <div key={g.title}>
              <div className="text-xs font-semibold uppercase tracking-wider text-foreground">
                {g.title}
              </div>
              <ul className="mt-4 space-y-2.5">
                {g.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      to={l.to}
                      className="text-sm leading-snug text-muted-foreground transition hover:text-foreground"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
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
