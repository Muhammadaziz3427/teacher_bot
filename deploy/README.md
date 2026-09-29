# 🖥 24/7 bepul ishga tushirish (uzilishlarsiz)

Bot **long polling** rejimida ishlaydi, ya'ni to'xtovsiz ishlab turishi kerak.
Quyida bepul variantlar — GitHub Actions'dan boshlab, eng ishonchlisigacha.

---

## ❓ "GitHub'ning o'zida qilsa bo'ladimi?"

**Qisqa javob: texnik jihatdan mumkin, lekin 24/7 uchun YARAMAYDI.**

GitHub Actions — bu CI (test) uchun xizmat, server emas. Aniq cheklovlar:

| Cheklov | Natijasi |
|---|---|
| Bitta job **maksimum 6 soat** | Bot har 6 soatda qayta ishga tushadi, o'rtada **5–25 daqiqa uzilish** bo'ladi |
| Cron **5 daqiqadan tez** ishlamaydi va kechikadi | "aniq vaqtda" eslatma, muddat yopish, avtomatik testlar **kechikadi** |
| Runner'da **doimiy disk yo'q** | Har run'da `data/teacher_bot.db` **yo'qoladi** → barcha ballar, davomat, vazifalar, hisobotlar o'chib ketadi |
| Repo'ga 60 kun push qilmasangiz | GitHub cron'ni **o'zi o'chirib qo'yadi** |
| Bepul daqiqalar | Public repo'da bepul, private'da oylik limit bor |

Ya'ni o'quvchilar ballari har 6 soatda nolga tushadigan bot — bu sinf uchun
yaramaydi. Shu sababli **GitHub faqat CI (test) uchun** qoldirilgan:
`.github/workflows/ci.yml` har push'da pytest + selftest ishlatadi.

> Tajriba qilishni istasangiz `deploy/actions-keepalive.yml.example` faylida
> 6 soatlik "keepalive" varianti bor — u ham bazani saqlab qololmaydi,
> faqat sinov uchun.

---

## 🏆 Variantlar taqqoslash

| Variant | Narxi | 24/7 | Baza saqlanadimi | Kim uchun |
|---|---|---|---|---|
| **Oracle Cloud Always Free** (ARM) | **Bepul, muddatsiz** | ✅ | ✅ | 🥇 Eng yaxshi tanlov (karta talab qilinadi, pul yechilmaydi) |
| Uy kompyuteri + Task Scheduler | Bepul | ⚠️ kompyuter yonib turishi kerak | ✅ | Kichik sinf, kompyuter doim yoniq bo'lsa |
| Raspberry Pi / eski telefon (Termux) | Bepul | ✅ | ✅ | Elektr sarfi past, internet uzilmaydigan joy |
| Fly.io | Bepul limit bor | ⚠️ cheklovli | ✅ (volume) | Karta kerak, limit tez tugaydi |
| Render / Koyeb free | Bepul | ❌ uxlab qoladi | ✅ | Faqat sinov |
| PythonAnywhere free | Bepul | ❌ | ⚠️ | Whitelist cheklovlari bor |
| GitHub Actions | Bepul | ❌ 6 soat | ❌ | Faqat CI/test |

**Xulosa:** doimiy ishlashi va baza saqlanishi kerak bo'lgani uchun
**Oracle Cloud Always Free** yoki **uy kompyuteri** ishlatiladi.

---

## 🥇 Oracle Cloud Always Free — qadam-baqadam

> Karta tekshiruv uchun kerak, lekin "Always Free" resurslardan **pul yechilmaydi**.

### 1) Mashina yaratish
1. <https://cloud.oracle.com> → ro'yxatdan o'tish (region: Frankfurt / Amsterdam — O'zbekistonga yaqin).
2. **Compute → Instances → Create instance**
   - Image: **Ubuntu 22.04** (yoki 24.04)
   - Shape: **VM.Standard.A1.Flex** (Ampere ARM) — 1–2 OCPU / 6–12 GB RAM (`Always Free` belgisi bo'lishi shart)
   - **Add SSH key** → o'z ochiq kalitingizni yuklang (`~/.ssh/id_ed25519.pub`)
3. Public IP manzilni yozib oling.

### 2) Serverga kirish va tayyorlash
```bash
ssh ubuntu@<SERVER_IP>

sudo apt update && sudo apt install -y python3-venv git sqlite3
git clone git@github.com:Muhammadaziz3427/teacher_bot.git /opt/teacher_bot
# (yoki HTTPS bilan: git clone https://github.com/Muhammadaziz3427/teacher_bot.git /opt/teacher_bot)
cd /opt/teacher_bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

### 3) `.env` (maxfiy fayl — repo'ga tushmaydi)
```bash
cp .env.example .env
nano .env            # BOT_TOKEN, OPENAI_API_KEY, ADMIN_IDS ni to'ldiring
chmod 600 .env       # faqat siz o'qiy olasiz
```

---

## 💾 Zaxira nusxa (majburiy maslahat)

Butun sinf tarixi bitta `data/teacher_bot.db` faylida. Uni yo'qotmaslik uchun:

```bash
cd /opt/teacher_bot
.venv/bin/python scripts/backup.py --keep 30        # backups/teacher_bot_<sana>.zip
crontab -e
# har kuni 03:30 da avtomatik zaxira:
30 3 * * * cd /opt/teacher_bot && .venv/bin/python scripts/backup.py --keep 30
```

Skript bazani **ishlab turganda ham xavfsiz** nusxalaydi (`sqlite backup API`)
va Excel hisobotlarini ham arxivga qo'shadi. Arxivlarni boshqa joyga
(masalan Google Drive yoki `scp`) ko'chirib qo'ysangiz yanada xotirjam bo'ladi.

---

## 🔄 Yangilash tartibi

```bash
cd /opt/teacher_bot
git pull
.venv/bin/pip install -r requirements.txt      # yangi kutubxona bo'lsa
sudo systemctl restart teacher-bot             # yoki: docker compose restart
```

Baza migratsiyalari (`app/db.py`) bot ishga tushganda **o'zi** bajariladi —
qo'lda hech narsa qilish shart emas.

---

## 👀 Kuzatish (bot tirikmi?)

| Nima | Buyruq |
|---|---|
| Xizmat holati | `systemctl status teacher-bot` |
| Loglar (jonli) | `journalctl -u teacher-bot -f` |
| Bot ichidagi log fayl | `tail -f /opt/teacher_bot/logs/bot.log` |
| Telegram'da tekshirish | guruhda `/check` — AI holati + navbat ko'rinadi |
| Server resursi | `htop` yoki `free -h` (bot ~80–120 MB RAM yeydi) |

---

## 🛡 Xavfsizlik eslatmalari

1. `.env` **hech qachon** repo'ga push qilinmaydi (`.gitignore` da) — tokenni
   chatda ham yozmang; OpenRouter/OpenAI kalitini vaqti-vaqti bilan yangilang.
2. `chmod 600 .env` — fayl faqat egasiga o'qiladi.
3. SSH uchun parol emas, **kalit** ishlatilsin (`PermitRootLogin no`).
4. Bot tashqi portni talab qilmaydi (polling ishlatadi). Mini App yoqilsa
   `8080` ni **tashqariga ochmang** — faqat reverse proxy yoki tunnel orqali.
5. Oracle'da "Always Free" limitidan chiqmaslik uchun ortiqcha instance
   yaratmang (billing alert qo'yish foydali).

---

## ❓ Tez-tez so'raladigan savollar

**Bot o'chib qolsa nima bo'ladi?**
Ballar, vazifalar, davomat bazada saqlanadi — hech narsa yo'qolmaydi. Yoqilgach
`check_deadlines` ishi o'tib ketgan muddatlarni topib, vazifalarni yopadi va
jarimalarni yozadi. Faqat o'sha oraliqda yuborilgan xabarlar kelmasligi mumkin
(Telegram yuborilmagan xabarni saqlab turmaydi) — ularni o'quvchi qayta
yuborsa bo'ladi.

**Internet uzilsa?**
`systemd` jarayonni qayta ishga tushiradi (`Restart=always`), aiogram esa
ulanishni o'zi tiklaydi.

**Ikki nusxa bir vaqtda ishlasa?**
Bu **mumkin emas** — bitta token bilan ikki joyda polling qilsangiz
`Conflict: terminated by other getUpdates request` xatosi chiqadi. Eski
nusxani to'xtatib, keyin yangisini yoqing.

**Bepul AI limiti tugasa-chi?**
Bot ishlashda davom etadi: AI chaqirilmaydi, ishlar `pending` bo'lib qoladi va
o'qituvchiga "qo'lda baholang" xabari keladi (batafsil: README → muammolar).

**Uy kompyuterida (Windows) qanday qilaman?**
Task Scheduler → "At startup" vazifasi:
`python c:\Users\Lenovo\Downloads\teacher_bot\run.py`
va "Restart on failure" ni yoqing. Kompyuter doim yoniq turishi kerak.


### 4) Avtomatik ishga tushish (systemd)
```bash
sudo cp deploy/teacher-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/teacher-bot.service   # User=ubuntu (yoki o'z nomingiz)
sudo systemctl daemon-reload
sudo systemctl enable --now teacher-bot
systemctl status teacher-bot          # holatni ko'rish
journalctl -u teacher-bot -f          # loglarni jonli ko'rish
```

`Restart=always` tufayli bot **yiqilsa ham, server qayta yonsa ham** o'zi
qaytadan ishga tushadi — qo'lda hech narsa qilish kerak emas.

### Docker bilan (agar docker afzal bo'lsa)
```bash
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER && newgrp docker
docker compose up -d --build          # ishga tushirish
docker compose logs -f                # loglar
docker compose restart                # qayta ishga tushirish
```
