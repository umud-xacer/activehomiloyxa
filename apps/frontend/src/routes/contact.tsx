import { createFileRoute } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Mail, MessageCircle } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { SocialIconsExpanded } from "@/components/site/SocialIcons";

export const Route = createFileRoute("/contact")({
  head: () => ({
    meta: [
      { title: "Aloqa — ActiveHome" },
      {
        name: "description",
        content: "ActiveHome jamoasi bilan bog'laning — email, Telegram va ijtimoiy tarmoqlar.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Aloqa"
        title="Biz bilan bog'laning"
        description="Savolingiz yoki taklifingiz bo'lsa, quyidagi kanallardan istalgani orqali murojaat qiling."
      />
      <div className="mx-auto max-w-2xl px-4 pb-24 pt-10 lg:px-8">
        <div className="grid gap-4 sm:grid-cols-2">
          <motion.a
            href="mailto:support@activehome.uz"
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="group flex items-start gap-4 rounded-2xl border border-border bg-card p-6 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
          >
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Mail className="size-5" />
            </div>
            <div>
              <h3 className="font-display text-sm font-semibold text-foreground">Email</h3>
              <p className="mt-1 text-sm text-muted-foreground group-hover:text-foreground">
                support@activehome.uz
              </p>
            </div>
          </motion.a>

          <motion.a
            href="https://t.me/Active_Home"
            target="_blank"
            rel="noopener noreferrer"
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.05 }}
            className="group flex items-start gap-4 rounded-2xl border border-border bg-card p-6 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
          >
            <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <MessageCircle className="size-5" />
            </div>
            <div>
              <h3 className="font-display text-sm font-semibold text-foreground">Telegram</h3>
              <p className="mt-1 text-sm text-muted-foreground group-hover:text-foreground">
                @Active_Home
              </p>
            </div>
          </motion.a>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="mt-10"
        >
          <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Ijtimoiy tarmoqlar
          </h2>
          <SocialIconsExpanded className="mt-4" />
        </motion.div>
      </div>
    </AppShell>
  );
}
