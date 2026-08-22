/**
 * Homepage promo carousel -- replaces the old single-static-image `PromoBanner` with a real
 * multi-slide slider (autoplay, prev/next arrows, dot pagination, each slide its own click-through
 * link), built on the app's existing `components/ui/carousel.tsx` (Embla, already a dependency,
 * already used nowhere else -- no new UI primitive introduced) plus `embla-carousel-autoplay`.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Autoplay from "embla-carousel-autoplay";
import { motion } from "framer-motion";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from "@/components/ui/carousel";
import { cn } from "@/lib/utils";

export interface PromoSlide {
  src: string;
  alt: string;
  href: string;
  /** "cover" fills a 16:9 box (landscape creatives). "contain" caps by height and keeps the
   * source's own ratio uncropped (portrait/poster creatives). */
  fit?: "cover" | "contain";
}

export function PromoCarousel({ slides }: { slides: PromoSlide[] }) {
  const [api, setApi] = useState<CarouselApi>();
  const [selected, setSelected] = useState(0);
  const multi = slides.length > 1;

  // Embla re-initializes (destroying and restarting the Autoplay timer) whenever the `opts`/
  // `plugins` values it's passed change identity -- a bare `[Autoplay({...})]`/`{...}` literal in
  // JSX is a NEW array/object/plugin-instance on every re-render, and this component re-renders
  // on every slide change (`setSelected` below), so a fresh Autoplay plugin was being created and
  // torn down before its own 5s timer ever had an uninterrupted chance to fire -- confirmed live,
  // autoplay never advanced past slide 1. Memoized so the same instances persist across renders.
  const opts = useMemo(() => ({ loop: multi, align: "start" as const }), [multi]);
  const plugins = useMemo(
    () => (multi ? [Autoplay({ delay: 5000, stopOnInteraction: true })] : []),
    [multi],
  );

  useEffect(() => {
    if (!api) return;
    const onSelect = () => setSelected(api.selectedScrollSnap());
    onSelect();
    api.on("select", onSelect);
    api.on("reInit", onSelect);
    return () => {
      api.off("select", onSelect);
      api.off("reInit", onSelect);
    };
  }, [api]);

  const scrollTo = useCallback((index: number) => api?.scrollTo(index), [api]);

  if (slides.length === 0) return null;

  return (
    <section className="px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="mx-auto max-w-7xl"
      >
        <Carousel setApi={setApi} opts={opts} plugins={plugins}>
          <CarouselContent className="-ml-0">
            {slides.map((slide, i) => (
              <CarouselItem key={slide.src} className="basis-full pl-0">
                <a
                  href={slide.href}
                  className="block overflow-hidden rounded-3xl border border-border shadow-elevated transition hover:shadow-glow"
                >
                  <img
                    src={slide.src}
                    alt={slide.alt}
                    loading={i === 0 ? "eager" : "lazy"}
                    className={
                      (slide.fit ?? "cover") === "contain"
                        ? "mx-auto h-[440px] w-auto object-contain sm:h-[560px]"
                        : "aspect-[16/9] w-full object-cover"
                    }
                  />
                </a>
              </CarouselItem>
            ))}
          </CarouselContent>

          {multi && (
            <>
              <CarouselPrevious className="left-4 border-none bg-background/80 backdrop-blur" />
              <CarouselNext className="right-4 border-none bg-background/80 backdrop-blur" />
            </>
          )}
        </Carousel>

        {multi && (
          <div className="mt-4 flex items-center justify-center gap-2">
            {slides.map((slide, i) => (
              <button
                key={slide.src}
                type="button"
                aria-label={`${i + 1}-slaydga o'tish`}
                onClick={() => scrollTo(i)}
                className={cn(
                  "h-2 rounded-full transition-all",
                  i === selected ? "w-6 bg-primary" : "w-2 bg-border hover:bg-primary/50",
                )}
              />
            ))}
          </div>
        )}
      </motion.div>
    </section>
  );
}
