import { motion } from "framer-motion";

export function PromoBanner({
  src,
  alt,
  href = "tel:+998555000406",
  aspect = "aspect-[16/9]",
}: {
  src: string;
  alt: string;
  href?: string;
  aspect?: string;
}) {
  return (
    <section className="px-6 py-12">
      <motion.a
        href={href}
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto block max-w-7xl overflow-hidden rounded-3xl border border-border shadow-elevated transition hover:shadow-glow"
      >
        <img src={src} alt={alt} loading="lazy" className={`w-full ${aspect} object-cover`} />
      </motion.a>
    </section>
  );
}
