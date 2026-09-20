# Custom Demonlist Bot — Top 150

Własna Demonlista Discord z leaderboardem graczy i automatycznym przyznawaniem punktów po weryfikacji rekordu.

## Funkcje
- Top 150 leveli
- `/top`
- `/leaderboard`
- `/level`
- `/player`
- admin: `/admin addlevel`
- admin: `/admin removelevel`
- admin: `/admin record`
- admin: `/admin verify`
- domyślnie #1 = 150 pkt, #150 = 1 pkt
- przy `/admin addlevel` można podać własną liczbę punktów
- punkty z verified rekordów automatycznie tworzą Player Leaderboard
- SQLite zapisuje dane lokalnie w `demonlist.db`

## Uruchomienie
1. Python 3.10+.
2. `pip install -r requirements.txt`
3. Skopiuj `.env.example` jako `.env`.
4. Wpisz token bota, ID serwera i opcjonalnie ID roli admina.
5. `python bot.py`

Jeśli `ADMIN_ROLE_ID` jest ustawione, tylko osoby z tą rolą mogą używać komend `/admin`.
Jeśli jest `0`, wymagane jest uprawnienie Manage Server.

**Nie udostępniaj tokena bota.** Jeśli wycieknie, zregeneruj go w Discord Developer Portal.
