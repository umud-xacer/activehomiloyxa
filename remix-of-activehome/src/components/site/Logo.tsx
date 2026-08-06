export function Logo({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <div className={`inline-flex items-center ${className}`}>
      <img
        src="/logo.jpg"
        alt="ActiveHome"
        className="h-full w-auto rounded-md"
        draggable={false}
      />
    </div>
  );
}
