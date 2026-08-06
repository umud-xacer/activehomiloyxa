import { useTranslation } from "react-i18next";
import { Globe } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const langs = [
  { code: "en", label: "EN" },
  { code: "uz", label: "UZ" },
  { code: "ru", label: "RU" },
];

export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = (i18n.resolvedLanguage || i18n.language || "en").slice(0, 2);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 py-1.5 text-xs font-medium text-foreground/80 transition hover:bg-card hover:text-foreground"
        aria-label="Change language"
      >
        <Globe className="size-3.5" />
        {langs.find((l) => l.code === current)?.label ?? "EN"}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 min-w-[7rem] overflow-hidden rounded-xl border border-border bg-popover shadow-elevated">
          {langs.map((l) => (
            <button
              key={l.code}
              onClick={() => {
                i18n.changeLanguage(l.code);
                setOpen(false);
              }}
              className={`flex w-full items-center justify-between px-3 py-2 text-xs transition hover:bg-muted ${
                current === l.code ? "text-primary font-semibold" : "text-foreground/80"
              }`}
            >
              <span>{l.label}</span>
              {current === l.code && <span className="size-1.5 rounded-full bg-primary" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
