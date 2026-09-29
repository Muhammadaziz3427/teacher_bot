"""Multi-language string catalog: uz | en | bi (bilingual).

In `bi` mode the *English* label is kept — the target language must stay in
English — while the Uzbek hint/explanation is appended, so both the student
and the parent can follow along.
"""

from __future__ import annotations

LANGS = ("uz", "en", "bi")
DEFAULT_LANG = "bi"

CATALOG: dict[str, dict[str, str]] = {}


def add(key: str, en: str, uz: str, bi: str | None = None) -> None:
    """Register one string in all three presentation modes."""
    CATALOG[key] = {"en": en, "uz": uz, "bi": bi or en}


def t(key: str, lang: str = DEFAULT_LANG, **kw) -> str:
    """Translate `key` and format it with `kw` (never raises)."""
    entry = CATALOG.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or entry.get("uz") or key
    if kw:
        try:
            text = text.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def normalize_lang(value: str | None) -> str:
    raw = (value or "").strip().lower()
    aliases = {
        "uz": "uz", "uzb": "uz", "uzbek": "uz", "o'zbek": "uz", "uzbekcha": "uz",
        "en": "en", "eng": "en", "english": "en", "ingliz": "en", "inglizcha": "en",
        "bi": "bi", "both": "bi", "mix": "bi", "aralash": "bi", "bilingual": "bi",
    }
    return aliases.get(raw, DEFAULT_LANG)


def lang_display(lang: str) -> str:
    return {"uz": "O'zbekcha / Uzbek", "en": "English", "bi": "Bilingual EN+UZ"}.get(
        lang, lang
    )


# --------------------------------------------------------------------------
# Generic
# --------------------------------------------------------------------------
add("app_title", "English Homework Bot", "Ingliz tili vazifalari boti")
add("help_title", "<b>📘 English Homework Bot</b>", "<b>📘 Ingliz tili vazifalari boti</b>")
add("only_teacher", "⛔ This command is for teachers only.", "⛔ Bu buyruq faqat o'qituvchi uchun.")
add("only_group", "This command works inside the class group.", "Bu buyruq guruh ichida ishlaydi.")
add("cancelled", "❌ Cancelled.", "❌ Bekor qilindi.")
add("unknown", "🤔 I did not understand that.", "🤔 Tushunmadim.")
add(
    "student_unknown",
    "I could not find that student. Use the full name, @username or numeric id.",
    "O'quvchi topilmadi. To'liq ism, @username yoki ID raqamini yozing.",
)
add(
    "no_ai",
    "⚠️ AI is not configured — I saved the work and flagged it for the teacher.",
    "⚠️ AI sozlanmagan — ish saqlandi va o'qituvchi uchun belgilandi.",
)
add("done", "✅ Done.", "✅ Bajarildi.")
add("save_error", "❌ Something went wrong, please try again.", "❌ Xatolik yuz berdi, qayta urinib ko'ring.")

# --------------------------------------------------------------------------
# Language switch
# --------------------------------------------------------------------------
add(
    "lang_usage",
    "Use <code>/language uz</code>, <code>/language en</code> or <code>/language bi</code>.\n"
    "uz = Uzbek interface, en = all English, bi = English + Uzbek explanation.",
    "<code>/language uz</code>, <code>/language en</code> yoki <code>/language bi</code>.\n"
    "uz = interfeys o'zbekcha, en = hammasi inglizcha, bi = inglizcha + o'zbekcha izoh.",
)
add(
    "lang_set",
    "✅ Interface and report language: <b>{name}</b>",
    "✅ Interfeys va hisobot tili: <b>{name}</b>",
)

add(
    "help_teacher",
    "<b>👩‍🏫 Teacher commands</b>\n"
    "<b>Private chat (all your groups):</b>\n"
    "<code>/groups</code> — dashboard: open any group you manage\n"
    "📊 Overview · 🗓 Attendance · 📚 Homeworks · 👥 Students · 📑 Reports · ⚙️ Settings\n"
    "<b>In the group:</b>\n"
    "<code>/homework</code> — new assignment (reply to a message to reuse it)\n"
    "<code>/homeworks</code> — list active assignments\n"
    "<code>/attendance</code> — mark today's attendance\n"
    "<code>/timetable</code> — weekly lesson times (deadlines follow them)\n"
    "<code>/pending</code> — work that needs a human grade\n"
    "<code>/bonus</code> / <code>/penalty</code> — manual points\n"
    "<code>/extra</code> — assign an extra task as a penalty\n"
    "<code>/assign @user</code> / <code>/unassign @user</code> — who may open "
    "this group from private chat\n"
    "<code>/test</code> — AI tests from the lessons taught (+ weekly schedule)\n"
    "<code>/topics</code> — which forum topic each message kind uses\n"
    "<code>/weekly</code> <code>/monthly</code> <code>/yearly</code> — reports "
    "(sent to your private chat)\n"
    "<code>/report all</code> — every student's report at once\n"
    "<code>/report @user</code> — one student's report (for parents)\n"
    "<code>/ranking</code> — class leaderboard\n"
    "<code>/export</code> — Excel file with everything\n"
    "<code>/link @user</code> — one-tap report link for the parent\n"
    "<code>/app</code> — open the class dashboard (Mini App)\n"
    "<code>/language</code> — uz | en | bi\n"
    "<code>/roster</code> — manage students\n"
    "<code>/check</code> — diagnostics\n"
    "<code>/cancel</code> — abort the current step",
    "<b>👩‍🏫 O'qituvchi buyruqlari</b>\n"
    "<b>Shaxsiy chat (barcha guruhlaringiz):</b>\n"
    "<code>/groups</code> — panel: boshqaradigan guruhni oching\n"
    "📊 Umumiy holat · 🗓 Davomat · 📚 Vazifalar · 👥 O'quvchilar · 📑 Hisobotlar · ⚙️ Sozlamalar\n"
    "<b>Guruh ichida:</b>\n"
    "<code>/homework</code> — yangi vazifa (xabarga reply qilsangiz o'sha matn olinadi)\n"
    "<code>/homeworks</code> — faol vazifalar ro'yxati\n"
    "<code>/attendance</code> — bugungi davomat\n"
    "<code>/timetable</code> — haftalik dars vaqtlari (muddat shundan hisoblanadi)\n"
    "<code>/pending</code> — qo'lda baholash kerak bo'lgan ishlar\n"
    "<code>/bonus</code> / <code>/penalty</code> — qo'lda ball qo'shish / ayirish\n"
    "<code>/extra</code> — jazo sifatida qo'shimcha topshiriq\n"
    "<code>/assign @user</code> / <code>/unassign @user</code> — shaxsiy chatdan "
    "guruhga kirish huquqi\n"
    "<code>/test</code> — o'tilgan darslar asosida AI testlari (+ haftalik jadval)\n"
    "<code>/topics</code> — qaysi mavzu nima uchun ishlatiladi\n"
    "<code>/weekly</code> <code>/monthly</code> <code>/yearly</code> — hisobotlar "
    "(shaxsiy chatingizga)\n"
    "<code>/report all</code> — hamma o'quvchi hisoboti birdan\n"
    "<code>/report @user</code> — bitta o'quvchi hisoboti (ota-ona uchun)\n"
    "<code>/ranking</code> — guruh reytingi\n"
    "<code>/export</code> — hamma ma'lumot Excel faylida\n"
    "<code>/link @user</code> — ota-onaga bir bosishli hisobot havolasi\n"
    "<code>/app</code> — guruh panelini ochish (Mini App)\n"
    "<code>/language</code> — uz | en | bi\n"
    "<code>/roster</code> — o'quvchilarni boshqarish\n"
    "<code>/check</code> — tizim tekshiruvi\n"
    "<code>/cancel</code> — qadamni bekor qilish",
)
add(
    "help_student",
    "<b>🎓 For students</b>\n"
    "Send your homework <b>as text or as a photo</b> to the group — I check it with AI "
    "and explain every mistake.\n"
    "Reply to the assignment message, or use <code>/submit &lt;number&gt;</code>.\n"
    "<code>/myhomework</code> — what is due\n"
    "<code>/mystats</code> — my progress\n"
    "<code>/mypoints</code> — my points\n"
    "<code>/myattendance</code> — my attendance\n"
    "<code>/mytasks</code> — my extra tasks",
    "<b>🎓 O'quvchilar uchun</b>\n"
    "Vazifani guruhga <b>matn yoki rasm</b> ko'rinishida yuboring — AI orqali tekshirib, "
    "har bir xatoni tushuntiraman.\n"
    "Vazifa xabariga reply qiling yoki <code>/submit &lt;raqam&gt;</code> dan foydalaning.\n"
    "<code>/myhomework</code> — muddati kelayotgan vazifalar\n"
    "<code>/mystats</code> — natijalarim\n"
    "<code>/mypoints</code> — ballarim\n"
    "<code>/myattendance</code> — davomatim\n"
    "<code>/mytasks</code> — qo'shimcha topshiriqlarim",
)

# --------------------------------------------------------------------------
# Homework wizard
# --------------------------------------------------------------------------
add("hw_ask_title", "📝 <b>Step 1/4</b> — Lesson/task name (e.g. <i>Present Simple, Unit 3</i>):",
    "📝 <b>1/4 qadam</b> — Mavzu nomi (masalan <i>Present Simple, Unit 3</i>):")
add("hw_ask_skill", "🎯 <b>Step 2/4</b> — Which skill is being checked?",
    "🎯 <b>2/4 qadam</b> — Qaysi ko'nikma tekshiriladi?")
add("hw_ask_desc", "📚 <b>Step 3/4</b> — The task itself (exercise numbers, what to do):",
    "📚 <b>3/4 qadam</b> — Vazifaning o'zi (mashq raqami, nima qilish kerak):")
add("hw_ask_media",
    "🖼 <b>Step 4/4</b> — Send the task photo/page <b>or</b> press Skip.",
    "🖼 <b>4/4 qadam</b> — Vazifa rasmini yuboring <b>yoki</b> «O'tkazib yuborish» ni bosing.")
add("hw_preview", "🔍 <b>Check the assignment:</b>", "🔍 <b>Vazifani tekshirib ko'ring:</b>")
add("hw_created",
    "✅ Assignment #{id} published.\nDeadline: <b>{due}</b> ({rel})\nStudents were notified.",
    "✅ №{id} vazifa e'lon qilindi.\nMuddat: <b>{due}</b> ({rel})\nO'quvchilarga xabar berildi.")
add("hw_list", "<b>📋 Active assignments</b>", "<b>📋 Faol vazifalar</b>")
add("hw_none", "There are no active assignments.", "Faol vazifalar yo'q.")
add("hw_closed", "🔒 Assignment #{id} closed.", "🔒 №{id} vazifa yopildi.")
add("hw_reminded", "🔔 Reminder sent to the group.", "🔔 Guruhga eslatma yuborildi.")
add("hw_deadline_bad",
    "I could not read that date. Try <i>tomorrow 18:00</i>, <i>friday 14:30</i> or "
    "<i>25.12 10:00</i> — or send <code>-</code> to use the next lesson.",
    "Sanani o'qiy olmadim. <i>ertaga 18:00</i>, <i>juma 14:30</i>, <i>25.12 10:00</i> "
    "kabi yozing — yoki keyingi darsga qo'yish uchun <code>-</code> yuboring.")
add("hw_ask_deadline",
    "⏰ Deadline? Send a date (<i>tomorrow 18:00</i>) or <code>-</code> for the next lesson time.",
    "⏰ Muddat? Sana yozing (<i>ertaga 18:00</i>) yoki keyingi dars vaqti uchun <code>-</code>.")
add("hw_new", "🚀 <b>New assignment #{id}</b>", "🚀 <b>Yangi vazifa №{id}</b>")
add("btn_skip", "Skip", "O'tkazib yuborish")
add("btn_next_lesson", "⏰ Use the next lesson time", "⏰ Keyingi dars vaqtini ishlatish")
add("btn_change_due", "⏰ Change deadline", "⏰ Muddatni o'zgartirish")
add("hw_due_auto",
    "Deadline set to the next lesson: <b>{when}</b>",
    "Muddat keyingi dars vaqtiga qo'yildi: <b>{when}</b>")
add("hw_no_schedule",
    "No timetable yet, so the deadline is {hours} hours from now: <b>{when}</b>",
    "Jadval yo'q, shuning uchun muddat {hours} soatdan keyin: <b>{when}</b>")
add("btn_confirm", "✅ Confirm & publish", "✅ Tasdiqlash va e'lon qilish")
add("btn_cancel", "❌ Cancel", "❌ Bekor qilish")
add("btn_close", "🔒 Close", "🔒 Yopish")
add("btn_remind", "🔔 Remind", "🔔 Eslatish")
add("btn_stats", "📊 Statistics", "📊 Statistika")
add("btn_export", "📄 Excel", "📄 Excel")
add("btn_grade", "✍️ Grade manually", "✍️ Qo'lda baholash")
add("btn_accept", "✅ Accept AI grade", "✅ AI bahosini qabul qilish")
add("btn_partial", "⚠️ Partial", "⚠️ Qisman to'g'ri")
add("btn_reject", "❌ Reject", "❌ Rad etish")

# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------
add("att_title", "<b>🗓 Attendance — {date}</b>", "<b>🗓 Davomat — {date}</b>")
add("att_help",
    "Tap a name to switch: ✅ present → ⏰ late → ❌ absent → 🟡 excused.",
    "Ismni bosing: ✅ keldi → ⏰ kechikdi → ❌ kelmadi → 🟡 sababli.")
add("att_saved", "Saved: <b>{name}</b> — {status} ({points} points)",
    "Saqlandi: <b>{name}</b> — {status} ({points} ball)")
add("att_none", "There are no students yet. Ask them to write /start in the group.",
    "Hozircha o'quvchilar yo'q. Guruhda /start yozishlarini so'rang.")
add("att_all_present", "✅ All present", "✅ Hammasi keldi")
add("att_done", "💾 Save & finish", "💾 Saqlash va tugatish")
add("att_finished", "✅ Attendance saved for {date}.", "✅ {date} uchun davomat saqlandi.")
add("att_unmarked", "Not marked yet", "Hali belgilanmagan")
add("st_present", "✅ present", "✅ keldi")
add("st_late", "⏰ late", "⏰ kechikdi")
add("st_absent", "❌ absent", "❌ kelmadi")
add("st_excused", "🟡 excused", "🟡 sababli")

# --------------------------------------------------------------------------
# AI feedback
# --------------------------------------------------------------------------
add("fb_title", "📝 <b>Homework #{id} checked</b>", "📝 <b>№{id} vazifa tekshirildi</b>")
add("fb_student", "<b>Student:</b> {name}", "<b>O'quvchi:</b> {name}")
add("fb_score", "<b>Score:</b> {score}/100  <b>Grade:</b> {grade}",
    "<b>Ball:</b> {score}/100  <b>Baho:</b> {grade}")
add("fb_verdict", "<b>Result:</b> {verdict}", "<b>Natija:</b> {verdict}")
add("fb_late", "⏰ Submitted late — points were halved and a penalty applied.",
    "⏰ Kech topshirildi — ball yarmiga qisqartirildi va jarima yozildi.")
add("fb_points", "🏅 Points earned: <b>{points}</b>", "🏅 Olingan ball: <b>{points}</b>")
add("fb_tasks", "📋 <b>Exercise by exercise</b>", "📋 <b>Mashqma-mashq tahlil</b>")
add("fb_mistakes", "❌ <b>Mistakes and how to fix them</b>", "❌ <b>Xatolar va to'g'rilash yo'li</b>")
add("fb_no_mistakes", "🌟 No mistakes found — excellent work!", "🌟 Xato topilmadi — juda yaxshi!")
add("fb_strengths", "✅ <b>What you did well</b>", "✅ <b>Yaxshi tomonlaringiz</b>")
add("fb_tips", "💡 <b>Tips for next time</b>", "💡 <b>Keyingi marta uchun maslahatlar</b>")
add("fb_topics", "🎯 <b>Topic mastery</b>", "🎯 <b>Mavzular bo'yicha o'zlashtirish</b>")
add("fb_level", "<b>Estimated level:</b> {level}", "<b>Taxminiy daraja:</b> {level}")
add("fb_summary", "💬 <b>Summary</b>", "💬 <b>Umumiy xulosa</b>")
add("fb_teacher_note", "🧑‍🏫 <b>Teacher:</b> {comment}", "🧑‍🏫 <b>O'qituvchi izohi:</b> {comment}")
add("fb_pending",
    "⏳ I received your work (#{id}) and the teacher will grade it shortly.",
    "⏳ Ishingiz qabul qilindi (№{id}), o'qituvchi tez orada baholaydi.")
add("fb_pending_teacher",
    "⚠️ Submission #{id} from <b>{name}</b> could not be auto-checked. Use /pending.",
    "⚠️ <b>{name}</b> ning №{id} ishi avtomatik tekshirilmadi. /pending dan foydalaning.")
add("fb_rule", "rule: {rule}", "qoida: {rule}")
add("fb_you_sent", "you wrote: {original}", "siz yozgansiz: {original}")
add("fb_correct_is", "correct: {correction}", "to'g'risi: {correction}")
add("fb_task_line", "{task} — {status} — {comment}", "{task} — {status} — {comment}")
add("fb_no_text",
    "I could not read any text in your submission. Please send it as text or a clearer photo.",
    "Ishingizda matn topa olmadim. Iltimos, matn ko'rinishida yoki aniqroq rasm yuboring.")

add("vd_correct", "correct ✅", "to'g'ri ✅")
add("vd_partial", "partially correct ⚠️", "qisman to'g'ri ⚠️")
add("vd_wrong", "incorrect ❌", "noto'g'ri ❌")
add("vd_unclear", "could not be checked 🤔", "tekshirib bo'lmadi 🤔")
add("ts_correct", "✅ correct", "✅ to'g'ri")
add("ts_partial", "⚠️ partial", "⚠️ qisman")
add("ts_wrong", "❌ wrong", "❌ xato")
add("ts_missing", "⬜ not done", "⬜ bajarilmagan")
add("lv_weak", "needs work", "ishlash kerak")
add("lv_ok", "acceptable", "o'rtacha")
add("lv_strong", "strong", "yaxshi")

# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
add("rep_group_title", "<b>📊 {period} report — whole class</b>",
    "<b>📊 {period} hisobot — butun guruh</b>")
add("rep_student_title", "<b>📊 {period} report</b>", "<b>📊 {period} hisobot</b>")
add("rep_period_line", "Period: {start} — {end}", "Davr: {start} — {end}")
add("rep_attendance_line", "🗓 Attendance: {present}/{total} lessons ({pct}%)",
    "🗓 Davomat: {total} darsdan {present} tasi ({pct}%)")
add("rep_hw_line",
    "📚 Homework: {done}/{assigned} done, {ontime} on time, {late} late (average {avg})",
    "📚 Vazifalar: {assigned} tadan {done} tasi, {ontime} vaqtida, {late} kechikkan (o'rtacha {avg})")
add("rep_missing_line", "🚫 Not done: {count} → penalty {points}",
    "🚫 Bajarilmagan: {count} ta → jarima {points}")
add("rep_points_line", "🏅 Points this period: {points}", "🏅 Bu davrdagi ball: {points}")
add("rep_rank_line", "🏆 Position in class: {rank}/{total}", "🏆 Guruhdagi o'rni: {rank}/{total}")
add("rep_errors", "🔁 <b>Most frequent mistakes</b>", "🔁 <b>Eng ko'p uchraydigan xatolar</b>")
add("rep_errors_line", "• {category} — {count}×", "• {category} — {count} marta")
add("rep_strengths", "🌟 <b>Strengths</b>", "🌟 <b>Kuchli tomonlar</b>")
add("rep_focus", "🎯 <b>Next focus</b>", "🎯 <b>Keyingi ishlar</b>")
add("rep_parent_note", "👨‍👩‍👦 <b>Note for parents</b>", "👨‍👩‍👦 <b>Ota-onaga izoh</b>")
add("rep_no_data", "No data for this period yet.", "Bu davr uchun ma'lumot yo'q.")
add("rep_trend_up", "📈 Progress compared to the previous period: <b>+{value}</b>",
    "📈 Oldingi davrga nisbatan o'sish: <b>+{value}</b>")
add("rep_trend_down", "📉 Compared to the previous period: <b>-{value}</b>",
    "📉 Oldingi davrga nisbatan pasayish: <b>-{value}</b>")
add("rep_trend_same", "➖ Same level as the previous period.", "➖ Oldingi davr bilan bir xil.")
add("rep_class_avg", "Class average score: {avg}", "Guruh o'rtacha bahosi: {avg}")
add("rep_top", "🥇 Top students", "🥇 Eng yaxshi o'quvchilar")
add("rep_need_help", "⚠️ Need support", "⚠️ Yordam kerak")
add("rep_certificate",
    "🏆 <b>Year summary</b>\nLessons: {lessons}\nAttendance: {pct}%\n"
    "Homework completion: {hw}%\nAverage score: {avg}\nEstimated level: <b>{level}</b>",
    "🏆 <b>Yillik xulosa</b>\nDarslar: {lessons}\nDavomat: {pct}%\n"
    "Vazifa bajarilishi: {hw}%\nO'rtacha baho: {avg}\nTaxminiy daraja: <b>{level}</b>")
add("rep_export_ready", "📄 Report file is ready: {name}", "📄 Hisobot fayli tayyor: {name}")
add("rep_pick_student", "Choose a student:", "O'quvchini tanlang:")
add("menu_dashboard", "<b>🏫 My groups dashboard</b>", "<b>🏫 Guruhlarim paneli</b>")
add("menu_my_groups", "🏫 My groups", "🏫 Guruhlarim")
add("dash_pick_group", "Your groups — pick one to manage:", "Guruhlaringiz — boshqarish uchun tanlang:")
add("dash_no_groups",
    "You do not have access to any group yet. Add me to a class group and write /start there first.",
    "Hozircha hech bir guruhga kirish huquqingiz yo'q. Avval meni guruhga qo'shib, u yerda /start yozing.")
add("dash_open", "🏫 Open:", "🏫 Ochish:")
add("dash_group_line", "👥 {students} students · 📚 {active} active", "👥 {students} o'quvchi · 📚 {active} faol")
add("dash_sections", "Choose a section for <b>{title}</b>:",
    "<b>{title}</b> uchun bo'limni tanlang:")
add("dash_btn_overview", "📊 Overview", "📊 Umumiy holat")
add("dash_btn_attendance", "🗓 Attendance", "🗓 Davomat")
add("dash_btn_homeworks", "📚 Homeworks", "📚 Vazifalar")
add("dash_btn_students", "👥 Students", "👥 O'quvchilar")
add("dash_btn_reports", "📑 Reports", "📑 Hisobotlar")
add("dash_btn_settings", "⚙️ Settings", "⚙️ Sozlamalar")
add("dash_overview",
    "<b>{title}</b>\n👥 {students} students · 📚 {active} active tasks\n"
    "🗓 {today}: ✅ {present} · ⏰ {late} · ❌ {absent}\n"
    "📚 Next task: {next_task}\n🏆 Leader: {leader}",
    "<b>{title}</b>\n👥 {students} o'quvchi · 📚 {active} faol vazifa\n"
    "🗓 {today}: ✅ {present} · ⏰ {late} · ❌ {absent}\n"
    "📚 Keyingi vazifa: {next_task}\n🏆 Yetakchi: {leader}")
add("dash_next_none", "no active tasks", "faol vazifa yo'q")
add("dash_leader_none", "—", "—")
add("dash_settings",
    "<b>{title}</b> — settings\n🌐 Language: {language}\n👥 Teachers: {managers}\n"
    "Assign: <code>/assign @user</code> (inside the group)\n"
    "Unassign: <code>/unassign @user</code>",
    "<b>{title}</b> — sozlamalar\n🌐 Til: {language}\n👥 O'qituvchilar: {managers}\n"
    "Biriktirish: <code>/assign @user</code> (guruh ichida)\n"
    "Olib tashlash: <code>/unassign @user</code>")
add("dash_goto_group", "Open everything in the group itself with /menu there.",
    "Hamma narsani guruhning o'zida /menu bilan oching.")
add("dash_back_groups", "⬅️ My groups", "⬅️ Guruhlarim")
add("dash_back_sections", "⬅️ Sections", "⬅️ Bo'limlar")
add("assign_usage",
    "Usage (inside the group): <code>/assign @user</code> or <code>/assign 123456</code>",
    "Foydalanish (guruh ichida): <code>/assign @user</code> yoki <code>/assign 123456</code>")
add("assign_done", "✅ {name} can now manage this group from private chat.",
    "✅ {name} endi bu guruhni shaxsiy chatdan boshqara oladi.")
add("assign_self", "You already manage this group.", "Siz bu guruhni allaqachon boshqarasiz.")
add("unassign_done", "🗑 {name} was removed from this group's managers.",
    "🗑 {name} bu guruh boshqaruvchilaridan olib tashlandi.")
add("unassign_none", "That user is not an assigned manager of this group.",
    "Bu foydalanuvchi bu guruhga biriktirilmagan.")
add("only_manager", "⛔ You do not manage this group yet.",
    "⛔ Siz hali bu guruhni boshqarmaysiz.")
add("dash_recent", "🕘 <b>Latest checks</b>", "🕘 <b>So'nggi tekshiruvlar</b>")
add("dash_recent_line", "• {name} — #{hw} {score}/100", "• {name} — №{hw} {score}/100")
add("dash_missing_today", "🚫 <b>Missing today</b>", "🚫 <b>Bugun topshirmaganlar</b>")
add("dash_missing_line", "• {name} — #{hw} {title}", "• {name} — №{hw} {title}")
add("dash_homework_hint",
    "Create assignments inside the group with /homework, or pick one below:",
    "Vazifani guruh ichida /homework bilan yarating yoki quyidagidan tanlang:")
add("dash_att_hint",
    "Marking inside the group works best. Today so far:",
    "Davomatni guruh ichida belgilash qulay. Bugungi holat:")
add("dash_students_hint", "Top students this week:",
    "Bu haftaning eng yaxshi o'quvchilari:")
add("dash_reports_hint", "Pick a period, then a student:",
    "Davrni, keyin o'quvchini tanlang:")
add("dash_period_weekly", "📊 Week", "📊 Hafta")
add("dash_period_monthly", "📅 Month", "📅 Oy")
add("dash_period_yearly", "🗓 Year", "🗓 Yil")
add("dash_export_hint", "Excel report for the whole group:",
    "Butun guruh uchun Excel hisobot:")
add("dash_btn_export", "📄 Download Excel", "📄 Excel yuklash")
add("rep_parent_format", "⬆️ <b>Parent copy</b> — forward this message to the parent.",
    "⬆️ <b>Ota-ona uchun nusxa</b> — shu xabarni ota-onaga yuboring.")
add("rep_nobody", "No students registered yet.", "Hozircha o'quvchilar ro'yxatdan o'tmagan.")

# --------------------------------------------------------------------------
# Points, penalties, extra tasks
# --------------------------------------------------------------------------
add("pen_missing_title", "🚫 <b>Homework #{id} is closed</b> ({title})",
    "🚫 <b>№{id} vazifa muddati tugadi</b> ({title})")
add("pen_missing_line", "• {name} — not submitted ({points} points)",
    "• {name} — topshirmadi ({points} ball)")
add("pen_warning", "⚠️ {name}, this is your {count}-st missed homework. Please submit it!",
    "⚠️ {name}, bu sizning {count}-bajarilmagan vazifangiz. Iltimos, topshiring!")
add("pen_extra_assigned",
    "📌 <b>{name}</b>, as a penalty complete this extra task within {hours} hours:\n<i>{task}</i>",
    "📌 <b>{name}</b>, jazo sifatida {hours} soat ichida shu qo'shimcha topshiriqni bajaring:\n<i>{task}</i>")
add("pen_extra_list", "<b>📌 Extra tasks</b>", "<b>📌 Qo'shimcha topshiriqlar</b>")
add("pen_extra_none", "You have no extra tasks. Well done!",
    "Qo'shimcha topshiriqlaringiz yo'q. Barakalla!")
add("pen_extra_usage", "Usage: <code>/extra @student description</code>",
    "Foydalanish: <code>/extra @o'quvchi topshiriq matni</code>")
add("pen_bonus_usage", "Usage: <code>/bonus @student 2 reason</code>",
    "Foydalanish: <code>/bonus @o'quvchi 2 sabab</code>")
add("pen_penalty_usage", "Usage: <code>/penalty @student 3 reason</code>",
    "Foydalanish: <code>/penalty @o'quvchi 3 sabab</code>")
add("pen_points_added", "🏅 {name}: {sign}{points} points — {reason}",
    "🏅 {name}: {sign}{points} ball — {reason}")
add("pen_streak", "🔥 {name} submitted {count} homeworks on time in a row: +{points} bonus!",
    "🔥 {name} {count} marta ketma-ket vaqtida topshirdi: +{points} bonus!")
add("pen_grade_usage", "Usage: <code>/grade &lt;submission_id&gt; &lt;0-100&gt; [comment]</code>",
    "Foydalanish: <code>/grade &lt;ish_id&gt; &lt;0-100&gt; [izoh]</code>")
add("pen_graded", "✍️ Submission #{id} graded: {score}/100 — {points} points",
    "✍️ №{id} ish baholandi: {score}/100 — {points} ball")
add("pen_pending_title", "<b>⏳ Waiting for a manual grade</b>",
    "<b>⏳ Qo'lda baholash kutilmoqda</b>")
add("pen_pending_none", "Nothing is waiting. 🎉", "Kutayotgan ish yo'q. 🎉")
add("pen_sub_line", "#{id} {name} — {title} ({when})", "№{id} {name} — {title} ({when})")

# --------------------------------------------------------------------------
# Student views
# --------------------------------------------------------------------------
add("st_my_homework", "<b>📚 Your assignments</b>", "<b>📚 Sizning vazifalaringiz</b>")
add("st_nothing_due", "Nothing is due right now. 🎉", "Hozircha vazifa yo'q. 🎉")
add("st_hw_line", "#{id} {title}\n   deadline {due} — {status}",
    "№{id} {title}\n   muddat {due} — {status}")
add("st_status_done", "submitted ✅", "topshirilgan ✅")
add("st_status_late", "submitted late ⏰", "kech topshirilgan ⏰")
add("st_status_todo", "not submitted yet", "hali topshirilmagan")
add("st_my_stats", "<b>📊 Your results</b>", "<b>📊 Sizning natijalaringiz</b>")
add("st_my_points", "<b>🏅 Your points: {points}</b>", "<b>🏅 Sizning ballaringiz: {points}</b>")
add("st_my_attendance", "<b>🗓 Your attendance</b>", "<b>🗓 Sizning davomatingiz</b>")
add("st_att_line", "✅ {present} · ⏰ {late} · ❌ {absent} · 🟡 {excused} (total {total})",
    "✅ {present} · ⏰ {late} · ❌ {absent} · 🟡 {excused} (jami {total})")
add("st_submit_usage",
    "Reply to the assignment with your work, or use <code>/submit &lt;number&gt;</code> and then send it.",
    "Vazifa xabariga reply qilib ishingizni yuboring yoki <code>/submit &lt;raqam&gt;</code> dan keyin yuboring.")
add("st_submit_which", "Which assignment? Send one of: {ids}",
    "Qaysi vazifa? Bulardan birini yuboring: {ids}")
add("st_submit_saved", "📥 Saved. Checking with AI…", "📥 Qabul qilindi. AI tekshiruvi boshlandi…")
add("st_submit_queued",
    "📥 Saved. The AI is busy right now — {count} work(s) are ahead of yours, "
    "your result will arrive shortly.",
    "📥 Qabul qilindi. AI hozir band — sizdan oldin {count} ta ish turibdi, "
    "natija tez orada keladi.")
add("st_submit_queue_full",
    "⚠️ The queue is full right now. Please send your work again in a minute — "
    "nothing was lost.",
    "⚠️ Navbat to'la. Iltimos, bir daqiqadan keyin qayta yuboring — hech narsa yo'qolmadi.")
add("st_points_breakdown", "<b>Recent points</b>", "<b>Oxirgi ballar</b>")
add("st_points_event", "{date} {sign}{points} — {reason}", "{date} {sign}{points} — {reason}")
add("rank_title", "<b>🏆 Class leaderboard ({period})</b>", "<b>🏆 Guruh reytingi ({period})</b>")
add("rank_line", "{place}. {name} — {points} points ({avg} avg)",
    "{place}. {name} — {points} ball (o'rtacha {avg})")

# --------------------------------------------------------------------------
# Helper labels
# --------------------------------------------------------------------------
_SKILLS = {
    "grammar": ("Grammar", "Grammatika"),
    "vocabulary": ("Vocabulary", "Lug'at"),
    "writing": ("Writing", "Yozish"),
    "reading": ("Reading", "O'qish"),
    "listening": ("Listening", "Tinglash"),
    "speaking": ("Speaking", "Gapirish"),
    "mixed": ("Mixed", "Aralash"),
}


def skill_label(skill: str, lang: str = DEFAULT_LANG) -> str:
    key = (skill or "mixed").strip().lower()
    if key not in _SKILLS:
        for name in _SKILLS:
            if key.startswith(name[:4]):
                key = name
                break
    en, uz = _SKILLS.get(key, _SKILLS["mixed"])
    return en if lang == "en" else uz if lang == "uz" else f"{en} / {uz}"


_CATEGORIES = {
    "grammar": ("Grammar", "Grammatika"),
    "tense": ("Verb tenses", "Fe'l zamonlari"),
    "articles": ("Articles (a/an/the)", "Artikllar (a/an/the)"),
    "prepositions": ("Prepositions", "Predloglar"),
    "spelling": ("Spelling", "Imlo"),
    "punctuation": ("Punctuation", "Tinish belgilari"),
    "word order": ("Word order", "So'z tartibi"),
    "vocabulary": ("Vocabulary choice", "So'z tanlash"),
    "word form": ("Word form", "So'z shakli"),
    "pronoun": ("Pronouns", "Olmosh"),
    "plural": ("Singular / plural", "Birlik / ko'plik"),
    "capitalisation": ("Capital letters", "Bosh harflar"),
    "translation": ("Translation", "Tarjima"),
    "missing answer": ("Unanswered part", "Bajarilmagan qism"),
    "other": ("Other", "Boshqa"),
}


def category_label(category: str, lang: str = DEFAULT_LANG) -> str:
    key = (category or "other").strip().lower()
    if key not in _CATEGORIES:
        key = "other"
    en, uz = _CATEGORIES[key]
    return en if lang == "en" else uz if lang == "uz" else f"{en} / {uz}"


def grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 65:
        return "C"
    if score >= 50:
        return "D"
    return "E"


def cefr_for(score: int, base: str = "") -> str:
    """Very rough CEFR estimate derived from the average score."""
    if score >= 92:
        return "B2+"
    if score >= 82:
        return "B1"
    if score >= 70:
        return "B1-"
    if score >= 58:
        return "A2+"
    if score >= 45:
        return "A2"
    return base or "A1"


def level_label(level: str, lang: str = DEFAULT_LANG) -> str:
    mapping = {"weak": "lv_weak", "ok": "lv_ok", "strong": "lv_strong"}
    return t(mapping.get((level or "").strip().lower(), "lv_ok"), lang)


def verdict_label(verdict: str, lang: str = DEFAULT_LANG) -> str:
    mapping = {
        "correct": "vd_correct",
        "partial": "vd_partial",
        "wrong": "vd_wrong",
        "unclear": "vd_unclear",
    }
    return t(mapping.get((verdict or "").strip().lower(), "vd_unclear"), lang)


def task_status_label(status: str, lang: str = DEFAULT_LANG) -> str:
    mapping = {
        "correct": "ts_correct",
        "partial": "ts_partial",
        "wrong": "ts_wrong",
        "missing": "ts_missing",
    }
    return t(mapping.get((status or "").strip().lower(), "ts_partial"), lang)


def attendance_status_label(status: str, lang: str = DEFAULT_LANG) -> str:
    mapping = {"present": "st_present", "late": "st_late", "absent": "st_absent",
               "excused": "st_excused"}
    return t(mapping.get((status or "").strip().lower(), "st_present"), lang)


def period_label(period: str, lang: str = DEFAULT_LANG) -> str:
    en = {"weekly": "Weekly", "monthly": "Monthly", "yearly": "Yearly"}.get(period, period)
    uz = {"weekly": "Haftalik", "monthly": "Oylik", "yearly": "Yillik"}.get(period, period)
    if lang == "en":
        return en
    if lang == "uz":
        return uz
    return f"{en} / {uz}"


# --------------------------------------------------------------------------
# Timetable
# --------------------------------------------------------------------------
add("tt_title", "<b>🗓 Weekly timetable</b>", "<b>🗓 Haftalik dars jadvali</b>")
add("tt_empty",
    "No timetable set, so deadlines are <b>{hours} hours</b> after the assignment. "
    "Add lesson times with <code>/timetable</code>.",
    "Jadval o'rnatilmagan, shuning uchun muddat vazifa berilgandan <b>{hours} soat</b> keyin. "
    "<code>/timetable</code> orqali dars vaqtlarini qo'shing.")
add("tt_added", "✅ Lesson added: <b>{weekday} {time}</b>", "✅ Dars qo'shildi: <b>{weekday} {time}</b>")
add("tt_removed", "🗑 Removed.", "🗑 O'chirildi.")
add("tt_usage",
    "Usage: <code>/timetable add Monday 14:00</code> or <code>/timetable clear</code>",
    "Foydalanish: <code>/timetable add Monday 14:00</code> yoki <code>/timetable clear</code>")
add("tt_bad_weekday",
    "Please use an English weekday name, e.g. Monday.",
    "Hafta kunini inglizcha yozing, masalan Monday.")
add("tt_next", "Next lesson: <b>{when}</b>", "Keyingi dars: <b>{when}</b>")
add("rep_focus_rules", "Work on these rules: {rules}", "Quyidagi qoidalar ustida ishlash kerak: {rules}")
add("rep_examples", "✍️ <b>Real examples from the work</b>", "✍️ <b>Ishdan aniq misollar</b>")
add("rep_example_line", "• {original} → <b>{correction}</b>", "• {original} → <b>{correction}</b>")
add("rep_note_attendance",
    "{name} missed {absent} lesson(s). Regular attendance is the fastest way to improve.",
    "{name} {absent} ta darsni qoldirgan. Doimiy qatnashish — eng tez o'sish yo'li.")
add("rep_note_homework",
    "{name} did not submit {missing} homework task(s). Please check this at home.",
    "{name} {missing} ta vazifani topshirmagan. Iltimos, uyda nazorat qiling.")
add("rep_note_score",
    "The average score is {avg}/100. Short daily practice (15 minutes) will help a lot.",
    "O'rtacha baho {avg}/100. Har kuni 15 daqiqa mashq qilish katta yordam beradi.")
add("rep_note_good",
    "{name} is doing well — thank you for the support at home!",
    "{name} yaxshi o'zlashtirmoqda — uydagi yordamingiz uchun rahmat!")
add("rep_punctual", "⏱ Always submitted on time.", "⏱ Doim vaqtida topshirgan.")
add("rep_no_errors", "🎉 No grammar mistakes found in {count} checked works.",
    "🎉 {count} ta ishda grammatik xato topilmadi.")

# --------------------------------------------------------------------------
# Reports are private: only the teacher sees student reports
# --------------------------------------------------------------------------
add("rep_private_sent", "📨 Sent to your private chat ({count} message(s)).",
    "📨 Shaxsiy chatingizga yuborildi ({count} xabar).")
add("rep_private_needed",
    "🔒 Student reports are private. Open me in a private chat and press "
    "<code>/start</code> once, then repeat the command.",
    "🔒 O'quvchi hisobotlari maxfiy. Men bilan shaxsiy chatga o'tib bir marta "
    "<code>/start</code> bosing, keyin buyruqni takrorlang.")
add("rep_all_started",
    "🧑‍🏫 Generating reports for <b>{count}</b> student(s)…",
    "🧑‍🏫 <b>{count}</b> o'quvchi uchun hisobot tayyorlanmoqda…")
add("rep_all_done", "✅ All {count} reports were sent to your private chat.",
    "✅ {count} hisobot shaxsiy chatingizga yuborildi.")
add("rep_all_none", "There are no students to report on yet.",
    "Hozircha hisobot qiladigan o'quvchi yo'q.")
add("rep_usage",
    "<code>/report @user</code> — one student,\n"
    "<code>/report all</code> — every student (weekly + monthly each).",
    "<code>/report @user</code> — bitta o'quvchi,\n"
    "<code>/report all</code> — hamma o'quvchi (har biri haftalik + oylik).")

# --------------------------------------------------------------------------
# Forum topics
# --------------------------------------------------------------------------
add("topics_title", "<b>🧵 Group topics</b>", "<b>🧵 Guruh mavzulari</b>")
add("topics_status", "• {kind}: {value}", "• {kind}: {value}")
add("topics_detected", "auto-detected ✅", "avtomatik aniqlandi ✅")
add("topics_missing", "not detected yet (General is used)", "hali aniqlanmagan (General ishlatiladi)")
add("topics_how",
    "\nI detect topics by myself — nothing to configure:\n"
    "• send <code>/homework</code> inside the Homework topic\n"
    "• send <code>/test</code> inside the Test topic\n"
    "• send <code>/weekly</code> inside the Announcements topic\n"
    "After that every message of that kind goes to the same topic.",
    "\nMavzularni o'zim aniqlayman — sozlash shart emas:\n"
    "• Homework mavzusida <code>/homework</code> yuboring\n"
    "• Test mavzusida <code>/test</code> yuboring\n"
    "• Announcements mavzusida <code>/weekly</code> yuboring\n"
    "Shundan keyin o'sha turdagi xabarlar doim o'sha mavzuga tushadi.")
add("topics_forum", "🧵 This is a forum group with topics.", "🧵 Bu mavzularga bo'lingan guruh.")
add("topics_not_forum", "This group has no topics (a normal group).",
    "Bu guruh mavzularga bo'linmagan (oddiy guruh).")
add("student_joined",
    "👋 Welcome, {name}! I added you to the class list — send your homework here "
    "as text or a photo.",
    "👋 Xush kelibsiz, {name}! Sizni guruh ro'yxatiga qo'shdim — vazifani shu yerga "
    "matn yoki rasm qilib yuboring.")
add("roster_auto",
    "👥 Everyone in the group is a student automatically; teachers are recognised "
    "by <code>ADMIN_IDS</code>/<code>TEACHER_IDS</code> or <code>/assign</code>.",
    "👥 Guruhdagi har bir a'zo avtomatik o'quvchi bo'ladi; o'qituvchilar "
    "<code>ADMIN_IDS</code>/<code>TEACHER_IDS</code> yoki <code>/assign</code> orqali belgilanadi.")

# --------------------------------------------------------------------------
# Tests / quizzes
# --------------------------------------------------------------------------
add("test_menu",
    "<b>📝 Tests</b>\n<code>/test new 10</code> — AI builds 10 questions from the "
    "lessons taught\n<code>/test manual</code> — write questions yourself\n"
    "<code>/test post</code> — post the newest test now\n"
    "<code>/test schedule Wednesday 14:00</code> — automatic weekly test\n"
    "<code>/test off</code> — stop the automatic tests\n"
    "<code>/test list</code> — my tests",
    "<b>📝 Testlar</b>\n<code>/test new 10</code> — AI o'tilgan darslar asosida 10 savol "
    "tuzadi\n<code>/test manual</code> — savollarni o'zingiz yozasiz\n"
    "<code>/test post</code> — eng yangi testni hozir yuborish\n"
    "<code>/test schedule Wednesday 14:00</code> — har hafta avtomatik test\n"
    "<code>/test off</code> — avtomatik testni o'chirish\n"
    "<code>/test list</code> — testlarim")
add("test_new_started",
    "🤖 AI is preparing {count} questions on: <b>{topics}</b>…",
    "🤖 AI <b>{topics}</b> bo'yicha {count} savol tayyorlayapti…")
add("test_created",
    "✅ Test #{id} is ready: <b>{count}</b> question(s).\nTopics: {topics}\n"
    "Post it with <code>/test post</code> (students get {minutes} minutes).",
    "✅ #{id} test tayyor: <b>{count}</b> ta savol.\nMavzular: {topics}\n"
    "<code>/test post</code> bilan yuboring (o'quvchilarga {minutes} daqiqa).")
add("test_none_ready",
    "I have no questions yet. Use <code>/test new 10</code> (AI) or "
    "<code>/test manual</code>.",
    "Hozircha savollar yo'q. <code>/test new 10</code> (AI) yoki "
    "<code>/test manual</code> dan foydalaning.")
add("test_no_ai",
    "⚠️ AI is off, so I could not generate questions. Write them yourself with "
    "<code>/test manual</code>.",
    "⚠️ AI o'chiq, savol tuza olmadim. <code>/test manual</code> bilan o'zingiz yozing.")
add("test_manual_how",
    "✍️ Send each question like this:\n"
    "<code>Question text?\na) first\nb) second\n*c) correct one\nd) fourth</code>\n\n"
    "Mark the correct option with <code>*</code>. Send <code>/done</code> when finished.",
    "✍️ Har bir savolni shunday yuboring:\n"
    "<code>Savol matni?\na) birinchi\nb) ikkinchi\n*c) to'g'ri javob\nd) to'rtinchi</code>\n\n"
    "To'g'ri javobni <code>*</code> bilan belgilang. Tugatgach <code>/done</code> yuboring.")
add("test_added", "✅ Question {position} added ({total} total).",
    "✅ {position}-savol qo'shildi (jami {total}).")
add("test_manual_bad",
    "I could not read that. Format: question line, then a/b/c/d lines, "
    "with * on the correct one.",
    "O'qiy olmadim. Ko'rinish: savol qatori, keyin a/b/c/d qatorlari, "
    "to'g'risida * belgisi.")
add("test_scheduled",
    "📅 Automatic test: every <b>{weekday}</b> at <b>{time}</b> "
    "({count} questions, {minutes} min).\nI will post it in the Test topic myself.",
    "📅 Avtomatik test: har <b>{weekday}</b> kuni <b>{time}</b> da "
    "({count} savol, {minutes} daqiqa).\nUni Test mavzusiga o'zim joylayman.")
add("test_schedule_off", "🔕 Automatic weekly tests are off.",
    "🔕 Haftalik avtomatik testlar o'chirildi.")
add("test_posted",
    "📝 <b>Test #{id}: {title}</b>\n{count} questions · you have {minutes} minutes. "
    "Tap your answers below 👇",
    "📝 <b>#{id} test: {title}</b>\n{count} savol · {minutes} daqiqa vaqtingiz bor. "
    "Javoblarni quyidagi tugmalardan bosing 👇")
add("test_question", "<b>Question {position}/{total}</b>\n{text}",
    "<b>{position}/{total} savol</b>\n{text}")
add("test_answer_right", "✅ Correct! {explanation}", "✅ To'g'ri! {explanation}")
add("test_answer_wrong", "❌ Wrong. Correct answer: {answer}. {explanation}",
    "❌ Xato. To'g'ri javob: {answer}. {explanation}")
add("test_answer_done", "You already answered this question.",
    "Siz bu savolga allaqachon javob bergansiz.")
add("test_results",
    "<b>📊 Test #{id} results</b> — {title}\nAnswered: {answered}/{students}\n",
    "<b>📊 #{id} test natijalari</b> — {title}\nJavob berganlar: {answered}/{students}\n")
add("test_result_line", "{place}. {name} — {score}/{total}", "{place}. {name} — {score}/{total}")
add("test_no_answers", "Nobody answered this test.", "Bu testga hech kim javob bermadi.")
add("test_personal_result", "📊 Test #{id}: <b>{score}/{total}</b> correct.",
    "📊 №{id} test: <b>{total} tadan {score} ta</b> to'g'ri.")
add("test_list_title", "<b>📝 My tests</b>", "<b>📝 Testlarim</b>")
add("test_list_line", "#{id} {title} — {count} q · {status}",
    "№{id} {title} — {count} savol · {status}")
add("test_status_draft", "draft", "qoralama")
add("test_status_scheduled", "scheduled for {when}", "{when} ga rejalashtirilgan")
add("test_status_running", "running", "davom etmoqda")
add("test_status_finished", "finished", "tugagan")
add("test_needs_topic",
    "🧵 Tip: send this command inside your Test topic and I will keep posting "
    "there automatically.",
    "🧵 Maslahat: bu buyruqni Test mavzusida yuboring — keyin o'sha joyga "
    "o'zim joylab turaman.")


# --------------------------------------------------------------------------
# Diagnostics / roster
# --------------------------------------------------------------------------
add("check_title", "<b>🔧 System check</b>", "<b>🔧 Tizim tekshiruvi</b>")
add("check_ai_on", "✅ AI checking: ON ({model})", "✅ AI tekshiruvi: YOQILGAN ({model})")
add("check_ai_off", "❌ AI checking: OFF — add OPENAI_API_KEY to .env",
    "❌ AI tekshiruvi: O'CHIQ — .env fayliga OPENAI_API_KEY qo'shing")
add("check_worker",
    "⚙️ AI queue: {queue} waiting · {done} checked · {failed} failed",
    "⚙️ AI navbati: {queue} kutilmoqda · {done} tekshirildi · {failed} xato")
add("check_privacy",
    "⚠️ If photos are not checked, disable privacy mode in @BotFather "
    "(/setprivacy → Disable) and make the bot an admin in this group.",
    "⚠️ Rasm tekshirilmasa, @BotFather da privacy rejimini o'chiring "
    "(/setprivacy → Disable) va botni guruhga admin qiling.")
add("check_schedule", "🗓 Timetable entries: {count}", "🗓 Jadvaldagi darslar: {count}")
add("check_students", "👥 Students: {count}", "👥 O'quvchilar: {count}")
add("check_active", "📚 Active assignments: {count}", "📚 Faol vazifalar: {count}")
add("check_lang", "🌐 Language: {lang}", "🌐 Til: {lang}")
add("id_info", "👤 Your id: <code>{user_id}</code>\n💬 Chat id: <code>{chat_id}</code>",
    "👤 Sizning ID: <code>{user_id}</code>\n💬 Chat ID: <code>{chat_id}</code>")
add("st_no_class",
    "I could not find you in any class group. Write <code>/start</code> in your class group first.",
    "Sizni biror guruhda topa olmadim. Avval guruhda <code>/start</code> yozing.")
add("roster_title", "<b>👥 Class roster</b>", "<b>👥 Guruh a'zolari</b>")
add("roster_empty", "Nobody has written /start in the group yet.",
    "Hozircha hech kim guruhda /start yozmagan.")
add("roster_line", "• {name} — {role}{extra}", "• {name} — {role}{extra}")
add("roster_usage",
    "Usage: <code>/roster teacher @user</code> | <code>/roster student @user</code> | "
    "<code>/roster remove @user</code>",
    "Foydalanish: <code>/roster teacher @user</code> | <code>/roster student @user</code> | "
    "<code>/roster remove @user</code>")
add("roster_promoted", "✅ {name} is now a {role}.", "✅ {name} endi {role}.")
add("roster_role_teacher", "teacher", "o'qituvchi")
add("roster_role_student", "student", "o'quvchi")
add("menu_title", "<b>What would you like to do?</b>", "<b>Nima qilmoqchisiz?</b>")
add("welcome_group",
    "👋 Hello! I am the English homework bot.\nSend <code>/start</code> so I can see you, "
    "then send your homework as text or a photo.",
    "👋 Salom! Men ingliz tili vazifalari botiman.\nMen sizni ko'rishim uchun "
    "<code>/start</code> yozing, keyin vazifani matn yoki rasm ko'rinishida yuboring.")
add("welcome_private",
    "👋 Hello, {name}!\nThis bot checks English homework. Add me to your class group "
    "and use <code>/help</code>.",
    "👋 Salom, {name}!\nBu bot ingliz tili vazifalarini tekshiradi. Meni guruhga qo'shib, "
    "<code>/help</code> dan foydalaning.")

# --------------------------------------------------------------------------
# Blok 4: voice answers, confirmation buttons, parent links, mini app
# --------------------------------------------------------------------------
add("btn_submitted", "📤 I sent it", "📤 Topshirdim")
add("btn_not_yet", "✏️ Not yet", "✏️ Hali emas")
add("btn_parent_link", "👨‍👩‍👦 Send the report to the parent",
    "👨‍👩‍👦 Hisobotni ota-onaga yuborish")
add("btn_open_dashboard", "📊 Open the dashboard", "📊 Panelni ochish")

add("voice_listening", "🎤 I am listening to your voice answer…", "🎤 Ovozingiz yozib olinmoqda…")
add("voice_saved",
    "🎤 I heard: <i>{text}</i>",
    "🎤 Sizning ovozingiz: <i>{text}</i>")
add("voice_empty",
    "🎤 I could not hear anything in that voice message. Please write the answer or "
    "send a clear photo.",
    "🎤 Ovozli xabaringizda hech narsani eshitdim. Iltimos, javobni yozing yoki "
    "aniq rasm yuboring.")
add("voice_too_big",
    "🎤 That voice message is too long for me to read. Send a shorter one or write "
    "the answer.",
    "🎤 Ovozli xabaringiz juda uzun. Qisqaroq yuboring yoki javobni yozing.")
add("voice_not_ready",
    "🎤 Voice answers are not switched on yet — please write the answer or send a photo.",
    "🎤 Ovozli javoblar hali yoqiq — javobni yozing yoki rasm yuboring.")

add("sub_confirm_ask",
    "📥 Saved as <b>#{id}</b>. Press <b>📤 Topshirdim</b> when this is your final "
    "version, or <b>✏️ Hali emas</b> to send it again.",
    "📥 <b>#{id}</b> sifatida saqlandi. Bu yakuniy variant bo'lsa <b>📤 Topshirdim</b>, "
    "yana yubormoqchi bo'sangiz <b>✏️ Hali emas</b> ni bosing.")
add("sub_confirm_ok", "👍 Confirmed — checking it now.", "👍 Tasdiqlandi — tekshirilyapti.")
add("sub_confirm_cancelled", "🗑 Removed. Send it again whenever you are ready.",
    "🗑 O'chirildi. Tayyor bo'lgach yana yuboring.")
add("sub_confirm_denied", "That button is not yours.", "Bu tugma sizniki emas.")
add("sub_confirm_missing", "This submission is no longer waiting for confirmation.",
    "Bu ish tasdiqlashni kutayotgani yo'q.")

add("parent_link_ready",
    "🔗 Tap the button below — the parent opens the report with one tap. "
    "Only teachers of this group can use it.",
    "🔗 Pastdagi tugmani bosing — ota-ona hisobotni bir bosishda ochadi. "
    "Faqat shu guruhning o'qituvchilari foydalanishi mumkin.")
add("parent_link_no_username",
    "⚠️ I don't know my own @username. Write <code>BOT_USERNAME=@yourbot</code> into "
    "the <code>.env</code> file and try again.",
    "⚠️ O'z @username nomimni bilmayman. <code>.env</code> fayliga "
    "<code>BOT_USERNAME=@yourbot</code> yozib, qayta urinib ko'ring.")
add("parent_link_sent", "👨‍👩‍👦 The report is ready below — share it with the parent.",
    "👨‍👩‍👦 Hisobot pastda tayyor — ota-onaga yuboring.")
add("parent_link_denied",
    "⛔ This report belongs to a group you do not manage.",
    "⛔ Bu hisobot siz boshqarmaydigan guruhga tegishli.")
add("parent_link_unknown", "The link is broken — ask the teacher for a new one.",
    "Havola buzilgan — o'qituvchidan yangisini so'rang.")

add("app_open_title", "📊 <b>Class dashboard</b>", "📊 <b>Guruh paneli</b>")
add("app_open_off",
    "📊 The dashboard is switched off. Set <code>MINIAPP_ENABLED=true</code> and "
    "<code>MINIAPP_TOKEN=...</code> in <code>.env</code>.",
    "📊 Panel o'chirilgan. <code>.env</code> fayliga <code>MINIAPP_ENABLED=true</code> va "
    "<code>MINIAPP_TOKEN=...</code> qo'ying.")
add("app_open_https",
    "📊 The dashboard runs on <b>{url}</b>.\nTelegram only opens web apps over "
    "<b>https</b> — put a reverse proxy or a tunnel in front of it, then use "
    "<code>MINIAPP_PUBLIC_URL=https://…</code> in <code>.env</code>.",
    "📊 Panel <b>{url}</b> manzilida ishlayapti.\nTelegram web app'ni faqat "
    "<b>https</b> orqali ochadi — oldiga reverse proxy yoki tunnel qo'ying, keyin "
    "<code>.env</code> da <code>MINIAPP_PUBLIC_URL=https://…</code> belgilang.")
add("app_pick_group", "🏫 Which group?", "🏫 Qaysi guruh?")
add("app_chat_title", "🏫 <b>{title}</b>", "🏫 <b>{title}</b>")







