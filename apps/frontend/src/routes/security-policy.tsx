import { createFileRoute } from "@tanstack/react-router";
import { LegalPage, LegalBoxGrid } from "@/components/layout/LegalPage";

/** The public "Xavfsizlik siyosati" document -- distinct from `/security`, which is the
 * authenticated account-security settings page (2FA/sessions). Two different things that happen
 * to share a name in the source document; kept at separate routes so `requireAuth` on the
 * settings page doesn't block this public one. */
export const Route = createFileRoute("/security-policy")({
  head: () => ({
    meta: [
      { title: "Xavfsizlik siyosati — ActiveHome" },
      {
        name: "description",
        content:
          "ActiveHome platformasining texnik va foydalanuvchi xavfsizligi bo'yicha siyosati.",
      },
    ],
  }),
  component: Page,
});

function Page() {
  return (
    <LegalPage
      eyebrow="Huquqiy"
      title="Xavfsizlik siyosati"
      description="Platformamiz sizning ma'lumotlaringiz va bitimlaringiz xavfsizligini qanday ta'minlaydi."
    >
      <LegalBoxGrid
        items={[
          {
            title: "Texnik himoya",
            body: "SSL (HTTPS), muntazam zaxira nusxalash, 24/7 monitoring.",
          },
          {
            title: "Kirish nazorati",
            body: "Xodimlar uchun cheklangan kirish huquqi, parollar hash holatida saqlanadi.",
          },
          {
            title: "Foydalanuvchi javobgarligi",
            body: "Parolni hech kimga bermang, shubhali havolalarga kirmang, begona qurilmadan chiqishni unutmang.",
          },
          {
            title: "Firibgarlikdan himoya",
            body: "Qoidabuzarlikda e'lon o'chiriladi, akkaunt bloklanadi, kerak bo'lsa huquqiy organlarga murojaat qilinadi.",
          },
        ]}
      />
    </LegalPage>
  );
}
