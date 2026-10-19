# Notes de fusion
- La v2 contient tous les fichiers de la v1 (aucune fonction JS, route API ni page de la v1 absente de la v2 : vérifié par comparaison). La base de travail est donc la v2 ; la v1 n'a rien perdu.
- Remplacé volontairement : l'identité par « code d'appareil » (en-tête X-BalanceAI-User, restauration par code). Elle permettait d'accéder aux données de n'importe qui connaissant le code ; remplacée par les comptes. Les anciennes données sont rattachables à l'inscription.
- Remplacé : `tests/e2e_smoke.py` (basé sur le code d'appareil) par `tests/e2e_browser.py`. Les autres tests v2 sont conservés et adaptés à la connexion obligatoire.
- `DELETE /api/me` exige maintenant le mot de passe ; `POST /api/me/reset` efface planning/examens/notifications sans supprimer le compte.
- Ajoutés : `backend/auth.py`, `backend/chat_api.py`, migration 2, `frontend/js/auth.js`, `chat.js`, `i18n-chat.js`, page Assistant.
