import { useRef } from "react";
import { motion, useScroll, useTransform, type MotionValue } from "framer-motion";
import { Building2, Hammer, Wrench, Blocks, type LucideIcon } from "lucide-react";

const EASE = [0.22, 1, 0.36, 1] as const;

/**
 * "About Active Home" -- the copy is verbatim, as given, in three pieces (headline + two
 * paragraphs) with nothing added, cut, or reworded. Everything else here is presentation only: a
 * bounded premium panel instead of the text sitting bare on the page background, wordless
 * floating category icons for visual interest (`useScroll` + `useTransform` parallax, a different
 * depth per icon, plus a slow continuous bob), and a staggered scroll-reveal so the three pieces
 * arrive in reading order instead of all at once.
 */

interface FloaterSpec {
  Icon: LucideIcon;
  className: string;
  accent: string;
  depth: number;
  bobDuration: number;
}

const FLOATERS: FloaterSpec[] = [
  {
    Icon: Building2,
    className: "left-[7%] top-[16%]",
    accent: "var(--primary)",
    depth: 55,
    bobDuration: 5.2,
  },
  {
    Icon: Hammer,
    className: "right-[9%] top-[13%]",
    accent: "var(--primary-glow)",
    depth: 85,
    bobDuration: 4.6,
  },
  {
    Icon: Wrench,
    className: "left-[9%] bottom-[15%]",
    accent: "var(--accent)",
    depth: 70,
    bobDuration: 5.8,
  },
  {
    Icon: Blocks,
    className: "right-[8%] bottom-[17%]",
    accent: "var(--primary)",
    depth: 45,
    bobDuration: 6.2,
  },
];

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.75, delay: i * 0.15, ease: EASE },
  }),
};

function Floater({ spec, progress }: { spec: FloaterSpec; progress: MotionValue<number> }) {
  const { Icon, className, accent, depth, bobDuration } = spec;
  const y = useTransform(progress, [0, 1], [depth, -depth]);

  return (
    <motion.div
      style={{ y }}
      className={`pointer-events-none absolute hidden lg:block ${className}`}
    >
      <motion.div
        animate={{ y: [0, -12, 0] }}
        transition={{ duration: bobDuration, repeat: Infinity, ease: "easeInOut" }}
        className="flex size-12 items-center justify-center rounded-2xl border border-border bg-card/70 shadow-soft backdrop-blur-xl"
        style={{ color: accent }}
      >
        <Icon className="size-5" />
      </motion.div>
    </motion.div>
  );
}

export function MissionBand() {
  const sectionRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start end", "end start"] });
  const glowY = useTransform(scrollYProgress, [0, 1], [-30, 30]);

  return (
    <section ref={sectionRef} className="relative overflow-hidden px-6 py-24">
      <motion.div
        style={{ y: glowY }}
        className="pointer-events-none absolute inset-x-0 top-1/2 -z-10 h-[70%] -translate-y-1/2 bg-[radial-gradient(ellipse_at_center,oklch(0.65_0.18_275_/_0.12),transparent_65%)]"
        aria-hidden
      />

      <div className="relative mx-auto max-w-4xl overflow-hidden rounded-[2.5rem] border border-border bg-card/60 px-8 py-16 shadow-elevated backdrop-blur-xl sm:px-14 sm:py-20">
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-40" aria-hidden />

        {FLOATERS.map((spec, i) => (
          <Floater key={i} spec={spec} progress={scrollYProgress} />
        ))}

        <motion.div
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: "-100px" }}
          variants={{ show: { transition: { staggerChildren: 0.15 } } }}
          className="relative mx-auto max-w-2xl text-center"
        >
          <motion.div
            variants={fadeUp}
            custom={0}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur"
          >
            <span className="size-1.5 rounded-full bg-primary" />
            Active Home
          </motion.div>

          <motion.h2
            variants={fadeUp}
            custom={1}
            className="font-display mt-6 text-balance text-3xl font-semibold leading-[1.2] tracking-tight text-foreground sm:text-4xl md:text-[2.75rem]"
          >
            Ko‘chmas mulk va uy xizmatlari bo‘yicha ko‘p tarmoqli holding platformasi.
          </motion.h2>

          <motion.div
            variants={fadeUp}
            custom={2}
            className="mx-auto mt-6 h-px w-16 bg-gradient-to-r from-transparent via-primary/50 to-transparent"
          />

          <motion.p
            variants={fadeUp}
            custom={3}
            className="mt-6 text-balance text-base leading-relaxed text-muted-foreground sm:text-lg"
          >
            Active Home — uy sotish, sotib olish va vositachilik xizmatlaridan tortib, ta’mirlash
            ishlari, usta xizmatlari hamda qurilish materiallari savdosigacha bo‘lgan barcha
            yo‘nalishlarni yagona tizimga birlashtiradi.
          </motion.p>

          <motion.p
            variants={fadeUp}
            custom={4}
            className="mx-auto mt-4 max-w-xl text-balance text-sm leading-relaxed text-muted-foreground/90 sm:text-base"
          >
            Biz sizga ko‘chmas mulk bilan bog‘liq jarayonlarni soddalashtirish va ishonchli
            hamkorlikni ta’minlashni maqsad qilganmiz.
          </motion.p>
        </motion.div>
      </div>
    </section>
  );
}
