import { useTranslation } from "react-i18next";
import { Logo } from "./Logo";

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
        style={{ backgroundImage: `url(/background.jpg)` }}
        aria-hidden
      />
      <div className="mx-auto max-w-7xl px-6 py-16">
        <div className="grid gap-12 md:grid-cols-[1.4fr_repeat(3,1fr)]">
          <div>
            <Logo className="h-9" />
            <p className="mt-4 max-w-xs text-sm text-muted-foreground">{t("footer.tagline")}</p>
          </div>
          {cols.map((c) => (
            <div key={c.title}>
              <div className="text-xs font-semibold uppercase tracking-wider text-foreground">
                {c.title}
              </div>
              <ul className="mt-4 space-y-2.5">
                {c.links.map((l) => (
                  <li key={l}>
                    <a
                      href="#"
                      className="text-sm text-muted-foreground transition hover:text-foreground"
                    >
                      {l}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row sm:items-center">
          <div>© {new Date().getFullYear()} ActiveHome. {t("footer.rights")}</div>
          <div className="flex gap-4">
            <a href="#" className="hover:text-foreground">Twitter</a>
            <a href="#" className="hover:text-foreground">LinkedIn</a>
            <a href="#" className="hover:text-foreground">Instagram</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
