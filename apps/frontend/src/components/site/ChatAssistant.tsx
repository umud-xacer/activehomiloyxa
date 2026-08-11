import { useEffect, useRef, useState, type FormEvent } from "react";
import { motion } from "framer-motion";
import { Bot, Send, X, Sparkles, User } from "lucide-react";
import { answer, SUGGESTIONS } from "@/features/assistant/knowledge-base";

const EASE = [0.22, 1, 0.36, 1] as const;

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

const WELCOME: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "Assalomu alaykum! Men Active Home yordamchisiman. Sizga qanday yordam bera olaman? Uy va mulk, xizmatlar, investorlar, bron qilish yoki kompaniyalar haqida so'rashingiz mumkin.",
};

/**
 * Global "AI Chat Assistant" -- a self-positioned floating widget (not part of the navbar's own
 * layout flow, so the navbar redesign doesn't have to make room for it) rendered once from
 * `Navbar.tsx`, which itself renders on every page (`routes/index.tsx` and `AppShell.tsx`). Opens
 * itself shortly after mount -- since neither of those two Navbar call sites sits inside one
 * shared persistent root layout, every full navigation between them remounts this component too,
 * so the panel greets the visitor again each time they land on a fresh page, not just on a hard
 * refresh. Always closable (X button) and always reachable again via the floating bubble that
 * remains once closed. Answering logic lives in `features/assistant/knowledge-base.ts` --
 * deliberately keyless/on-topic-by-construction rather than a general LLM call (see that file's
 * header).
 */
export function ChatAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setOpen(true), 700);
    return () => window.clearTimeout(timer);
  }, []);

  // Lets other components (e.g. MobileMenu's "AI Yordamchi" item) open this
  // widget without needing to lift its state -- it's a self-positioned
  // singleton rendered once from Navbar, so a DOM event is simpler than
  // plumbing a shared store through every caller.
  useEffect(() => {
    const openHandler = () => setOpen(true);
    window.addEventListener("activehome:open-chat", openHandler);
    return () => window.removeEventListener("activehome:open-chat", openHandler);
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  const send = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || typing) return;
    setInput("");
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", text: trimmed }]);
    setTyping(true);
    const reply = await answer(trimmed);
    // A brief pause reads as "thinking" rather than an instant canned lookup -- cosmetic only.
    await new Promise((r) => setTimeout(r, 450 + Math.random() * 350));
    setTyping(false);
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "assistant", text: reply }]);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void send(input);
  };

  return (
    <>
      {/* Always mounted (unlike the panel below) -- toggled via inline style, not Tailwind
          opacity/scale utility classes (their first use anywhere in this codebase never got
          picked up by the dev server's JIT scan) and not AnimatePresence (an always-present
          element next to a mount/unmount-driven AnimatePresence sibling toggling on the same
          instant is unreliable exit-animation territory, since `open` flips in one render, not
          two). Pointer-events are set explicitly rather than relying on unmount to disable them. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Active Home AI yordamchisi"
        tabIndex={open ? -1 : 0}
        style={
          open
            ? { opacity: 0, transform: "scale(0.75)", pointerEvents: "none" }
            : { pointerEvents: "auto" }
        }
        className="fixed bottom-5 right-4 z-[71] flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-elevated transition-all duration-200 ease-out hover:scale-[1.05] hover:shadow-glow active:scale-[0.97] sm:right-6"
      >
        <Bot className="size-6" />
      </button>

      {/* Backdrop + panel are always mounted (same reasoning as the bubble above -- an
          AnimatePresence-driven mount/unmount here got visibly stuck mid-exit in testing,
          leaving both un-clickable-but-still-in-the-DOM) and toggled via inline style instead. */}
      <button
        type="button"
        aria-label="Yopish"
        tabIndex={open ? 0 : -1}
        onClick={() => setOpen(false)}
        style={open ? undefined : { opacity: 0, pointerEvents: "none" }}
        className="fixed inset-0 z-[70] cursor-default bg-black/10 backdrop-blur-[2px] transition-opacity duration-200 sm:bg-transparent sm:backdrop-blur-none"
      />
      <div
        style={
          open
            ? undefined
            : { opacity: 0, transform: "translateY(16px) scale(0.97)", pointerEvents: "none" }
        }
        aria-hidden={!open}
        className="glass fixed bottom-5 right-4 z-[71] flex h-[min(32rem,75vh)] w-[calc(100vw-2rem)] max-w-sm flex-col overflow-hidden rounded-3xl shadow-elevated transition-all duration-200 ease-out sm:right-6"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center gap-2.5 border-b border-border/60 px-4 py-3.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Bot className="size-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="font-display text-sm font-semibold text-foreground">
              Active Home Yordamchisi
            </div>
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <span className="size-1.5 rounded-full bg-success" />
              Onlayn
            </div>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Yopish"
            className="flex size-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Messages */}
        <div ref={listRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((m) => (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
              className={`flex items-end gap-2 ${m.role === "user" ? "flex-row-reverse" : ""}`}
            >
              <div
                className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
                  m.role === "user"
                    ? "bg-secondary text-secondary-foreground"
                    : "bg-primary/10 text-primary"
                }`}
              >
                {m.role === "user" ? <User className="size-3" /> : <Bot className="size-3" />}
              </div>
              <div
                className={`max-w-[80%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                  m.role === "user"
                    ? "rounded-br-sm bg-primary text-primary-foreground"
                    : "rounded-bl-sm bg-card text-foreground shadow-soft"
                }`}
              >
                {m.text}
              </div>
            </motion.div>
          ))}

          {typing && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-end gap-2"
            >
              <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Bot className="size-3" />
              </div>
              <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-card px-3.5 py-3 shadow-soft">
                {[0, 1, 2].map((i) => (
                  <motion.span
                    key={i}
                    className="size-1.5 rounded-full bg-muted-foreground/60"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{
                      duration: 1,
                      repeat: Infinity,
                      delay: i * 0.15,
                      ease: "easeInOut",
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}

          {messages.length === 1 && !typing && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => void send(s)}
                  className="inline-flex items-center gap-1 rounded-full border border-border bg-card/60 px-2.5 py-1 text-[11px] font-medium text-foreground/75 transition hover:border-primary/40 hover:text-foreground"
                >
                  <Sparkles className="size-2.5 text-primary" />
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Input */}
        <form onSubmit={onSubmit} className="shrink-0 border-t border-border/60 p-3">
          <div className="flex items-center gap-2 rounded-full border border-border bg-card px-2 py-1.5">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Savolingizni yozing…"
              className="min-w-0 flex-1 bg-transparent px-2 text-[13px] text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || typing}
              aria-label="Yuborish"
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition hover:shadow-glow disabled:opacity-40"
            >
              <Send className="size-3.5" />
            </button>
          </div>
          <div className="mt-2 text-center text-[10px] text-muted-foreground/70">
            Faqat Active Home platformasi bo'yicha savollarga javob beradi
          </div>
        </form>
      </div>
    </>
  );
}
