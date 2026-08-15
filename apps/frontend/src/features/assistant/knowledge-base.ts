/**
 * ActiveHome-only assistant knowledge base. No external LLM call -- keyless by design (matching
 * this project's established keyless-first preference: no paid API key to provision or leak).
 * Each entry is scored by how many of its keywords appear in the user's message; the
 * highest-scoring entry above the threshold answers, otherwise `FALLBACK` fires. This keeps the
 * assistant strictly on-topic by construction (it can only ever say what's in this file) rather
 * than by prompting a general-purpose model not to wander.
 *
 * Swap point: once a real backend AI endpoint exists, replace `answer()`'s body with that call --
 * the only caller (`ChatAssistant`) already awaits it.
 */

interface KBEntry {
  topic: string;
  keywords: string[];
  reply: string;
}

const KB: KBEntry[] = [
  {
    topic: "greeting",
    keywords: ["salom", "assalomu", "hello", "hi", "yaxshimisiz", "qalaysiz"],
    reply:
      "Assalomu alaykum! Men Active Home yordamchisiman. Uy va mulk qidirish, e'lon joylashtirish, usta xizmatlari, qurilish mollari, investitsiya imkoniyatlari yoki bron qilish haqida so'rashingiz mumkin.",
  },
  {
    topic: "buy_property",
    keywords: ["uy", "kvartira", "mulk", "xonadon", "hovli", "kotej", "sotib ol", "uy ol"],
    reply:
      "Ko'chmas mulk bo'limida kvartira, hovli, kotej va boshqa turdagi mulklarni ko'rishingiz mumkin. Bosh sahifadagi qidiruv orqali yoki \"Kategoriyalar\" qatoridan mos kategoriyani tanlab, filtrlar yordamida narx va joylashuv bo'yicha qidirishingiz mumkin.",
  },
  {
    topic: "rent_property",
    keywords: ["ijara", "ijaraga", "arenda"],
    reply:
      "Ijaraga uy yoki xonadon topish uchun \"Ko'chmas mulk\" bo'limidan foydalaning va qidiruv natijalarini \"Ijara\" turi bo'yicha filtrlang. Har bir e'lon admin tomonidan tekshirilganidan keyingina saytda ko'rinadi.",
  },
  {
    topic: "list_property",
    keywords: ["elon", "e'lon", "joylash", "sotmoqchi", "sotaman", "sotuvga", "reklama qil"],
    reply:
      "E'lon joylashtirish uchun avval ro'yxatdan o'ting (jismoniy yoki yuridik shaxs sifatida), so'ng \"E'lon joylash\" bo'limi orqali mulk yoki xizmatingiz haqida ma'lumot kiriting. Har bir yangi e'lon admin tomonidan ko'rib chiqilib, tasdiqlangach chop etiladi.",
  },
  {
    topic: "services",
    keywords: ["usta", "xizmat", "ta'mirlash", "tamirlash", "montaj", "santexnik", "elektrik"],
    reply:
      "\"Usta xizmatlari\" bo'limida tekshirilgan ustalar va xizmat ko'rsatuvchilarni topasiz — ta'mirlash, montaj va boshqa uy xizmatlari uchun to'g'ridan-to'g'ri murojaat qilishingiz mumkin.",
  },
  {
    topic: "materials",
    keywords: ["qurilish", "material", "mol", "sement", "g'isht", "gisht", "armatura"],
    reply:
      "Qurilish mollari (sement, g'isht, armatura va boshqalar) alohida kategoriyada joylashgan — kerakli mahsulotni tanlab, sotuvchi bilan bog'lanishingiz mumkin.",
  },
  {
    topic: "invest",
    keywords: ["invest", "investitsiya", "investor", "mablag'", "loyiha", "portfel"],
    reply:
      "Investorlar uchun \"Investorlar\" bo'limida real qurilish va ko'chmas mulk loyihalarini ko'rib chiqishingiz, har birining tafsilotlari (maqsad summa, ROI, muddat) bilan tanishishingiz mumkin.",
  },
  {
    topic: "recreation_booking",
    keywords: ["dam olish", "turbaza", "bron", "mehmonxona", "hostel", "hotel", "kurort"],
    reply:
      "Dam olish maskanlari va mehmonxonalarni xarita orqali topib, joylashuv va narxlarini solishtirib bron qilishingiz mumkin. Bron qilish tafsilotlari har bir e'londa ko'rsatilgan.",
  },
  {
    topic: "organizations",
    keywords: ["kompaniya", "tashkilot", "hamkor", "bank", "ipoteka"],
    reply:
      "Bosh sahifadagi \"Tashkilotlar\" bo'limida tasdiqlangan hamkor banklar va tashkilotlarni ko'rishingiz mumkin — masalan, ipoteka uchun hamkor banklar ro'yxati shu yerda.",
  },
  {
    topic: "signup",
    keywords: ["ro'yxat", "royxat", "kirish", "akkaunt", "parol", "sign up", "sign in", "hisob"],
    reply:
      "Ro'yxatdan o'tishda jismoniy shaxs, yuridik shaxs (ishlab chiqaruvchi) yoki investor turlaridan birini tanlaysiz. Email yoki telefon (SMS-kod) orqali ro'yxatdan o'tish mumkin; ba'zi akkaunt turlari admin tasdig'idan keyin faollashadi.",
  },
  {
    topic: "trust",
    keywords: ["ishonch", "tasdiq", "xavfsiz", "firibgar", "verify", "tekshir"],
    reply:
      "Active Home'da har bir yangi akkaunt va e'lon firibgarlikdan himoya qilish maqsadida admin tomonidan qo'lda tekshiriladi — shuning uchun platformadagi barcha tasdiqlangan e'lonlarga ishonish mumkin.",
  },
  {
    topic: "map",
    keywords: ["xarita", "joylashuv", "map", "manzil"],
    reply:
      "Bosh sahifadagi jonli xaritada barcha e'lonlarni joylashuv bo'yicha ko'rishingiz, filtrlashingiz va tanlangan manzilgacha yo'nalish (haydash yoki piyoda) olishingiz mumkin.",
  },
  {
    topic: "contact",
    keywords: ["yordam", "murojaat", "telefon raqam", "aloqa", "qollab"],
    reply:
      "Qo'shimcha yordam kerak bo'lsa, sahifa pastidagi ijtimoiy tarmoq havolalari (Telegram, Instagram va boshqalar) orqali biz bilan bog'lanishingiz mumkin.",
  },
];

export const FALLBACK =
  "Men faqat Active Home platformasi bo'yicha — ko'chmas mulk, qurilish, usta xizmatlari, investitsiyalar, bron qilish va tashkilotlar haqida — savollarga javob bera olaman. Savolingizni shu mavzularda qayta so'rab ko'rasizmi?";

export const SUGGESTIONS = [
  "Uy qanday qidiraman?",
  "E'lon qanday joylashtiraman?",
  "Investorlar uchun nima bor?",
  "Bron qilish qanday ishlaydi?",
];

function normalize(s: string): string {
  return s.toLowerCase().replace(/[’‘'`]/g, "'");
}

export async function answer(message: string): Promise<string> {
  const text = normalize(message);
  let best: KBEntry | null = null;
  let bestScore = 0;

  for (const entry of KB) {
    const score = entry.keywords.reduce(
      (acc, kw) => (text.includes(normalize(kw)) ? acc + 1 : acc),
      0,
    );
    if (score > bestScore) {
      bestScore = score;
      best = entry;
    }
  }

  return best ? best.reply : FALLBACK;
}
