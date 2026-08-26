import logoMark from "@/assets/logo-mark.png";

/**
 * Icon + wordmark. The icon is the real ActiveHome brand mark (carried over from the platform's
 * original build, `ActiveReturn`); previously this rendered a remotely-hosted placeholder image
 * that 404s outside the Lovable-hosted preview, showing a broken-image glyph in every header.
 * `className` sets the overall height (e.g. `h-8`); the wordmark's size stays fixed since it reads
 * fine across every height this component is actually used at (h-6 through h-9).
 */
export function Logo({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <img
        src={logoMark}
        alt=""
        className="h-full w-auto shrink-0 rounded-[7px]"
        draggable={false}
      />
      <span className="font-display text-[0.8rem] font-bold leading-none tracking-tight text-foreground sm:text-[0.95rem]">
        ActiveHome
      </span>
    </div>
  );
}
