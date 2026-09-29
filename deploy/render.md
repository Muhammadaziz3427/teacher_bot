# 🆓 Render'da bepul ishga tushirish (qadam-baqadam)

> Bu qo'llanma **Render Free** reja uchun. Render hujjatlari asosidagi aniq
> cheklovlar (2026-yil holati):
>
> | Cheklov | Ta'siri |
> |---|---|
> | Faqat **Web Service** bepul (**Background Worker pullik**) | Bot `python run.py` bilan Web Service sifatida ishlaydi + `/healthz` endpointi |
> | **15 daqiqa** trafik bo'lmasa → **spin-down** | 15 daqiqada bir marta tashqaridan ping **shart** |
> | Spin-down / restart / deploy bo'lsa **disk yo'qoladi** | `data/*.db` GitHub'ga doimiy **sinxronlanadi** (pastda) |
> | 0.1 CPU / 512 MB | Bot ~100–150 MB RAM oladi — yetarli, biroz sekin |
> | Free Postgres **30 kundan keyin o'chiriladi** | ❌ ishlatilmaydi |

Render **bevosita GitHub bilan ishlaydi**: `render.yaml` (blueprint) va
`.github/workflows/ci.yml` (har push'da test) tayyor.

---

## 0) Qoida: baza hech qayerda yo'qolmasligi kerak

Render free'da **doimiy disk yo'q** — shuning uchun baza GitHub'ning
**PRIVATE** reposida nusxalanadi:

```
boshlang'ich            ish payti              qayta ishga tushganda
────────────────        ─────────────────       ─────────────────────────
 GitHub zip ──pull──▶  data/teacher_bot.db  ──▶ GitHub zip (har 5 daqiqada)
```

Sekinlik: cheklovlarsiz ham bir muammo yo'q — nusxa 5 daqiqada bir
saqlanadi (faqat baza **o'zgargan** bo'lsa; jimlikda API chaqirmaydi),
SIGTERM'da esa **majburiy saqlash** bajariladi.

---

## 1) Private data repo + token yaratish

1. GitHub → **New repository** → `teacher_bot_data` → 📕 **Private** → Create.
   > ⚠️ Asosiy repo **public** — `teacher_bot_data` **shart private** bo'lishi
   > kerak (talabalar ismlari, ballar, ota-ona kontaktlari).
2. GitHub → Settings → **Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**
   - Repository access: **Only select repositories** → `teacher_bot_data`
   - Permissions: **Contents → Read and write**
   - Expiry: qachon xohlasangiz (yuqori — yiliga qayta yozasiz)
3. Tokenni nusxalang — u **hech qayerga commit qilinmaydi**.

## 2) Render'da blueprint yaratish

1. <https://dashboard.render.com> → **New → Blueprint**
2. GitHub'ga ulaning → `Muhammadaziz3427/teacher_bot` ni tanlang
   (`render.yaml` avtomatik aniqlanadi → **Apply**)
3. **Environment** bo'limidagi `sync: false` qiymatlarni to'ldiring:

| O'zgaruvchi | Qanday qiymat |
|---|---|
| `BOT_TOKEN` | @BotFather'dan olingan token |
| `OPENAI_API_KEY` | OpenRouter kaliti (`sk-or-v1-…`) |
| `ADMIN_IDS` | Sizning Telegram ID ingiz (`/id` bilan) |
| `TEACHER_IDS` | O'qituvchilar IDlari (vergul bilan) |
| `DB_SYNC_REPO` | `Muhammadaziz3427/teacher_bot_data` |
| `DB_SYNC_TOKEN` | 1-qadamdagi PAT |

> `.env` faylini Render'ga yuklash shart **emas** — hammasi shu yerda.
> Foydalaniladigan qo'shimcha qiymatlar `render.yaml` da yozilgan
> (`MINIAPP_TOKEN` Render o'zi yaratadi — uni saqlab qo'ying).

4. **Apply Blueprint** → Build va Watch (birinchi deploy ~1–2 daqiqa).

## 3) Tekshirish

- **Logs**: `Started @… · v… · AI ON` va `DB sync: database restored from …`
  (birinchi marta `restored` bo'lmasligi mumkin — repo hali bo'sh)
- https://**sizning-manzilingiz**.onrender.com/**healthz** → `{"status":"ok"}`
- Grudda: `/check` → AI + navbat ko'rinadi
- Baza saqlanganini tekshirish: `teacher_bot_data` reposida
  `teacher_bot.db.zip` paydo bo'lishi kerak

---

## 4) ✅ Keep-alive: 15 daqiqalik spin-down'ni yengish (MUVAFFAQIYAT UCHUN SHART)

Render free **15 daqiqa HTTP trafik kelmasa** xizmatni uxlatadi va
**barcha lokal fayllarni o'chiradi**. Bot esa **HTTP trafik yubormaydi**
(faqat Telegram tomoniga so'rov qiladi) → demak, **tashqi ping majburiy**.

1. <https://uptimerobot.com> → bepul ro'yxatdan o'ting (bepul: 50 monitor,
   **5 daqiqada bir** so'rov)
2. **Add New Monitor** → Type: **HTTP(s)** → Friendly name: `teacher-bot`
3. URL: `https://<sizning-manzilingiz>.onrender.com/healthz`
4. Monitoring Interval: **5 minutes** → Create

> 5 daqiqalik ping = hech qachon spin-down bo'lmaydi → disk ham,
> bot ham to'xtovsiz ishlaydi. Bu Render uchun odatiy (va noqonuniy
> emas) usul.

**Muhim:** faqat Render'ning o'z health check'i **yetarli emas** — u
tashqaridan ping emas. UptimeRobot (yoki dosta.zone, BetterStack) **kerak**.

---

## 5) 📱 Mini App panelini Render'da ishlatish (bonus)

Render **https** manzil beradi, ya'ni Telegram'ning asosiy talabi bajarilgan:

```
MINIAPP_ENABLED=true   (render.yaml da allaqachon bor)
MINIAPP_TOKEN=…        (Render generateValue bilan yaratadi)
MINIAPP_PUBLIC_URL     (bosh qoldirilsa — Render o'z manzilini beradi,
                        /app avtomatik ko'radi)
```

Render dashboard'ida **Logs → Copy URL** qilib `MINIAPP_PUBLIC_URL` ga
qo'shsangiz, `/app` buyrug'i https tugma beradi. UptimeRobot ping'i
panelni ham uxlashdan saqlaydi.

---

## 6) 🔍 Kuzatish va muammolar

| Muammo | Sabab → Yechim |
|---|---|
| **Deploy failed: health check** | `/healthz` javob bermayapti → Logs'da xatoni ko'ring (`PORT` ni almashtirmang, Render o'zi beradi) |
| `Conflict: terminated by other getUpdates request` | Botning **ikkinchi nusxasi** ishlayapti (masalan uy kompyuterida) → eskisini to'xtating |
| `DB sync pull failed and there is no local database` | PAT yoki `DB_SYNC_REPO` noto'g'ri → xavfsiz rejim: baza buzilmaydi, tokenni tekshiring |
| Spin-down → baza yo'qolayotgan bo'lsa | `DB_SYNC_REPO/TOKEN` sozlanmagan → Logs'da `DB sync:` xabari bormi? |
| Bot sekin ishlayapti | 0.1 CPU — tabiiy. Sizga tezroq kerak bo'lsa `0.5c-512mb` ($7) yoki `1c-2g` ($25) |
| Telegram'da uzilish his qilinadi | UptimeRobot monitori o'chib qolganini tekshiring (pulsiz akkauntlar passivlashishi mumkin) |
| Xatolar | Logs → Filter `ERROR` · guruhda `/check` |

Kuzatish uchun:
- Render → **Logs** (jonli) va **Metrics** (CPU/RAM)
- Telegram guruh → **`/check`** (AI holati, navbat, muddat)
- Baza holati: kompyuteringizda `python -m app.db_sync status`

---

## 7) 💾 Qo'shimcha zaxira

GitHub'dagi zip — asosiy zaxira. Uni qo'lda ham olish mumkin:

```bash
python -m app.db_sync pull        # GitHub'dan yuklab olish
python -m app.db_sync push        # darhol saqlash
python scripts/backup.py --keep 14    # alohida zip arxivi
```

Hammasi qayta tiklanadi: **GitHub zip = butun sinf tarixi.**

---

## 8) 🆚 Nima uchun "pullik ishonchli" bo'lmasa ham yaxshi ishlaydi

Agar bir necha nafar o'quvchi bo'lsa, Render Free + keep-alive + DB sync
yetarli. Lekin **asosiy sinf uchun** javobgarlikni oshirmaslik uchun:

| Kerakli narsa | Render'da yechim |
|---|---|
| 0.1 CPU (sekin) | `$7`/oy **Starter** (0.5 CPU) |
| Disk yo'q (sync bilan xavfsiz, lekin 5 daqiqalik yo'qotish) | Disk ($$/oy) yoki shu GitHub sync — **bepul** |
| 15 daqiqalik keep-alive ping | Starter'da ham kerak (faqat VM'da kerak emas) |
| To'xtovsizlik darajasi ~99% | **Background Worker** (pullik emas) — lekin u ham 24/7 polling uchun eng toza yo'l |

Ko'p guruh/jiddiy ish uchun avvalgi qo'llanmaga qarang:
[`deploy/README.md`](README.md) (Oracle Cloud — muddatsiz bepul, diskli,
hech qanday ping'siz).
