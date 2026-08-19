import { motion } from "framer-motion";

export function PromoBanner({
  src,
  alt,
  href = "tel:+998555000406",
  aspect = "aspect-[16/9]",
  fit = "cover",
}: {
  src: string;
  alt: string;
  href?: string;
  /** Only used when `fit="cover"` -- a portrait creative (fit="contain") sizes itself by height
   * instead, so a fixed crop aspect would fight that. */
  aspect?: string;
  /** "cover" fills a wide `aspect` box, cropping the source to match -- right for landscape
   * creatives. "contain" instead caps the image by height and lets width follow its own natural
   * ratio, so a portrait/poster-shaped creative shows in full, uncropped. */
  fit?: "cover" | "contain";
}) {
  return (
    <section className="px-6 py-12">
      <motion.a
        href={href}
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className={
          fit === "contain"
            ? "mx-auto block w-fit overflow-hidden rounded-3xl border border-border shadow-elevated transition hover:shadow-glow"
            : "mx-auto block max-w-7xl overflow-hidden rounded-3xl border border-border shadow-elevated transition hover:shadow-glow"
        }
      >
        {fit === "contain" ? (
          <img
            src={src}
            alt={alt}
            loading="lazy"
            className="h-[440px] w-auto object-contain sm:h-[560px]"
          />
        ) : (
          <img src={src} alt={alt} loading="lazy" className={`w-full ${aspect} object-cover`} />
        )}
      </motion.a>
    </section>
  );
}
