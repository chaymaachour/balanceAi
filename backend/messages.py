"""Notification and encouragement texts in French, English and Tunisian Derja.

Messages are chosen according to the proximity of the exam and the revision
progress, and rotate deterministically (by date/subject) to avoid sending the
same sentence every day. No guilt, no pressure, no medical claims.
"""
from __future__ import annotations

import zlib

TEXTS = {
    "fr": {
        "day_end_title": "Ta journée est terminée 💜",
        "day_end": [
            "Coucou 💜 Ta journée est terminée ! J'espère qu'elle s'est bien passée. Est-ce qu'il y a quelque chose qui t'a stressée ou dérangée aujourd'hui ? Si tu en as envie, tu peux en parler avec BalanceAI.",
            "Te voilà enfin au calme 🌷 Comment s'est passée ta journée ? Prends deux minutes pour faire ton bilan, si tu en as envie.",
            "Bravo pour cette journée 🌿 Si quelque chose t'a pesé aujourd'hui, BalanceAI est là pour t'écouter.",
        ],
        "wellness_title": "Petit moment pour toi 🌿",
        "wellness": ["Comment te sens-tu aujourd'hui ? Un petit check-in de deux minutes peut aider à y voir plus clair.",
                     "Prends une pause et une grande respiration 💜 Tu veux faire ton bilan du jour ?"],
        "session_title": "Révision dans 10 minutes 📚",
        "session": ["Ta session de {subject} commence à {start} ({minutes} min). Installe-toi tranquillement, un pas à la fois.",
                    "Dans 10 minutes : {subject} ({minutes} min). Prépare ton eau et ton bureau, tu vas y arriver 🌷"],
        "check_title": "Ta session est terminée ?",
        "check": ["Tu as pu faire ta session de {subject} ? Marque-la comme faite, ou dis-moi si elle est manquée : je te proposerai un autre créneau, sans stress.",
                  "Petit point sur {subject} : session faite ou à replanifier ? Les deux sont ok 💜"],
        "resched_title": "Nouveau créneau proposé",
        "resched": ["Pas de souci pour la session manquée 💜 Je t'ai proposé un nouveau créneau pour {subject} : {date} à {start}."],
        "empty_title": "Ton planning de révision est vide",
        "empty": ["Ton examen de {subject} approche et aucun créneau de révision n'est prévu. On crée un planning ensemble ? Ça prend une minute."],
        "examday_title": "C'est le jour J 🌷",
        "examday": ["Bon courage pour {subject} aujourd'hui ! Respire profondément : tu as fait de ton mieux pour te préparer 💜"],
        "test_title": "Test de notification",
        "test_body": "Les notifications BalanceAI fonctionnent 💜",
        "private_title": "BalanceAI",
        "private_body": "Tu as un petit rappel 💜 Ouvre BalanceAI pour le voir.",
        "enc_far": ["Tu as encore du temps pour {subject} : quelques sessions régulières suffiront, sans te surcharger.",
                    "Commencer tôt {subject}, c'est se faire un cadeau pour plus tard 🌱"],
        "enc_week": ["Ton examen de {subject} est dans {days} jours. Une session courte aujourd'hui, et tu avances déjà.",
                     "{subject} dans {days} jours : petit à petit, tu y arrives. Choisis un chapitre et commence par 25 minutes."],
        "enc_soon": ["L'examen de {subject} approche ({days} jours), mais tu peux encore réviser une petite partie. Choisis une matière et commence par 25 minutes de concentration.",
                     "Ne t'inquiète pas, étape par étape tu peux faire beaucoup. Tu as un peu de temps pour réviser {subject} aujourd'hui ?"],
        "enc_tomorrow": ["{subject}, c'est demain 🌷 Revois les points essentiels, puis repose-toi bien : le sommeil fait aussi partie des révisions."],
        "enc_today": ["Bon courage pour {subject} aujourd'hui 💜 Tu as fait de ton mieux."],
        "enc_low": ["Pas de jugement : une petite étape faisable aujourd'hui vaut mieux qu'un grand plan qui fait peur."],
        "enc_good": ["Bravo, tu as déjà bien avancé 🌷 Continue à ton rythme."],
        "coach_step_chapter": "Réviser « {ch} » : relire, faire une fiche courte, 2 exercices",
        "coach_generic_1": "Faire la liste des chapitres et cocher ceux déjà connus",
        "coach_generic_2": "Revoir le chapitre le plus important avec une fiche résumé",
        "coach_generic_3": "Faire des exercices ou un ancien sujet",
        "coach_step_selftest": "Mini auto-test : expliquer les notions clés à voix haute",
        "coach_tip": "Travaille par blocs de 25 à 45 minutes avec une vraie pause, et garde tes heures de sommeil.",
    },
    "en": {
        "day_end_title": "Your day is done 💜",
        "day_end": [
            "Hi 💜 Your day is over! I hope it went well. Did anything stress or bother you today? If you feel like it, you can talk about it with BalanceAI.",
            "You're finally home and calm 🌷 How was your day? Take two minutes for your check-in, if you want.",
            "Well done for today 🌿 If something weighed on you, BalanceAI is here to listen.",
        ],
        "wellness_title": "A little moment for you 🌿",
        "wellness": ["How are you feeling today? A two-minute check-in can help you see more clearly.",
                     "Take a break and a deep breath 💜 Would you like to do your daily check-in?"],
        "session_title": "Revision in 10 minutes 📚",
        "session": ["Your {subject} session starts at {start} ({minutes} min). Settle in calmly, one step at a time.",
                    "In 10 minutes: {subject} ({minutes} min). Grab some water, you've got this 🌷"],
        "check_title": "Is your session done?",
        "check": ["Did you manage your {subject} session? Mark it done, or tell me it was missed and I'll suggest a new slot, no stress.",
                  "Quick check on {subject}: done or to reschedule? Both are okay 💜"],
        "resched_title": "New slot suggested",
        "resched": ["No worries about the missed session 💜 I suggested a new slot for {subject}: {date} at {start}."],
        "empty_title": "Your revision plan is empty",
        "empty": ["Your {subject} exam is coming up and no revision slot is planned. Shall we create a plan together? It takes a minute."],
        "examday_title": "It's exam day 🌷",
        "examday": ["Good luck with {subject} today! Breathe deeply: you did your best to prepare 💜"],
        "test_title": "Test notification",
        "test_body": "BalanceAI notifications are working 💜",
        "private_title": "BalanceAI",
        "private_body": "You have a gentle reminder 💜 Open BalanceAI to see it.",
        "enc_far": ["You still have time for {subject}: a few regular sessions will do, without overloading yourself.",
                    "Starting {subject} early is a gift to your future self 🌱"],
        "enc_week": ["Your {subject} exam is in {days} days. One short session today and you're already moving forward.",
                     "{subject} in {days} days: little by little, you'll get there. Pick a chapter and start with 25 minutes."],
        "enc_soon": ["The {subject} exam is close ({days} days), but you can still review a small part. Pick one topic and start with 25 focused minutes.",
                     "Don't worry, step by step you can do a lot. Do you have a little time for {subject} today?"],
        "enc_tomorrow": ["{subject} is tomorrow 🌷 Review the essentials, then rest well: sleep is part of revising too."],
        "enc_today": ["Good luck with {subject} today 💜 You did your best."],
        "enc_low": ["No judgement: one small doable step today beats a big scary plan."],
        "enc_good": ["Well done, you've already made great progress 🌷 Keep going at your own pace."],
        "coach_step_chapter": "Revise \"{ch}\": re-read, make a short summary sheet, 2 exercises",
        "coach_generic_1": "List the chapters and tick the ones you already know",
        "coach_generic_2": "Review the most important chapter with a summary sheet",
        "coach_generic_3": "Do exercises or a past paper",
        "coach_step_selftest": "Mini self-test: explain the key ideas out loud",
        "coach_tip": "Work in 25-45 minute blocks with real breaks, and protect your sleep.",
    },
    "tn": {
        "day_end_title": "نهارك وفى 💜",
        "day_end": [
            "عسلامة 💜 نهارك وفى! إن شاء الله تعدّى بخير. فمّا حاجة قلقتك ولا ضايقتك اليوم؟ كان تحب، تنجم تحكي عليها مع BalanceAI.",
            "وصلت للدار وارتحت شوية 🌷 كيفاش تعدّى نهارك؟ خذ دقيقتين وعمل البيلان متاعك كان تحب.",
        ],
        "wellness_title": "لحظة صغيرة ليك 🌿",
        "wellness": ["كيفاش تحس روحك اليوم؟ تشيك-إن صغير في دقيقتين ينجم يعاونك."],
        "session_title": "مراجعة بعد 10 دقايق 📚",
        "session": ["حصة {subject} تبدا على {start} ({minutes} دقيقة). قعد على روحك بالشوية، خطوة بخطوة."],
        "check_title": "كمّلت الحصة؟",
        "check": ["عملت حصة {subject}؟ علّمها كمّلتها، ولا قلّي فاتتك ونلقالك وقت آخر، بلاش ستراس."],
        "resched_title": "وقت جديد للمراجعة",
        "resched": ["ما عليهش على الحصة اللي فاتت 💜 لقيتلك وقت جديد لـ {subject}: {date} على {start}."],
        "empty_title": "برنامج المراجعة فارغ",
        "empty": ["عندك امتحان قريب في {subject}؟ خلّينا نعملوا برنامج مراجعة حسب الوقت اللي مازال عندك."],
        "examday_title": "اليوم نهار الامتحان 🌷",
        "examday": ["ربي معاك في {subject} اليوم! تنفّس بالشوية، عملت اللي عليك 💜"],
        "test_title": "تجربة إشعار",
        "test_body": "الإشعارات متاع BalanceAI تخدم 💜",
        "private_title": "BalanceAI",
        "private_body": "عندك تذكير صغير 💜 حلّ BalanceAI باش تشوفو.",
        "enc_far": ["مازال عندك الوقت لـ {subject}: شوية حصص منظّمة يكفيو، من غير ما تتعب روحك."],
        "enc_week": ["امتحان {subject} بعد {days} أيام. حصة صغيرة اليوم وتوّا تقدّمت."],
        "enc_soon": ["الامتحان قرّب ({days} أيام)، أما مازال تنجّم تراجع جزء صغير. اختار مادة وابدأ بـ 25 دقيقة تركيز.",
                     "ربي معاكم 💜 ما تخافوش، خطوة بخطوة تنجّموا تعملوا برشا. عندكم شوية وقت للمراجعة اليوم؟"],
        "enc_tomorrow": ["{subject} غدوة 🌷 راجع أهم النقاط وبعد ارتاح مليح: النوم زادة من المراجعة."],
        "enc_today": ["ربي معاك في {subject} اليوم 💜"],
        "enc_low": ["بلاش حكم على روحك: خطوة صغيرة اليوم خير من برنامج كبير يخوّف."],
        "enc_good": ["برافو عليك! تقدّمت برشا 🌷 كمّل على راحتك."],
        "coach_step_chapter": "راجع « {ch} »: اقرا، اعمل فيش صغيرة، و2 تمارين",
        "coach_generic_1": "اكتب قائمة الشابيترات وعلّم اللي تعرفهم",
        "coach_generic_2": "راجع أهم شابيتر بفيش ملخّص",
        "coach_generic_3": "اعمل تمارين ولا امتحان قديم",
        "coach_step_selftest": "تيست صغير: فسّر الأفكار المهمة بصوت عالي",
        "coach_tip": "خدم بحصص من 25 لـ 45 دقيقة مع راحة حقيقية، وحافظ على نومك.",
    },
}


def t(lang: str, key: str):
    return TEXTS.get(lang, TEXTS["fr"]).get(key) or TEXTS["fr"][key]


def pick(lang: str, key: str, seed: str = "", **fmt) -> str:
    pool = t(lang, key)
    if isinstance(pool, list):
        pool = pool[zlib.crc32(seed.encode("utf-8")) % len(pool)]
    return pool.format(**fmt) if fmt else pool


def encouragement(lang: str, days_left, percent: int, subject: str, seed: str = "") -> str:
    """Encouragement adapted to exam proximity and revision progress."""
    if days_left is None or days_left > 7:
        key = "enc_far"
    elif days_left <= 0:
        key = "enc_today"
    elif days_left == 1:
        key = "enc_tomorrow"
    elif days_left <= 3:
        key = "enc_soon"
    else:
        key = "enc_week"
    msg = pick(lang, key, seed, subject=subject, days=days_left)
    if days_left is not None and days_left > 0:
        if percent >= 60:
            msg += " " + pick(lang, "enc_good", seed)
        elif percent < 20 and days_left <= 7:
            msg += " " + pick(lang, "enc_low", seed)
    return msg
