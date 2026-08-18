import { useTranslation } from "react-i18next";
import { Link } from "@tanstack/react-router";
import { QRCodeSVG } from "qrcode.react";
import { QrCode } from "lucide-react";
import { Logo } from "./Logo";
import { SocialIconsExpanded } from "./SocialIcons";
import { Container } from "@/components/layout/Container";
import logoMark from "@/assets/logo-mark.png";

/** Every link points at a real route. `null` means no page exists yet for that label -- left
 * unlinked rather than wired to `#` or a fabricated page. Hotels/Build/Careers point at the real
 * catalog category that actually covers that topic (`/hotels`, `/construction`, `/jobs` were
 * always-empty top-level stubs; `/categories/mexmonxona`, `/categories/qurilish-materiallari`,
 * `/categories/ish-orni` are the real, populated pages a visitor actually wants). "AI Search"
 * points at the real site-wide search built this session (`/search`) rather than a page that
 * never existed. Press has no real content anywhere in the app yet -- left unlinked rather than
 * invent a redirect target for it. */
const FOOTER_LINK_TO: Record<string, string | null> = {
  Buy: "/properties",
  Rent: "/properties",
  Hotels: "/categories/mexmonxona",
  Build: "/categories/qurilish-materiallari",
  Shop: "/materials",
  "AI Search": "/search",
  About: "/about",
  Careers: "/categories/ish-orni",
  Press: null,
  Partners: "/list",
  Contact: "/contact",
};

/** Taplink hand-off link the footer QR code points visitors to on their phone
 * (tracked with `from=qr` so scans are distinguishable from other Taplink traffic). */
const QR_TARGET_URL = "https://taplink.cc/activehome.uz?from=qr";

/** Legal/info links, split into two short, clearly-labeled groups (mirrors how every real
 * marketplace footer organizes this -- one glance answers "where are the rules" vs "where are
 * the policies"). Every entry links to a real route with real content (Terms/Rules/Refund/Offer/
 * Security Policy all live under `LegalPage`, see routes/terms.tsx etc.). */
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
    <footer className="border-t border-border bg-background">
      <Container className="py-20">
        {/* `sm`/`md` (tablet) get a 2-column step instead of jumping straight from 1 to the full
            5-column asymmetric layout -- at ~768px, 5 fractional columns squeeze the two legal
            groups down to ~95px each, wrapping every link label. Full layout only from `lg`+. */}
        <div className="grid gap-x-8 gap-y-14 sm:grid-cols-2 lg:grid-cols-[1.3fr_0.8fr_0.8fr_0.9fr_0.9fr] lg:gap-x-10">
          <div>
            <Logo className="h-9" />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">{t("footer.tagline")}</p>
            <SocialIconsExpanded className="mt-5" />

            {/* Scan-to-open card: branded QR (logo excavated into the center, same trick the
                reference site used with its Taplink badge) pointing at the Taplink hand-off
                page -- a real mobile-handoff affordance, not decoration. */}
            <div className="mt-6 flex max-w-xs items-center gap-4 rounded-2xl border border-border bg-card p-4 shadow-soft">
              <div className="shrink-0 rounded-xl bg-white p-2">
                <QRCodeSVG
                  value={QR_TARGET_URL}
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
                  <span className="font-medium text-foreground">activehome.uz</span>ni
                  telefoningizda oching.
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
      </Container>
    </footer>
  );
}
