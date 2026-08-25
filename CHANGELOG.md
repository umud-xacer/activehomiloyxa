# CHANGELOG

ActiveHome (activehome.uz) loyihasining yirik bosqichlari, xronologik tartibda. Har bir push
`main`ga avtomatik deploy qilinadi (`.github/workflows/deploy.yml`), shuning uchun bu yerdagi
sanalar production'ga chiqish sanalari bilan mos keladi. Format erkin -- kichik tuzatish/bugfix
commitlari emas, faqat foydalanuvchiga sezilarli yirik bosqichlar qayd etiladi.

## 2026-08-25 -- "Sotildi" (Mark as Sold) hayot tsikli + yakuniy CI tozalash

- **E'lon hayot tsikliga yangi holat qo'shildi: `SOLD`** (`LifecycleState`ning ilgari qat'iy
  yettita qiymatli to'plami sakkiztaga kengaytirildi, `TransitionKind.SELL` bilan birga).
  Sotuvchi endi sotuvchi paneli va admin paneldan e'lonni "Sotildi deb belgilash" tugmasi orqali
  belgilay oladi -- e'lon katalog/qidiruvdan chiqadi (boshqa `ARCHIVED` holatlari kabi), lekin
  sotuvchining o'z ro'yxatida "Sotilganlar" bo'limida qoladi va o'z havolasi orqali hali ham
  ochiladi (404 emas), "Bu mahsulot sotilgan" belgisi va o'xshash e'lonlar tavsiyasi bilan.
- **Yangi `ListingSold` domain-hodisasi** -- `ListingArchived`dan ataylab alohida (bildirishnoma
  shabloni matn jihatidan farq qiladi), `search` va `notifications` modullariga ulandi.
- **`window.confirm()` butunlay olib tashlandi** -- barcha o'chirish tugmalari endi qayta
  ishlatiladigan `ConfirmDialog` komponenti (shadcn `AlertDialog` asosida) orqali ishlaydi,
  brauzer-darajasidagi standart dialog yo'q.
- **ADR-0011 yozildi** (`docs/adr/0011-mark-as-sold-listing-lifecycle-state.md`) -- `ListingSold`
  hodisasi ilgari `contracts/events/__init__.py`ning muzlatilgan `EVENT_CATALOGUE` reestriga hech
  qachon ro'yxatdan o'tkazilmagan edi (real xato, shu tozalash bosqichida topildi va tuzatildi).
- **CI pipeline to'liq yashil holatga keltirildi**:
  - QG-04 (90%-domen/ilova-qatlami coverage floor) -- oxirgi 11 ta bayroqlangan fayl ham 90%+
    darajaga chiqarildi (`catalog/application/listing_use_cases.py`, uchta `identity` fayli,
    to'rtta `profiles` fayli, `configuration/domain/whitelist.py`, `billing`ning ikkita fayli) --
    real xulq-atvorli testlar bilan, ko'pchiligi 100%ga yetdi.
  - QG-03b (OpenSearch/MinIO to'liq E2E benchmark) -- haqiqiy sabab topildi: benchmark
    testlarining o'zi (`tests/performance/test_benchmark_*.py`, to'rtta fayl) global per-IP
    rate-limit (`GlobalRateLimitMiddleware`, 300 so'rov/60s) chegarasidan xato chiqarib
    o'tkazib yuborgan edi -- qidiruv funksiyasining o'zida hech qanday nosozlik yo'q edi. CI
    ish oqimida shu bitta job uchun `RATE_LIMIT_MAX_REQUESTS` ko'tarildi, production'dagi
    haqiqiy himoya chegarasi o'zgarishsiz qoldi.

## 2026-08-24 -- To'liq dinamik Admin panel

- Admin panel butunlay dinamik arxitekturaga o'tkazildi: kategoriyalar, forma maydonlari,
  mahsulot narxlari (paywall pricing UI), foydalanuvchi/profil boshqaruvi -- barchasi backend'dan
  real vaqtda boshqariladi, frontend'da qattiq kodlangan qiymatlar yo'q.
- Super-admin (`umud200426@gmail.com`) uchun `ReviewGate`/`SubscriptionGate` bypass qilindi --
  admin akkaunt hech qanday tekshiruv/obuna to'sig'isiz butun platformani sinab ko'ra oladi.
- Admin orqali kreditlar/VIP-TOP promo berish (grant-credits) funksiyasidagi yashirin tranzaksiya
  izolyatsiyasi xatosi tuzilib, real production'da tekshirildi.

## 2026-08-22 -- 2026-08-24 -- Paywall / Monetizatsiya (E'lon joylashtirish to'lovi)

- E'lon joylashtirish uchun to'liq pullik model bosqichma-bosqich qurib chiqildi (Phase 1-6):
  mahsulot turlari va dinamik narxlash (`configuration`/`billing`), mock to'lov provayderi,
  `awaiting_payment` holati va avtomatik faollashtirish, kredit balansini sarflash mexanizmi,
  ommaviy `PaywallModal` UI va router ulanishi, va nihoyat admin panelidan narxlarni real vaqtda
  tahrirlash imkoniyati.
- **Ochiq qolgan band**: haqiqiy Uzum Pay adapteri hali qurilmagan -- buning uchun foydalanuvchining
  o'z Uzum Pay API hujjatlari kerak (hozircha loyihada bunday hujjat yo'q). Hozircha mock
  to'lov provayderi ishlatiladi.

## 2026-08-06 -- 2026-08-23 -- 18 ta kategoriya va dinamik filtrlar

- Butun katalog taksonomiyasi (ko'chmas mulk, yer, tovarlar, mehmonxona/hostel, biznes-katalog,
  dam olish maskanlari, xizmat ko'rsatish, landshaft dizayni, ish o'rni va h.k.) 18 ta yuqori
  darajadagi kategoriyaning barchasi uchun o'ziga xos `FormDefinition` (dinamik maydonlar) va
  real subkategoriyalar bilan to'ldirildi -- oxirgisi 2026-08-23'da yakunlandi (18/18, curl orqali
  tasdiqlangan).
- Har bir kategoriya uchun dinamik, backend-boshqaruvidagi filtr paneli qurildi (OLX-uslubidagi
  faset filtrlar), homepage joylashuvi tuzatildi.
- Yo'lda topilgan ikkita real production xatosi tuzatildi: kategoriya forma-maydon self-heal
  bug'i (9 ta kategoriya daraxti eski/orfan formaga bog'langan qolib ketgan edi) va admin
  grant-credits tranzaksiya izolyatsiyasi bug'i.

## 2026-08-19 -- 2026-08-21 -- Infratuzilma va xavfsizlik

- To'liq CI gate auditi: QG-03/03b/04/05 haqiqatda hech qachon ishlamaganligi aniqlandi (yuqori
  oqimdagi xatolar sabab bloklangan edi) -- har biri o'z real muammosi bilan tuzatildi.
- Server xavfsizlik auditi (jonli SSH orqali): UFW, fail2ban, MinIO ochiq port kabi muammolar
  topildi va tuzatildi.
- Yandex Geocoder kaliti muammosi -- Nominatim fallback orqali xarita qidiruvi ishlab turishi
  ta'minlandi (Yandex kalitning o'zi hali foydalanuvchining Yandex Kabinetida faollashtirilishini
  kutmoqda).

## 2026-08-18 -- Birinchi to'liq audit

- 18 bandli baholangan topilmalar ro'yxati tuzildi (huquqiy hujjatlar yo'qligi, PyJWT CVE'lari,
  frontend CI hech qachon ishlamasligi, footer'dagi o'lik havolalar va h.k.) -- shundan buyon
  birma-bir yopib kelinmoqda.
