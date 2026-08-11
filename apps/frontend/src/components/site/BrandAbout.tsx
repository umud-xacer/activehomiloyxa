import { Building2, Home, Wrench, HardHat, ShieldCheck, Handshake } from "lucide-react";
import aboutBrand from "@/assets/about-brand.png.asset.json";
import bgMap from "@/assets/bg-worldmap-logo.png.asset.json";
import { Container } from "@/components/layout/Container";

const pillars = [
  { icon: Home, title: "Ko'chmas mulk", desc: "Sotish, sotib olish va vositachilik." },
  { icon: Wrench, title: "Ta'mirlash", desc: "Usta xizmatlari va ichki bezak." },
  { icon: HardHat, title: "Qurilish", desc: "Materiallar savdosi va yetkazish." },
  { icon: Handshake, title: "Vositachilik", desc: "Ishonchli agentlar tarmog'i." },
  { icon: ShieldCheck, title: "Kafolat", desc: "Har bir bitim uchun himoya." },
  { icon: Building2, title: "Holding", desc: "Yagona tizim, ko'p tarmoq." },
];

export function BrandAbout() {
  return (
    <section id="about" className="relative isolate overflow-hidden py-20 md:py-28">
      {/* Background layers */}
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center opacity-[0.04]"
        style={{ backgroundImage: `url(${bgMap.url})` }}
        aria-hidden
      />
      <div className="absolute inset-0 -z-10 gradient-mesh opacity-60" aria-hidden />
      <div
        className="absolute inset-x-0 top-0 -z-10 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent"
        aria-hidden
      />

      <Container>
        <div className="grid items-stretch gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
          {/* Brand card with provided image */}
          <div className="relative overflow-hidden rounded-3xl border border-glass-border bg-gradient-to-br from-primary via-primary to-primary-glow p-6 shadow-elevated md:p-8">
            {/* decorative grid */}
            <div
              className="pointer-events-none absolute inset-0 opacity-[0.12]"
              style={{
                backgroundImage:
                  "linear-gradient(to right, white 1px, transparent 1px), linear-gradient(to bottom, white 1px, transparent 1px)",
                backgroundSize: "44px 44px",
              }}
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-primary-glow/40 blur-3xl"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-accent/30 blur-3xl"
              aria-hidden
            />

            <div className="relative flex h-full flex-col">
              <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/20 bg-white/10 px-3 py-1 text-xs font-medium uppercase tracking-wider text-primary-foreground/90 backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                Kompaniya haqida
              </span>

              <div className="mt-6 flex flex-1 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.04] p-4 shadow-glow md:p-6">
                <img
                  src={aboutBrand.url}
                  alt="Active Home — uy ta'mirlash xizmatlari"
                  className="max-h-[420px] w-auto rounded-xl object-contain shadow-2xl drop-shadow-[0_12px_32px_rgba(0,0,0,0.35)] md:max-h-[520px]"
                  draggable={false}
                />
              </div>

              <div className="mt-auto grid grid-cols-3 gap-3 pt-8">
                {[
                  { k: "12+", v: "Yo'nalish" },
                  { k: "1,200+", v: "Hamkor" },
                  { k: "24/7", v: "Qo'llab-quvvatlash" },
                ].map((s) => (
                  <div
                    key={s.v}
                    className="rounded-2xl border border-white/15 bg-white/5 px-3 py-4 text-center backdrop-blur"
                  >
                    <div className="font-display text-2xl font-bold text-primary-foreground">
                      {s.k}
                    </div>
                    <div className="mt-1 text-[11px] uppercase tracking-wider text-primary-foreground/70">
                      {s.v}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="flex flex-col justify-center">
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Active Home Holding
            </span>
            <h2 className="mt-4 font-display text-3xl font-bold leading-tight text-foreground md:text-4xl lg:text-5xl">
              Ko‘chmas mulk va uy xizmatlari bo‘yicha{" "}
              <span className="bg-gradient-to-r from-primary to-primary-glow bg-clip-text text-transparent">
                ko‘p tarmoqli holding platformasi
              </span>
              .
            </h2>

            <div className="mt-6 space-y-4 text-base leading-relaxed text-muted-foreground md:text-lg">
              <p>
                <span className="font-semibold text-foreground">Active Home</span> — uy sotish,
                sotib olish va vositachilik xizmatlaridan tortib, ta’mirlash ishlari, usta
                xizmatlari hamda qurilish materiallari savdosigacha bo‘lgan barcha yo‘nalishlarni
                yagona tizimga birlashtiradi.
              </p>
              <p>
                Biz sizga ko‘chmas mulk bilan bog‘liq jarayonlarni soddalashtirish va ishonchli
                hamkorlikni ta’minlashni maqsad qilganmiz.
              </p>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {pillars.map(({ icon: Icon, title, desc }) => (
                <div
                  key={title}
                  className="group flex items-start gap-3 rounded-2xl border border-border bg-card/60 p-4 shadow-soft backdrop-blur transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-elevated"
                >
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-primary-glow text-primary-foreground shadow-glow">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-foreground">{title}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
