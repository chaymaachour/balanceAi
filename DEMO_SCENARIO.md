# BalanceAI — Live demo scenario (≈ 3 minutes)

## Before going on stage (5 minutes before)
1. Launch the app (`run.bat` on Windows or `./run.sh`) and open **http://localhost:5000**.
2. Check the badge in the top-right corner:
   - green **"Real AI active"** → AI is configured;
   - yellow **"Demo mode"** → no key / no internet. The demo still works; say honestly that results are from the local demo mode.
3. Do one test check-in so the AI provider is "warmed up", then click **"Clear my data"** in the footer to start fresh (or keep a few real check-ins if you want to show the chart).
4. Choose the interface language (FR/EN button) that matches the jury. Zoom the browser to 110-125 % for visibility.
5. Close other tabs and mute *other* apps' notifications (keep the browser's). Never show the `.env` file.
6. The day before: complete the onboarding (Lycée or Université), enable browser notifications (bell → Enable → Allow) and click **Send a test** once to be sure the permission is granted on the demo PC. Keep the terminal running during the whole demo (it sends the reminders).

## On stage

**1. Home (20 s)** — "This is BalanceAI, a calm space for everyday stress, designed for young Tunisian women students and graduates, but useful for anyone." Point to the disclaimer: support, not diagnosis. Click **Start my wellness check-in**.

**2. Check-in (40 s)** — Click the example **"Français"** (or type your own). It selects *Overwhelmed* + *Studies* and fills a realistic text about the PFE, exams, sleep and family pressure. Mention: "You can also write in Derja or Arabizi" (show the **Derja** example if time allows). Click **Analyze my check-in**.

**3. AI analysis (50 s)** — Show the green banner "Analyzed by real AI · provider · model". Walk through:
- emotions with confidence levels and *evidence quoting the user's words*,
- stress signals, practical challenges,
- 3 personalised suggestions and **one small next step**.
Say: "The AI never diagnoses — it offers possibilities." Click 👍 to show the feedback loop.

**4. Planner (50 s)** — Click **Turn this into a plan**: tasks extracted by the AI appear in the planner and the stress level is pre-set from the mood. Choose **4 h**, click **Generate my plan**. Show short sessions, breaks, a healthy-habit block, and the "This can wait" section if the workload is too high. Tick the first block ✔ → progress bar + encouragement. Then change the stress to 3 and time to 8 h and click **Regenerate** to show the plan adapts.

**5. Relax (20 s)** — Open **Relax**, press **Start**: the circle breathes with "Breathe in / Hold / Breathe out". Press **Pause** to show you can stop anytime.

**6. Progress (15 s)** — Open **My progress**: mood chart for the week, habits, gentle observations computed only from recorded data. Mention privacy: everything stays in the browser, "Clear my data" deletes it.

**7. Studies: calendar → exam → revisions → notification (60 s, new)** — Open **Calendar**: the Lycée/Université timetable prepared beforehand (show **Edit my timetable**, add a club on Wednesday 17:00 → overlapping it shows the conflict warning). Tap a day → **Cancelled this day** on a class: the bell time under the day updates (end of classes + way home + rest). Open **Exams**, add *Maths, in 6 days, Intégrales difficult* → the plan is created instantly. Click **Study steps** (AI coach, green or clearly-labelled demo banner). Open **Revisions**: sessions only after classes, never at night; click **Missed** on one → "No worries, new slot: …". Finally **Notifications → Send a test**: a real browser notification pops up.

**Closing line:** "BalanceAI turns *I'm overwhelmed* into *here is my next small step* — a little more balance, one day at a time."

## Backup plan
- **No internet / AI error:** the app automatically falls back to demo mode and says so. Explain: "Without connection we show the transparent local fallback; with the key, the real AI analysis you saw in our screenshots runs."
- Prepare 2-3 screenshots of a real AI analysis in your slides in case the network fails.
- **Push notification does not appear:** the in-app notification centre still shows it; check that Windows "Focus assist / Do not disturb" is off and that the page is opened via `http://localhost:5000`.
- If the safety topic comes up: typing a crisis sentence shows the emergency card (SAMU 190) — avoid demonstrating it live unless asked.
