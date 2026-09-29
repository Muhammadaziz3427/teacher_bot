# 📘 Teacher Bot — Ingliz tili vazifalarini AI bilan tekshirish tizimi

Offline (uyda o'qiyotgan) o'quvchilar uchun **Telegram guruh boti**: uy vazifasini
matn yoki **rasm** ko'rinishida qabul qiladi, AI orqali tekshiradi, xatolarni
tushuntiradi, davomatni yuritadi, ball/jarima tizimini boshqaradi va ota-onalar
uchun **haftalik / oylik / yillik** hisobotlarni tayyorlaydi.

---

## ✨ Nima qiladi

| Bo'lim | Tafsilot |
|---|---|
| 📝 Vazifa berish | `/homework` — mavzu, ko'nikma, tavsif, muddat, rasm. Muddat **keyingi dars vaqtiga** avtomatik qo'yiladi |
| 🤖 AI tekshiruvi | O'quvchi **matn yoki rasm** yuboradi → AI har bir mashqni alohida tekshiradi, xatoni `siz yozgansiz → to'g'risi` ko'rinishida, qoida nomi va tushuntirish bilan beradi |
| ⏰ Muddat | 24 soat va 1 soat oldin eslatma; muddat tugagach vazifa avtomatik yopiladi |
| 🚫 Jazo tizimi | Bajarilmagan vazifa = **−3 ball**, kech topshirilsa ball yarmi + **−1**; takrorlansa jazo kuchayadi (ogohlantirish → AI qo'shimcha topshiriq) |
| 🏅 Rag'bat | To'g'ri ish **+2**, qisman **+1**, ketma-ket 3 marta vaqtida topshirsa **+1 bonus** |
| 🗓 Davomat | `/attendance` — bir bosishda ✅/⏰/❌/🟡, dars qoldirsangiz **−1** |
| 📊 Hisobotlar | `/weekly`, `/monthly`, `/yearly`, `/report`, `/parent`, `/ranking`, `/export` (Excel) |
| 🌐 Til | `/language uz｜en｜bi` — guruh uchun alohida tanlanadi |
| 🎤 Ovozli javob | O'quvchi **voice** yuboradi → matnga o'giriladi → oddiy vazifa kabi tekshiriladi |
| 📤 Tasdiqlash | `CONFIRM_SUBMISSIONS=true` bo'lsa: ish saqlanadi va o'quvchi **o'zi** 📤 bosgach AI tekshiradi |
| 🔗 Ota-ona havolasi | `/link @ali` — bitta tugma: ota-ona hisobotni bir bosishda ochadi |
| 📱 Mini App | `/app` — guruh paneli (ballar, davomat, faol vazifalar) Telegram ichida |

---

## 🚀 O'rnatish

```powershell
cd c:\Users\Lenovo\Downloads\teacher_bot
pip install -r requirements.txt
copy .env.example .env      # keyin .env ni tahrirlang
python run.py
```

### 1) Bot tokeni (@BotFather)

1. @BotFather → `/newbot` → tokenni oling → `.env` faylidagi `BOT_TOKEN` ga yozing.
2. **Muhim:** `/setprivacy` → botni tanlang → **Disable**.
   Aks holda bot guruhdagi o'quvchi **rasmlarini ko'rmaydi** va tekshira olmaydi.
3. Botni guruhga qo'shing va **administrator** qiling.
4. `ADMIN_IDS` ga o'z Telegram ID ingizni yozing (botda `/id` buyrug'i bilan
   bilib olasiz). Admin va `TEACHER_IDS` dagi odamlar o'qituvchi huquqiga ega bo'ladi.

### 2) AI kaliti

`.env` faylida (bu loyihada **OpenRouter** sozlangan — tekshirilgan):

```env
OPENAI_API_KEY=sk-or-v1-....            # OpenRouter kaliti
OPENAI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openai/gpt-4o-mini             # matn uchun
AI_VISION_MODEL=openai/gpt-4o-mini      # rasmni o'qiy oladigan model bo'lishi shart
```

OpenRouter o'rniga istalgan OpenAI-mos API ishlaydi (OpenAI, DeepSeek,
Gemini proxy, yoki mahalliy `http://localhost:11434/v1` — Ollama). Rasm
tekshirilishi uchun model **vision** qo'llab-quvvatlashi kerak.

**AI sifati nazorati:**

* `score` va `verdict` har doim **bir xil bandda** — model ziddiyat bersa
  (`score: 1` + `verdict: partial`) ball verdict bandiga tuzatiladi, shuning
  uchun baho, ball va hisobotlar hech qachon kelishmay qolmaydi.
* Xatolar **major → minor** tartibda chiqadi (avval asosiy xatolar).
* Har bir tekshiruv logga **kechikish + token sarfi** bilan yoziladi,
  `/check` esa AI navbatini ko'rsatadi: `kutilmoqada · tekshirildi · xato`.
* `429/5xx` xatolarida 1s → 3s bilan 3 marta qayta urinish; `401/403`
  (kalit noto'g'ri) darhol to'xtaydi.

> **Kalit bo'lmasa ham bot ishlaydi:** ish saqlanadi, o'quvchiga oddiy
> ogohlantirishlar ko'rsatiladi va o'qituvchiga “qo'lda baholang” xabari
> yuboriladi. Bunda AI hech narsani o'ylab topmaydi.

### 3) Guruhni sozlash (birinchi 5 daqiqa)

```
/start                 ← bot guruhni ro'yxatga oladi
/language bi           ← interfeys + hisobot tili (uz | en | bi)
/timetable add Monday 14:00
/timetable add Wednesday 14:00      ← haftalik dars jadvali
/roster                ← o'quvchilar ro'yxati (/start yozganlar avtomatik qo'shiladi)
/homework              ← birinchi vazifani yaratish
/check                 ← hammasi to'g'rimi? (AI, jadval, o'quvchi soni)
```

Dars jadvali kiritilmasa, muddat `DEFAULT_DUE_HOURS` (standart 24 soat) bo'ladi —
`/check` buni eslatib turadi.

---

## 👩‍🏫 O'qituvchi buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/homework` | Yangi vazifa: mavzu → ko'nikma → tavsif → muddat → rasm. Xabarga **reply** qilib `/homework` yozsangiz, o'sha xabarning matni/rasmi olinadi |
| `/homeworks` | Faol vazifalar + har biri uchun 🔒 yopish / 🔔 eslatish / 📊 statistika |
| `/attendance` | Bugungi davomat. “✅ Hammasi keldi” → keyin kelmaganlarni bir marta bosish |
| `/timetable` | `add Monday 14:00`, `del #3`, `clear` |
| `/pending` | AI tekshira olmagan ishlar → ✍️ tugma bilan qo'lda baholash |
| `/grade 12 85 yaxshi` | Ishi №12 ni 85 ball bilan baholash |
| `/bonus @ali 2 faol qatnashdi` | Qo'lda ball qo'shish |
| `/penalty @ali 3 uyga vazifa qilmadi` | Qo'lda jarima |
| `/extra @ali 10 ta gap yozing` | Jazo sifatida qo'shimcha topshiriq |
| `/weekly` `/monthly` `/yearly` | **Hisobotlar shaxsiy chatga yuboriladi** (`/weekly group` — guruhga) |
| `/report all` | **Bir bosishda hamma o'quvchi** hisoboti → shaxsiy chat |
| `/report @ali` | Bitta o'quvchi hisoboti → shaxsiy chat |
| `/parent @ali` | “Ota-ona uchun nusxa” — forward qilish uchun tayyor |
| `/ranking` | Guruh reytingi → shaxsiy chat (`/ranking group` — guruhga) |
| `/export monthly` | 5 varaqli **Excel** → shaxsiy chat |
| `/test` | **AI testlari**: `/test new 10`, `/test schedule Wednesday 14:00`, `/test post` |
| `/topics` | Qaysi forum mavzusi qaysi ish uchun (avtomatik aniqlangan) |
| `/language uz｜en｜bi` | Tilni almashtirish |
| `/roster teacher @ali` | O'quvchini o'qituvchi qilish |
| `/check`, `/id`, `/help`, `/cancel` | Diagnostika va yordam |

---

## 🏫 Bir nechta guruh (learning center uchun)

**Bot bir nechta guruh bilan ishlaydi** — har bir guruh alohida:
o'quvchilar, davomat, vazifalar, ballar, hisobot va AI tekshiruvlari butunlay
**ajratilgan**. Siz va boshqa o'qituvchilar hammasini **shaxsiy chatdan**
boshqarasiz — guruhlarga alohida kirish shart emas.

### 📱 Shaxsiy chatda: boshqaruv paneli

`/start` yoki `/groups` bosilganda sizda guruhlar ro'yxati paydo bo'ladi.
Guruhni tanlagach, 6 bo'lim ochiladi:

| Bo'lim | Nima ko'rsatadi |
|---|---|
| 📊 **Overview** | O'quvchi soni, faol vazifalar, bugungi davomat, keyingi vazifa, yetakchi |
| 🗓 **Attendance** | Bugungi davomat jadvali — bir bosishda ✅/⏰/❌/🟡, xuddi guruhdagidek |
| 📚 **Homeworks** | Faol vazifalar: muddat, necha kishi topshirdi, nechasi baholangan |
| 👥 **Students** | Haftalik reyting (🥇🥈🥉) |
| 📑 **Reports** | Hafta / Oy / Yil hisobotlari + **Excel** yuklash |
| ⚙️ **Settings** | Til, o'qituvchilar ro'yxati, `/assign` yo'riqnomasi |

> ✅ Xavfsizlik: faqat sizga **biriktirilgan** guruhlar ko'rinadi.
> Boshqa guruhni ochishga urinsangiz: “⛔ You do not manage this group yet.”

### 👥 O'qituvchilarni biriktirish

Guruh ichida boshlovchi o'qituvchi:

```
/assign @muallim          ← u shaxsiy chatdan shu guruhni boshqaradi
/unassign @muallim        ← huquqni bekor qilish
/roster                   ← kim kimni boshqaradi
```

* **Admin** (`ADMIN_IDS` va `TEACHER_IDS`) — barcha guruhlarni ko'radi.
* **Biriktirilgan o'qituvchi** — faqat o'z guruhini ko'radi.
* Aynan shu tufayli markazda bir nechta o'qituvchi xavfsiz ishlay oladi.

### 🛠 Nega buni qilish shart edi

Eski sxemada `users` jadvalida **Telegram ID** asosiy kalit bo'lgan edi —
bu bitta odamni bitta guruhga “qulflab qo'ygan” (ikkinchi guruhga qo'shilganda
eski yozuv o'zgarib ketardi). Endi:

* `users.id` — surrogate kalit, `(chat_id, tg_id)` **unikal juftlik**
* har bir guruh uchun **alohida** ro'yxat qatorlari
* davomat, ball, vazifa `chat_id` bo'yicha ajratilgan
* **Migratsiya avtomatik** — eski `data/teacher_bot.db` bo'lsa, ishga tushirishda
  eski `id` → `tg_id` ga aylanadi, **barcha ma'lumot saqlanadi**
  (ism, rol, izohlar). Migratsiya bir marta ishlaydi va takroriy xavfsiz.

### 🧪 Tekshirish

Ko'p guruhli qism ham self-test doirasida tekshiriladi (10- va 11-bosqichlar):

* xuddi shu Telegram foydalanuvchi 2 guruhda birga mavjud
* ball/davomat/vazifalar guruhlar orasida **yotqizilmaydi**
* admin barcha guruhni, biriktirilgan o'qituvchi faqat bittasini ko'radi
* panel tugmalari **to'g'ri guruh** ID sini olib yuradi
* eski sxemadagi ma'lumot migratsiyada **yo'qolmaydi**

## 👥 A'zolar avtomatik o'quvchi bo'ladi

Bot guruhga qo'shilgandan keyin **hech kimni qo'lda qo'shish shart emas**:

| Hodisa | Nima bo'ladi |
|---|---|
| Kimdir guruhga **qo'shilsa** | darhol o'quvchi sifatida ro'yxatga olinadi + salomlashadi |
| Kimdir guruhda **yozsa** | o'quvchi sifatida ro'yxatga olinadi (allaqachon bo'lsa yangilanadi) |
| Kimdir guruhdan **chiqsa** | ma'lumoti o'chmaydi, faqat «faolsiz» bo'ladi (📉 hisobotda saqlanadi) |
| **O'qituvchi** bo'lsa | `ADMIN_IDS` / `TEACHER_IDS` yoki `/assign` orqali — o'quvchi ro'yxatiga **tushmaydi** |

> ℹ️ Telegram Bot API guruh a'zolari ro'yxatini bermaydi, shuning uchun bot
> a'zolarni **qo'shilish hodisasi** va **xabarlari** orqali o'zi yig'adi.
> Qo'shilish hodisasini olish uchun botni guruhda **administrator** qiling.

---

## 🔒 Hisobotlar faqat sizga (o'qituvchiga)

O'quvchi hisobotlari guruhga **hech qachon** chiqmaydi — ular **shaxsiy
chatingizga** keladi:

```
/report @ali          → @ali hisoboti shaxsiy chatga
/report all           → HAMMA o'quvchi hisoboti birdan (haftalik + oylik)
/weekly               → butun guruh xulosasi + har bir o'quvchi hisoboti → shaxsiy chat
/parent @ali          → ota-onaga forward qilish uchun tayyor nusxa → shaxsiy chat
/ranking              → reyting → shaxsiy chat
/export               → Excel fayl → shaxsiy chat
```

* **Vaqtingizni tejaydi:** `/report all` bilan bir marta bosib butun guruh
  hisobotini olasiz — har bir o'quvchini alohida terish shart emas.
* Guruhga **jamoa xulosasi** chiqishi kerak bo'lsa: `/weekly group` yoki
  `/ranking group` deb yozing (o'sha payt «group» so'zi qo'shiladi).
* O'quvchilar o'z natijasini `/mystats` bilan ko'radi.

> ⚠️ Bir marta botni shaxsiy chatda `/start` qilib qo'ying — aks holda bot
> hisobotni yubora olmaydi va guruhda «/start bosing» deb eslatadi.

---

## 🧵 Mavzularga bo'lingan guruhlar (forum)

Guruh **General · Homework · Test · Announcements** kabi mavzularga bo'lingan
bo'lsa, bot **hech narsa so'ramasdan o'zi aniqlaydi** — ID yozish shart emas:

| Siz nima qilasiz | Bot nima eslab qoladi |
|---|---|
| **Homework** mavzusida `/homework` yuborasiz | shu mavzu = 📚 Homework (keyingi vazifalar ham shu yerga) |
| **Test** mavzusida `/test` yuborasiz | shu mavzu = 📝 Test (avtomatik testlar ham shu yerga) |
| **Announcements** mavzusida `/weekly` yuborasiz | shu mavzu = 📢 Announcements |
| Birinchi yozgan mavzuingiz | 🏠 General (standart) |

* O'quvchi vazifasiga bot **o'sha mavzuda** javob beradi (xabar thread'ini
  Telegram o'zi saqlaydi) — mavzular **aralashib ketmaydi**.
* `/topics` — qaysi mavzu nima uchun ishlatilayotganini ko'rsatadi.
* Mavzu hali aniqlanmagan bo'lsa, bot General'ga yozadi va `/test` da
  «Test mavzusida yuboring» deb maslahat beradi.
* Oddiy (mavzusiz) guruhlarda ham hammasi avvalgidek ishlaydi.

---

## 📝 Testlar — bot o'zi tuzadi, o'zi joylaydi

**AI o'tilgan darslar asosida test tuzadi** — mavzuni aytish shart emas, bot
guruhga berilgan vazifalar (darslar) ro'yxatidan mavzularni o'zi aniqlaydi:

```
/test new 10                    → AI o'tilgan darslardan 10 savol tuzadi
/test manual                    → savollarni o'zingiz yozasiz
/test post                      → eng yangi testni hozir yuborish
/test schedule Wednesday 14:00  → har chorshanba 14:00 da AVTOMATIK test
/test schedule Friday 10:00 15  → 15 savolli haftalik test
/test off                       → avtomatik testni o'chirish
/test list                      → testlar ro'yxati
```

**Avtomatik test** (`/test schedule`) — belgilangan kun/vaqtda bot:
1. O'tilgan darslar ro'yxatini yig'adi
2. AI'dan shu mavzular bo'yicha savollar so'raydi
3. Savollarni **Test mavzusiga** A/B/C/D tugmalari bilan joylaydi
4. Belgilangan vaqt (standart 30 daq.) ichida o'quvchilar javob beradi
5. Vaqt tugagach: **natijalarni guruhga** e'lon qiladi va **har bir o'quvchiga
   shaxsiy ball** yuboradi

O'quvchi tugma bosganda javob faqat **o'ziga** ko'rinadi (✅/❌ + to'g'ri javob
+ izoh) — guruh spam bo'lmaydi. Javoblar bir marta qabul qilinadi (qayta
bosish hisoblanmaydi).

**Qo'lda savol yozish formati:**

```
I ___ never been to London.
a) has
b) have
*c) had
d) having
```

To'g'ri javob oldiga `*` qo'yiladi. Har bir savolni alohida xabar qilib
yuboring, tugatgach `/done`.

---

## 🧑‍🏫 Boshqa o'qituvchilar (ma'lumot aralashmaydi)

Markazda bir nechta o'qituvchi ishlasa ham hech narsa aralashmaydi:

| Kim | Nimani ko'radi |
|---|---|
| **Admin** (`ADMIN_IDS`) | barcha guruhlarni |
| **Biriktirilgan o'qituvchi** (`/assign @user`) | faqat o'zi biriktirilgan guruhni |
| **O'quvchi** | faqat o'z natijalarini (`/mystats`) |

* Har bir guruhning **o'quvchilari, davomati, vazifalari, testlari, ballari va
  hisobotlari alohida** saqlanadi (`chat_id` bo'yicha).
* Bir o'qituvchi bir necha guruhga biriktirilishi mumkin.
* Begona guruhni ochishga urinsa: `⛔ You do not manage this group yet.`
* Bir o'quvchi bir necha guruhda bo'lsa ham, har guruhdagi natijasi alohida.

## 🎓 O'quvchi tomonidan topshirish

1. Vazifa xabariga **reply** qilib ishini yuboradi (matn yoki rasm) — eng aniq usul.
2. Yoki oddiy rasm/matn yuboradi — bot eng oxirgi faol vazifaga bog'laydi.
3. Yoki `/submit 3` → keyin ishni yuboradi.

Bot darhol javob beradi:

```
📝 Homework #12 checked
Student: Aziza Karimova
Score: 78/100  Grade: C
Result: partially correct ⚠️

💬 Summary
Good attempt. Watch the 3rd person -s and articles.

📋 Exercise by exercise
• Ex. 1a — ✅ correct
• Ex. 1b — ❌ wrong — Missing -s

❌ Mistakes and how to fix them
1. you wrote: He go to school
   ✅ correct: He goes to school
   🏷 Verb tenses · rule: Present Simple: 3rd person -s
   💬 he/she/it takes verb + s.

💡 Tips for next time
• Write 5 sentences with he/she/it
🎯 Topic mastery
• Present Simple — needs work
🏅 Points earned: 1.0
```

O'qituvchi har bir tekshiruv ostidagi **✅ Qabul qilish / ⚠️ Qisman / ❌ Rad etish**
tugmalari bilan AI bahosini o'zgartira oladi — baho va ballar qayta hisoblanadi.

Shaxsiy buyruqlar: `/myhomework`, `/mypoints`, `/myattendance`, `/mystats`,
`/mytasks` — guruhda ham, botning shaxsiy chatida ham ishlaydi.

---

## ⏰ Muddat qanday hisoblanadi

```
Vazifa berildi (dushanba 16:00)
        ↓
Muddat = keyingi dars boshlanishi (chorshanba 14:00)   ← /timetable asosida
        ↓
24 soat oldin → 🔔 eslatma
 1 soat oldin → 🔔 eslatma
        ↓
Muddat tugadi → vazifa 🔒 yopiladi, topshirmaganlar ro'yxati guruhga chiqadi
        ↓
Jarima + keyingi bosqichga o'tish
```

Muddatni qo'lda ham berish mumkin: `ertaga 18:00`, `juma 14:30`, `25.12 10:00`,
`in 3 hours`, yoki `-` (keyingi dars).

---

## 🏅 Ball va jazo tizimi

| Holat | Ball | Izoh |
|---|---|---|
| To'g'ri (≥80) | **+2** | `POINT_FULL` |
| Qisman (50–79) | **+1** | `POINT_PARTIAL` |
| Noto'g'ri (<50) | 0 | `POINT_WRONG` |
| Kech topshirilgan | **−1** + ball yarmi | `POINT_LATE`, `LATE_HALVES_SCORE` |
| Umuman qilinmagan | **−3** | `POINT_MISSING` |
| Darsga kelmagan | **−1** | `POINT_ABSENT` |
| Darsga kechikkan | **−0.5** | `POINT_LATE_ATTENDANCE` |
| 3 marta ketma-ket vaqtida | **+1 bonus** | 🔥 rag'bat |
| 🥇🥈🥉 hafta/guruh reytingi | — | motivatsiya |

**Jazoning kuchayishi (avtomatik):**

1. **1-uyga vazifa qilinmasa** → guruhda ogohlantirish: “bu sizning 1-bajarilmagan vazifangiz”.
2. **2-marta** → bot **AI yordamida qo'shimcha topshiriq** beradi
   (masalan “Write 10 sentences using 'Present Simple' in your notebook…”),
   topshirish muddati 48 soat, `/mytasks` da ko'rinadi.
3. **3-marta va undan keyin** → o'sha tartib davom etadi va hisobotda avtomatik
   **⚠️ Need support** ro'yxatiga tushadi — ota-onaga alohida e'tibor uchun.

Barcha ballar `point_events` jadvalida saqlanadi (`event_key` bilan — bir voqea
ikki marta yozilmaydi), shuning uchun har bir hisobot tekshiriladigan.

Barcha qiymatlar `.env` orqali o'zgartiriladi: `POINT_FULL`, `POINT_PARTIAL`,
`POINT_LATE`, `POINT_MISSING`, `POINT_ABSENT`, `POINT_LATE_ATTENDANCE`.

---

## 📊 Hisobotlar

**Haftalik** (`/weekly`) va har bir o'quvchi uchun (`/report @ali`):

* 🗓 Davomat foizi, darslar soni
* 📚 Nechta vazifa berilgan / bajarilgan / vaqtida / kech
* 🚫 Bajarilmaganlar va jarima ballari
* 🏅 Davr uchun ball, 🏆 guruhdagi o'rin
* 📈 Oldingi davrga nisbatan o'sish/pasayish
* 🔁 **Eng ko'p uchraydigan xatolar** (kategoriya bo'yicha) va
  ✍️ **aniq misollar**: `He go to school → He goes to school`
* 🌟 Kuchli tomonlar, 🎯 keyingi mashqlar
* 👨‍👩‍👦 **Ota-onaga izoh** — avtomatik tayyorlanadi

**Oylik / Yillik** — tendensiya, CEFR darajasi bahosi, yillik “sertifikat” xulosasi.

**Excel** (`/export`) — 5 varaq: `Summary`, `Attendance`, `Homework`,
`Mistakes`, `Points`.

Har hafta yakshanba 20:00 da guruhga avtomatik haftalik hisobot yuboriladi
(`AUTO_WEEKLY_REPORT`, `AUTO_WEEKLY_DAY`, `AUTO_WEEKLY_HOUR`).

---

## 🌐 Til rejimi (`/language`)

Har bir guruh uchun alohida tanlanadi:

| Rejim | Interfeys | AI tushuntirishi | Hisobot |
|---|---|---|---|
| `en` | Inglizcha | Inglizcha | Inglizcha |
| `uz` | O'zbekcha | Tuzatish inglizcha, **izoh o'zbekcha** | O'zbekcha |
| `bi` (standart) | Inglizcha + o'zbekcha | Inglizcha tuzatish + o'zbekcha izoh | Ikki tilli |

> **Muhim qoida:** *tuzatishning o'zi har doim inglizcha* bo'ladi
> (`He go` → `He goes`), chunki o'rganilayotgan til — ingliz tili.
> Faqat **izoh, maslahat, interfeys va hisobot** tarjima qilinadi.

---

## 🗂 Loyiha tuzilishi

```
teacher_bot/
├── run.py                     ← ishga tushirish:  python run.py
├── requirements.txt
├── requirements-dev.txt       ← pytest (unit testlar)
├── pytest.ini                 ← test sozlamalari
├── .env.example               ← andoza (nusxa olib .env qiling)
├── README.md
├── tests/                     ← unit testlar (pytest)
│   ├── conftest.py            ← alohida test bazasi (haqiqiy DB ga tegmaydi)
│   ├── test_utils.py          ← muddat/jadval parseri
│   ├── test_scoring.py        ← ball va jarima qoidalari
│   ├── test_ai_checker.py     ← AI natijasini normallashtirish, retry
│   ├── test_i18n.py           ← 3 til to'liqligi, grade chegaralari
│   └── test_submissions_db.py ← topshirish tsikli (haqiqiy SQLite)
├── app/
│   ├── config.py              ← .env → sozlamalar, ball qoidalari
│   ├── logging_setup.py       ← konsol + logs/bot.log (rotating)
│   ├── i18n.py                ← uz / en / bi matnlar katalogi
│   ├── utils.py               ← sana, "ertaga 18:00" kabi muddatlarni o'qish
│   ├── models.py               ← jadvalar: users, homeworks, submissions,
│   │                            attendance, point_events, lesson_slots, reports
│   ├── db.py                  ← async engine + sessiya
│   ├── ai_checker.py          ← AI tekshiruvi (matn + rasm/vision), JSON natija
│   ├── ai_worker.py           ← AI tekshiruvi fonda: navbat, 5 ta parallel limit
│   ├── stt.py                 ← ovozli javobni matnga o'girish (whisper)
│   ├── deeplink.py            ← ota-ona havolasi: parent_<chat>_<student>
│   ├── miniapp.py             ← panel uchun read-only HTTP + token himoyasi
│   ├── keyboards.py           ← inline tugmalar
│   ├── middlewares.py         ← har bir xabar uchun DB sessiya + til + rol
│   ├── scheduler.py           ← eslatmalar, muddat yopish, haftalik hisobot
│   ├── states.py              ← FSM bosqichlari
│   ├── services/
│   │   ├── students.py        ← ro'yxat, rollar, o'quvchini topish
│   │   ├── schedule.py        ← haftalik jadval → keyingi dars
│   │   ├── homework.py        ← vazifalar
│   │   ├── submissions.py     ← topshiriqlar va AI natijalari
│   │   ├── attendance.py      ← davomat
│   │   ├── scoring.py         ← ball, jarima, bonus, jazo bosqichlari
│   │   ├── reports.py         ← haftalik/oylik/yillik hisobot matni
│   │   ├── exporter.py        ← Excel (5 varaq)
│   │   └── notifier.py        ← barcha xabarlarni chiroyli chiqarish
│   └── handlers/
│       ├── common.py          ← /start, /help, /language, /check, /roster
│       ├── teacher.py         ← vazifa ustasi, davomat, baholash, ball
│       ├── student.py         ← topshirish + AI tekshiruvi + shaxsiy statistika
│       └── reports.py         ← hisobot buyruqlari va tugmalari
└── scripts/
    └── selftest.py            ← offline to'liq test (token va AI kalitisiz)
```

---

## ✅ O'z-o'zini tekshirish

Botni ishga tushirishdan oldin ham hamma mantiqni sinab ko'rish mumkin —
Telegram tokeni ham, AI kaliti ham kerak emas:

```powershell
python scripts/selftest.py
```

Skript guruh, o'quvchilar, dars jadvali, vazifa, AI bahosi (test uchun
deterministik), ball/jarima, jazo bosqichlari, davomat, 3 tildagi hisobotlar va
Excel faylini yaratib tekshiradi va oxirida:

```
OK  All checks passed — the whole pipeline works offline.
```

### 🧪 Unit testlar (pytest)

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

50 ta tez test: muddat parseri, ball qoidalari, AI normallashtirish
(score↔verdict, severity, retry), 3 tilning to'liqligi va **haqiqiy SQLite**
da topshirish tsikli (qayta yuborish → yangi attempt). Testlar alohida
`data/pytest.db` foydalanadi — ishlab turgan bazaga **tegmaydi**.

Xatolarni ko'rish uchun: `python -m pytest -v` yoki bitta fayl:
`python -m pytest tests/test_scoring.py -v`.

CI (GitHub Actions) `.github/workflows/ci.yml` da har push'da `pytest` +
`selftest.py` ni ishga tushiradi.

### 📜 Loglar

`python run.py` ishga tushganda konsolga va **`logs/bot.log`** ga yozadi
(2 MB × 4, avtomatik siqiladi). Har bir AI chaqiruvi kechikish va token
sarfi bilan yoziladi, navbatdagi qayta urinishlar va xatolar ham logda:

```
2026-09-29 14:03:11 | INFO    | app.ai_checker | AI ok model=openai/gpt-4o-mini 6.2s prompt=812 completion=244 attempt=1
2026-09-29 14:03:12 | WARNING | app.ai_worker   | AI unavailable for submission 7: RateLimitError ...
```

### 🎤 Ovoz, 📤 tasdiqlash, 🔗 havola, 📱 panel (Blok 4)

| Funksiya | Qanday ishlaydi | `.env` |
|---|---|---|
| **Ovozli javob** | O'quvchi voice yuboradi → `whisper` matnga o'giradi → matn ko'rinishida tekshiriladi. Rasmdagi/yozuvdagi savol bilan birga yuborilsa ikkalasi qo'shiladi. Ovoz ishlamasa o'quvchi "yozib yuboring" degan xabar oladi (hech narsa yo'qolmaydi) | `STT_MODEL`, `STT_API_KEY`, `STT_BASE_URL` |
| **Tasdiqlash** | `true` bo'lsa: ish `confirm` holatida saqlanadi va faqat o'quvchi **📤 Topshirdim** bosgach AI tekshiruvi boshlanadi. **✏️ Hali emas** bosilsa yozuv o'chiriladi. Muddat tugasa parkdagi ish **avtomatik topshirilgan** hisoblanadi (jarima yo'q). Tugma faqat ish egasiga ishlaydi | `CONFIRM_SUBMISSIONS` |
| **Ota-ona havolasi** | `/link @ali` → `t.me/<bot>?start=parent_<chat>_<student>` tugmasi. Ota-ona bosganda bot guruh o'qituvchisiga hisobotni ko'rsatadi. Begona odam uchun havola **ishlamaydi** | `BOT_USERNAME` |
| **Mini App panel** | `/app` → har bir guruh uchun tugma: haftalik ball, davomat %, topshirilganlar, faol vazifalar. Ma'lumot read-only va `MINIAPP_TOKEN` bilan himoyalangan | `MINIAPP_ENABLED`, `MINIAPP_TOKEN`, `MINIAPP_PUBLIC_URL` |

**Mini App'ni yoqish** (Telegram faqat `https://` manzilni ochadi):

```powershell
# 1) .env da: MINIAPP_ENABLED=true, MINIAPP_TOKEN=<uzun tasodifiy matn>
# 2) tashqariga https bilan chiqaring (reverse proxy yoki tunnel), masalan:
npx localtunnel --port 8080
# 3) .env da: MINIAPP_PUBLIC_URL=https://<tunnel-manzil>
# 4) botda /app → tugma paydo bo'ladi
```

Panelga brauzerdan ham kirish mumkin: `http://127.0.0.1:8080/?chat=<guruh_id>&token=<MINIAPP_TOKEN>`
(`/api/summary` esa token bo'lmasa `401` qaytaradi).

---

## ⚙️ Ishonchlilik: AI navbati va qayta urinishlar

O'quvchi xabar yuborganidan keyin bot **darhol javob beradi** — AI tekshiruvi
orqa fonda (`app/ai_worker.py`) bajariladi:

```
ish saqlanadi → "📥 qabul qilindi" → navbat → AI (en ko'pi 5 ta parallel) →
ball → guruhga tahlil
```

* **Qisqa DB tranzaksiyalar** — AI 90 soniya o'ylasa ham SQLite qulflanmaydi
  (shu bilan birga `WAL` rejimi yoqilgan: scheduler va yozuv parallel ishlaydi).
* **Navbat** — bir vaqtda 5 ta tekshiruv, navbatda 100 tagacha ish. Navbat
  to'lsa o'quvchiga “qayta yuboring” deyiladi, hech narsa yo'qolmaydi.
* **Qayta urinish** — `429/5xx/tarmoq` xatolarida 1s → 3s kechikish bilan
  3 marta urinish. `401/403` (kalit noto'g'ri) esa **darhol** to'xtaydi.
* **Xavfsizlik to'ri** — AI yoki Telegram ishlamasa ish `pending` holatida
  qoladi va `/pending` da ko'rinadi; o'qituvchi qo'lda baholaydi.
* **Kechik baholash ustuvorligi** — navbatda turgan paytda o'qituvchi qo'lda
  baholasa, eski AI vazifasi bekor qilinadi (qayta yuborilsa yangi urinish
  bajariladi).

---

## 🛠 Ko'p uchraydigan muammolar

| Muammo | Yechim |
|---|---|
| **Rasm tekshirilmayapti** | @BotFather → `/setprivacy` → **Disable**; botni guruhda **admin** qiling; `/check` bilan tekshiring |
| “AI tekshiruvi: O'CHIQ” | `.env` da `OPENAI_API_KEY` bo'sh. Kalit qo'yilmasa bot ishlaydi, lekin qo'lda baholash kerak bo'ladi |
| AI xato bersa | Ish `pending` holatda saqlanadi, `/pending` da ko'rinadi — hech narsa yo'qolmaydi |
| Muddat noto'g'ri | `/timetable` to'ldirilganini tekshiring; vaqt zonasi `TZ` (.env), standart `Asia/Tashkent` |
| O'quvchi ro'yxatda yo'q | U guruhda `/start` yozishi kerak, yoki `/roster` bilan tekshiring |
| Ballarni qayta hisoblash | `/grade <id> <ball>` yoki tekshiruv ostidagi ✅/⚠️/❌ tugmalari |

---

## ▶️ Doimiy ishlatish (24/7)

To'liq qo'llanma: **[`deploy/README.md`](deploy/README.md)** — GitHub Actions
nega 24/7 uchun yaramaydi, Oracle Cloud Always Free'da bepul VM, Docker,
systemd, zaxira va kuzatish bo'yicha qadam-baqadam ko'rsatmalar.

Qisqacha eng ishonchli bepul variant — **Oracle Cloud Always Free VM + systemd**
(`deploy/teacher-bot.service`), Docker ishlatsangiz: `docker compose up -d`
(`restart: unless-stopped` tufayli bot o'zi qayta ko'tariladi).

**Windows** — Task Scheduler da "At startup" vazifasi:

```powershell
python c:\Users\Lenovo\Downloads\teacher_bot\run.py
```

**Linux (systemd)**

```ini
[Unit]
Description=Teacher Bot
After=network.target

[Service]
WorkingDirectory=/opt/teacher_bot
ExecStart=/usr/bin/python3 run.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Ma'lumotlar `data/teacher_bot.db` (SQLite) faylida saqlanadi — zaxira nusxa
olish uchun shu faylni ko'chirib qo'yish kifoya.


