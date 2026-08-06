import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";

export function CtaBand() {
  const { t } = useTranslation();
  return (
    <section className="px-6 py-24">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] border border-border bg-primary px-8 py-16 text-center shadow-elevated sm:px-12 sm:py-20"
      >
        <div
          className="absolute inset-0 bg-cover bg-center opacity-30"
          style={{ backgroundImage: `url(/background.jpg)` }}
          aria-hidden
        />
        <div className="gradient-mesh absolute inset-0 opacity-60" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,oklch(1_0_0_/_0.08),transparent_60%)]" />
        <div className="relative">
          <h2 className="font-display text-balance text-3xl font-semibold tracking-tight text-primary-foreground sm:text-5xl md:text-6xl">
            {t("cta.title")}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-primary-foreground/75">
            {t("cta.subtitle")}
          </p>
          <form className="mx-auto mt-8 flex max-w-md flex-col gap-2 sm:flex-row">
            <input
              type="email"
              required
              placeholder="you@email.com"
              className="min-w-0 flex-1 rounded-full border border-white/15 bg-white/10 px-5 py-3 text-sm text-primary-foreground placeholder:text-primary-foreground/50 backdrop-blur focus:border-white/30 focus:outline-none"
            />
            <button
              type="submit"
              className="inline-flex items-center justify-center gap-1.5 rounded-full bg-primary-foreground px-5 py-3 text-sm font-semibold text-primary transition hover:shadow-glow"
            >
              {t("cta.button")} <ArrowRight className="size-4" />
            </button>
          </form>
        </div>
      </motion.div>
    </section>
  );
}
