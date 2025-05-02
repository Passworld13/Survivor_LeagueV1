import logging
import datetime
import json
import secrets
import base64
from base58 import b58decode
import nacl.signing
import nacl.exceptions
import telebot
from telebot import types
import requests
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


# Configuration
API_TOKEN = '7740869260:AAF92N039RvJGMyqksAKwh2yxJ3g8KyncpU'  # Token du Bot
ADMIN_ID = 5247720666  # Ton ID Telegram (admin)
bot = telebot.TeleBot(API_TOKEN)

API_KEY = "c53fdd80-a73f-472d-9a71-04b25f41a98b"
COLLECTION_ID = "21ac9f6e-9b28-41ab-90e8-a654b285325b"

SUPABASE_URL = "https://viiksbknchgarfcmolil.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZpaWtzYmtuY2hnYXJmY21vbGlsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUzMjQ1NTcsImV4cCI6MjA2MDkwMDU1N30.oN7sR8zyom71ocn3mJFUW4QxKuCca5JDWqicom4EEhU"
from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)

# Global state
CURRENT_GAME_WEEK = 0  # Semaine de jeu courante (0 si aucune démarrée)
user_nonces = {}       # Stocke les messages de vérification en attente par user

def is_admin(user_id: int) -> bool:
    """Vérifie si l'ID utilisateur correspond à l'admin."""
    return user_id == ADMIN_ID

def get_current_week() -> int:
    """Retourne la Game Week courante."""
    return CURRENT_GAME_WEEK

def escape_markdown_v2(text: str) -> str:
    """Échappe les caractères spéciaux pour Markdown V2."""
    special_chars = r'_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!'
    return re.sub(f'([{special_chars}])', r'\\\1', text)

def parse_results(text: str) -> dict:
    """
    Parse le texte des résultats (format: 'Team1 vs Team2 X-Y, ...')
    Retourne un dict {team: {"result": "W/L/D", "score": "a-b"}} par équipe.
    """
    results = {}
    matches = [m.strip() for m in text.split(',') if m.strip()]
    for match in matches:
        m = re.match(r"(.+?) vs (.+?) (\d+-\d+)$", match)
        if not m:
            return None
        team1 = m.group(1).strip()
        team2 = m.group(2).strip()
        score_str = m.group(3).strip()
        if '-' not in score_str:
            return None
        try:
            score1, score2 = score_str.split('-', 1)
            score1 = int(score1)
            score2 = int(score2)
        except ValueError:
            return None
        # Déterminer gagnant/perdant/nul
        if score1 > score2:
            res1, res2 = "W", "L"
        elif score1 < score2:
            res1, res2 = "L", "W"
        else:
            res1, res2 = "D", "D"
        results[team1] = {"result": res1, "score": f"{score1}-{score2}"}
        results[team2] = {"result": res2, "score": f"{score2}-{score1}"}
    return results

def save_results(results_dict: dict):
    """Sauvegarde les résultats dans le fichier JSON, par GameWeek."""
    file_path = "results.json"
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    data[f"GW{CURRENT_GAME_WEEK}"] = results_dict
    with open(file_path, 'w') as f:
        json.dump(data, f)
    logging.info(f"Résultats de la GW{CURRENT_GAME_WEEK} sauvegardés.")

def update_points_from_results():
    """Calcule et met à jour les points des utilisateurs en fonction des résultats."""
    try:
        with open("results.json", "r") as f:
            all_results = json.load(f)
    except FileNotFoundError:
        all_results = {}
    week_key = f"GW{CURRENT_GAME_WEEK}"
    week_results = all_results.get(week_key, {})
    picks_res = supabase.table('picks').select('*').eq('week', CURRENT_GAME_WEEK).execute()
    picks = picks_res.data if picks_res.data else []
    for pick in picks:
        user_id = str(pick['user_id'])
        team = pick['team']
        prediction = pick.get('prediction', None)
        points = 0
        match_result = week_results.get(team)
        if match_result:
            if match_result.get('result') == 'W':
                points += 1
            if prediction and match_result.get('score') == prediction:
                points += 3
        timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
        data = {"user_id": user_id, "team": team, "week": CURRENT_GAME_WEEK, "points": points, "updated_at": timestamp}
        res = supabase.table('points').insert(data).execute()
        if res.status_code != 201:
            supabase.table('points').update({"points": points, "updated_at": timestamp}).eq("user_id", user_id).eq("week", CURRENT_GAME_WEEK).execute()
    logging.info(f"Points mis à jour pour la GW{CURRENT_GAME_WEEK}.")

def update_leaderboard_monthly():
    """Mise à jour du leaderboard mensuel (cumul points par mois calendrier)."""
    month = datetime.datetime.utcnow().month
    points_data = supabase.table("points").select("*").execute().data or []
    leaderboard = {}
    for entry in points_data:
        user_id = entry['user_id']
        leaderboard[user_id] = leaderboard.get(user_id, 0) + entry['points']
    for user_id, total in leaderboard.items():
        supabase.table('leaderboard_monthly').upsert({
            "user_id": user_id,
            "month": month,
            "points": total
        }, on_conflict="user_id").execute()
    logging.info("Leaderboard mensuel mis à jour.")

def update_leaderboard_yearly():
    """Mise à jour du leaderboard annuel (cumul points par année)."""
    year = datetime.datetime.utcnow().year
    points_data = supabase.table("points").select("*").execute().data or []
    leaderboard = {}
    for entry in points_data:
        user_id = entry['user_id']
        leaderboard[user_id] = leaderboard.get(user_id, 0) + entry['points']
    for user_id, total in leaderboard.items():
        supabase.table('leaderboard_yearly').upsert({
            "user_id": user_id,
            "year": year,
            "points": total
        }, on_conflict="user_id").execute()
    logging.info("Leaderboard annuel mis à jour.")

# ----------------- Handlers Utilisateur -----------------
@bot.message_handler(commands=["start"])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🪪 Connect Survivor Wallet", url="https://survivor-league-v1.vercel.app")
    )

    bot.send_message(
        message.chat.id,
        "👋 Welcome to Survivor League!\n\nClick the button below to connect your wallet 👇",
        reply_markup=markup
    )

    welcome_message = (
        "👋 *Welcome to Survivor League!*\n\n"
        "Each week, pick a team you believe will *win*.\n"
        "⚽ If they win, you *survive*. If they *lose or draw*, you're *eliminated by the Kraken* (or Burn 3 points).\n\n"
        "🔥 *Monthly survivors* split rewards (50% of the pool).\n"
        "🏆 *Top 11 and Top 25%* at the end of the season share the Season Pool (remaining 50%).\n\n"
        "🎮 Ready to kick off?\nClick below to get started 👇"
    )

    bot.send_message(message.chat.id, welcome_message, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(content_types=['web_app_data'])
def handle_webapp_data(message):
    data = message.web_app_data.data
    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        payload = json.loads(data)
        action = payload.get("action")
        wallet_address = payload.get("address")
        signature_b64 = payload.get("signature")
        signed_message = payload.get("message")

        if not (wallet_address and signature_b64 and signed_message):
            bot.send_message(chat_id, "⚠️ Incomplete data received. Please try again.")
            return
        if not signed_message.startswith("Survivor League Verification"):
            bot.send_message(chat_id, "⚠️ Invalid signed message format.")
            return

        # Decode public key and signature
        pubkey_bytes = base58.b58decode(wallet_address)
        signature_bytes = base64.b64decode(signature_b64)

        # Verify signature
        try:
            verify_key = nacl.signing.VerifyKey(pubkey_bytes)
            verify_key.verify(signed_message.encode(), signature_bytes)
        except nacl.exceptions.BadSignatureError:
            bot.send_message(chat_id, "❌ Invalid signature. Wallet not verified.")
            return

        # Signature is valid, save to Supabase
        supabase.table("users").upsert({
            "telegram_id": str(user_id),
            "wallet_address": wallet_address,
            "created_at": datetime.datetime.utcnow().isoformat()
        }, on_conflict="telegram_id").execute()

        bot.send_message(chat_id, "✅ Wallet verified and connected successfully!")

        # Optionally check NFT pass
        if not has_nft_pass(wallet_address):  # À implémenter selon ta logique
            bot.send_message(chat_id, "🎟️ No SURVIVOR PASS detected.\nPlease buy one to join the game.")
        else:
            bot.send_message(chat_id, "🎫 Pass verified. You're ready to play!")
            show_main_menu(chat_id)

    except Exception as e:
        logging.error(f"[web_app_data error] {e}")
        bot.send_message(chat_id, "⚠️ Error verifying your wallet. Please retry.")

def verify_wallet_signature(wallet_address, signature, user_id):
    try:
        # Exemple simple pour Ethereum
        from eth_account.messages import encode_defunct
        from eth_account import Account
        import web3

        message = f"Survivor League Verification: {user_id}"
        encoded_message = encode_defunct(text=message)

        recovered_address = Account.recover_message(encoded_message, signature=signature)

        return recovered_address.lower() == wallet_address.lower()

    except Exception as e:
        print(f"Verification error: {e}")
        return False

def has_nft_pass(wallet_address):
    try:
        # Ici tu dois checker la blockchain. Exemple : requête Helius ou Crossmint API
        url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/nfts?api-key={API_KEY}"
        response = requests.get(url)
        data = response.json()

        # Vérifie la présence de ton NFT spécifique
        for nft in data:
            if nft.get("collection", {}).get("key") == "COLLECTION_ID":
                return True
        return False
    except Exception as e:
        print(f"NFT check error: {e}")
        return False

def prompt_purchase(chat_id):
    markup = types.InlineKeyboardMarkup()
    buy_button = types.InlineKeyboardButton(
        text="🎟️ Buy Survivor Pass",
        web_app=types.WebAppInfo(url="https://ton-site.com/buy_pass?uid={}".format(chat_id))
    )
    markup.add(buy_button)

    bot.send_message(chat_id, "🎫 You need a Survivor Pass NFT to play. Click below to purchase your pass:", reply_markup=markup)
    bot.send_message(chat_id, "🛒 Once you've completed your NFT purchase, come back here and press /start again to verify it.")

def show_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⚽ Pick my Team", callback_data="pick"))
    markup.add(types.InlineKeyboardButton("🎯 View Rewards", callback_data="rewards"))
    markup.add(types.InlineKeyboardButton("📜 Game Rules", callback_data="rules"))

    bot.send_message(chat_id, "✅ Welcome Survivor! Choose your next move 👇", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "connect_wallet")
def connect_wallet_callback(call):
    """Callback du bouton 'Connect Wallet'. Lance la demande de l'adresse du wallet."""
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    # Step 1/3: Prompt for the wallet address
    prompt = bot.send_message(chat_id, "🪪 *Step 1/3:* Please enter your wallet address:", parse_mode="Markdown")
    bot.register_next_step_handler(prompt, process_wallet_address)

def send_verification_message(chat_id: int, user_id: int, wallet_address: str):
    """Envoie le message de vérification à signer par l'utilisateur (Step 2/3)."""
    # Generate a random nonce and store it for this user
    nonce = secrets.token_hex(16)
    user_nonces[user_id] = {"wallet": wallet_address, "nonce": nonce}
    verification_message = f"Survivor League Verification: {nonce}"
    # Step 2/3: Instructions for signing the message
    msg_text = (
        "🖊️ *Step 2/3:* To verify ownership, please sign the message below with your wallet:\n"
        f"`{verification_message}`\n\n"
        "After signing, copy the signature.\n"
        "Then click **✅ I’ve Signed, Confirm Now** below to continue."
    )
    # Inline buttons: help link and confirm action
    markup = types.InlineKeyboardMarkup()
    btn_help = types.InlineKeyboardButton("🧾 How to Sign a Message", url="https://docs.phantom.app/user/transactions/signing-messages")
    btn_confirm = types.InlineKeyboardButton("✅ I’ve Signed, Confirm Now", switch_inline_query_current_chat="/confirm ")
    markup.add(btn_help)
    markup.add(btn_confirm)
    bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=markup)

def process_wallet_address(message):
    """Traite l'adresse du wallet fournie par l'utilisateur (après l'étape 1)."""
    chat_id = message.chat.id
    wallet_address = message.text.strip()
    if not wallet_address:
        bot.reply_to(message, "❌ Invalid address. Please try again.")
        # If empty, the user can be prompted again or restart the flow
        return
    # Proceed to Step 2: send the verification message for signing
    send_verification_message(chat_id, message.from_user.id, wallet_address)

@bot.message_handler(commands=['confirm'])
def confirm(message):
    """Commande /confirm <signature> pour terminer la connexion (Step 3/3)."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if user_id not in user_nonces:
        bot.reply_to(message, "❌ First, use the *Connect Wallet* button to start the process.", parse_mode="Markdown")
        return
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "⚠️ You need to paste the signature after the command.\nExample:\n`/confirm Gp1Yx2...7fqp6U==`", parse_mode="Markdown")
        return
    signature_b64 = parts[1].strip()
    wallet = user_nonces[user_id]["wallet"]
    nonce = user_nonces[user_id]["nonce"]
    try:
        # Decode the signature and verify it against the stored nonce
        signature_bytes = base64.b64decode(signature_b64)
        public_key_bytes = b58decode(wallet)
        verify_key = nacl.signing.VerifyKey(public_key_bytes)
        verify_key.verify(f"Survivor League Verification: {nonce}".encode(), signature_bytes)
        # Save the wallet address in the database (Supabase)
        supabase.table("users").upsert({
            "telegram_id": str(user_id),
            "wallet_address": wallet,
            "created_at": datetime.datetime.utcnow().isoformat()
        }, on_conflict="telegram_id").execute()
        # Success: wallet verified and saved
        bot.reply_to(message, "✅ Wallet saved. You're ready to pick your team!")
        del user_nonces[user_id]  # clear temporary state
        # Present the main menu options to the user
        menu_text = (
            "*Menu:* Now you can use the commands below:\n"
            "• /pick – Choose your team for this week\n"
            "• /rules – View the game rules\n"
            "• /leaderboard – See the current leaderboard\n"
            "• /profile – Check your profile and points"
        )
        bot.send_message(chat_id, menu_text, parse_mode="Markdown")
    except nacl.exceptions.BadSignatureError:
        bot.reply_to(message, "❌ Invalid signature. Please make sure you signed the exact message provided.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {e}")

@bot.message_handler(commands=['savewallet'])
def savewallet(message):
    """Commande /savewallet pour initier le processus de connexion du wallet."""
    chat_id = message.chat.id
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        # No address provided: start interactive Step 1
        prompt = bot.reply_to(message, "🪪 *Step 1/3:* Please enter your wallet address:", parse_mode="Markdown")
        bot.register_next_step_handler(prompt, process_wallet_address)
    else:
        # Address was provided directly with the command
        wallet_address = parts[1].strip()
        # (Optional: validate address format/length here if needed)
        send_verification_message(chat_id, user_id, wallet_address)

# Gère le bouton inline "I've Signed, Confirm Now"
@bot.callback_query_handler(func=lambda call: call.data == "confirm_now")
def confirm_now_callback(call):
    # Accuse réception de l'appui sur le bouton
    bot.answer_callback_query(call.id)
    # Rappelle à l'utilisateur de fournir la signature avec la commande /confirm
    bot.send_message(call.message.chat.id, "⚠️ You need to paste the signature after the command.\nExample:\n/confirm Gp1Yx2...7fqp6U==")

@bot.message_handler(commands=['mywallet'])
def mywallet(message):
    """Affiche le wallet enregistré de l'utilisateur."""
    user_id_str = str(message.from_user.id)
    res = supabase.table("users").select("wallet_address").eq("telegram_id", user_id_str).execute()
    data = res.data
    if data:
        wallet_address = data[0]['wallet_address']
        bot.reply_to(message, f"✅ Your registered wallet: `{wallet_address}`", parse_mode="Markdown")
    else:
        bot.reply_to(message, "⛔️ You haven't registered a wallet yet. Use /savewallet.")

@bot.message_handler(commands=['pick'])
def pick(message):
    """Commande /pick pour choisir son équipe de la semaine."""
    user_id_str = str(message.from_user.id)
    res = supabase.table("users").select("wallet_address").eq("telegram_id", user_id_str).execute()
    if not res.data:
        bot.reply_to(message, "⚠️ Please connect your wallet first using /savewallet.")
        return
    if CURRENT_GAME_WEEK <= 0:
        bot.reply_to(message, "ℹ️ No active Game Week at the moment.")
        return
    matches_res = supabase.table("matches").select("team1, team2").eq("week", CURRENT_GAME_WEEK).execute()
    matches = matches_res.data or []
    if not matches:
        bot.reply_to(message, "ℹ️ No matches found for this week.")
        return
    markup = types.InlineKeyboardMarkup()
    for m in matches:
        team1 = m['team1']; team2 = m['team2']
        btn1 = types.InlineKeyboardButton(team1, callback_data=f"pick_{team1.replace(' ', '_')}")
        btn2 = types.InlineKeyboardButton(team2, callback_data=f"pick_{team2.replace(' ', '_')}")
        markup.add(btn1, btn2)
    bot.reply_to(message, f"Choose your team for Week {CURRENT_GAME_WEEK}:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pick_"))
def pick_team_callback(call):
    """Callback lors du choix d'une équipe via le menu /pick."""
    user_id = call.from_user.id
    user_id_str = str(user_id)
    team_choice = call.data[len("pick_"):].replace('_', ' ')
    existing = supabase.table("picks").select("*").eq("user_id", user_id_str).eq("week", CURRENT_GAME_WEEK).execute()
    if existing.data:
        prev_team = existing.data[0]['team']
        bot.answer_callback_query(call.id)
        bot.reply_to(call.message, f"⚠️ You have already picked **{prev_team}** this week.", parse_mode="Markdown")
        return
    res_user = supabase.table("users").select("wallet_address").eq("telegram_id", user_id_str).execute()
    wallet_address = res_user.data[0]['wallet_address'] if res_user.data else None
    supabase.table("picks").insert({
        "user_id": user_id_str,
        "wallet": wallet_address,
        "team": team_choice,
        "week": CURRENT_GAME_WEEK
    }).execute()
    bot.answer_callback_query(call.id)
    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=None)
    bot.reply_to(call.message, f"✅ Pick saved: {team_choice} for week {CURRENT_GAME_WEEK}. Good luck!")

@bot.message_handler(commands=['leaderboard'])
def leaderboard(message):
    """Commande /leaderboard pour afficher les classements mensuel et annuel."""
    year = datetime.datetime.utcnow().year
    month = datetime.datetime.utcnow().month
    monthly_res = supabase.table("leaderboard_monthly").select("*").eq("month", month).order("points", desc=True).execute()
    monthly_data = monthly_res.data or []
    yearly_res = supabase.table("leaderboard_yearly").select("*").eq("year", year).order("points", desc=True).execute()
    yearly_data = yearly_res.data or []
    leaderboard_text = "*🏆 Monthly Leaderboard:*\n"
    if monthly_data:
        for i, entry in enumerate(monthly_data[:5], start=1):
            uid = entry['user_id']; pts = entry['points']
            user_res = supabase.table("users").select("wallet_address").eq("telegram_id", str(uid)).execute()
            name = user_res.data[0]['wallet_address'] if user_res.data else str(uid)
            if len(name) > 10:
                name = name[:6] + "..." + name[-4:]
            leaderboard_text += f"{i}. {name} — {pts} pts\n"
    else:
        leaderboard_text += "_No data for this month._\n"
    leaderboard_text += "\n*🌍 Season Leaderboard:*\n"
    if yearly_data:
        for i, entry in enumerate(yearly_data[:5], start=1):
            uid = entry['user_id']; pts = entry['points']
            user_res = supabase.table("users").select("wallet_address").eq("telegram_id", str(uid)).execute()
            name = user_res.data[0]['wallet_address'] if user_res.data else str(uid)
            if len(name) > 10:
                name = name[:6] + "..." + name[-4:]
            leaderboard_text += f"{i}. {name} — {pts} pts\n"
    else:
        leaderboard_text += "_No data for this season._"
    bot.reply_to(message, leaderboard_text, parse_mode="Markdown")

@bot.message_handler(commands=['rules'])
def rules(message):
    """Envoie les règles du jeu."""
    rules_text = ("*📜 The 10 Commandments of Survivor League:*\n\n"
                  "1️⃣ Every week, choose one team. If they *win*, you survive in the Survivor Monthly mode.\n"
                  "2️⃣ If your team *loses or draws*, you're eliminated... unless you burn 3 points or use a 'Second Chance' NFT card.\n"
                  "3️⃣ You can only pick each team *once per season*.\n"
                  "4️⃣ A victory = +1 point (+0.5 bonus if you're in a Club), and you survive. +3 points if you guessed the exact score.\n"
                  "5️⃣ One month = 4 Game Weeks. If you survive all 4, you become a *Monthly Survivor*.\n"
                  "6️⃣ Eliminated? You can *still play every week* to earn points for the Season leaderboard — but you’re out of Monthly Survivor rewards.\n"
                  "7️⃣ All Survivors who last the 4 weeks *share equally* the 100% Monthly Reward Pool.\n"
                  "8️⃣ The Season leaderboard adds up *all your points*: wins, bonuses, burns, exacts.\n"
                  "9️⃣ End of season (final European league day): Top 11 players share 50% of the Season pool + exclusive NFT rewards. Extra bonus for Top 3.\n"
                  "🔟 Top 25% of the Season leaderboard *share the remaining 50%* of the Season pool + exclusive rewards.\n\n"
                  "_Tie-breaker: More exact scores > Fewer burned points > Random draw._")
    bot.reply_to(message, rules_text, parse_mode="Markdown")

@bot.message_handler(commands=['rewards'])
def rewards(message):
    """Envoie la description des récompenses."""
    rewards_text = ("*🏆 Survivor League Rewards:*\n\n"
                    "*💰 Monthly Rewards:*\n"
                    "• Survive 4 Game Weeks in a month\n"
                    "• Share *100% of the monthly reward pool* with all Monthly Survivors\n"
                    "• Stay alive to claim your piece of the pie 🍰\n\n"
                    "*📅 Season Rewards:*\n"
                    "• Accumulate points all season (victories, bonuses, exact scores, etc.)\n"
                    "• *Top 11 players* share 50% of the seasonal reward pool\n"
                    "• *Top 3 players* get extra bonuses 🥇🥈🥉\n"
                    "• *Top 25%* of the leaderboard share the other 50% + exclusive NFT rewards\n\n"
                    "_Play smart. Survive. Score high._ ⚔️")
    bot.reply_to(message, rewards_text, parse_mode="Markdown")

@bot.message_handler(commands=['profile'])
def profile_cmd(message):
    """Affiche le profil de l'utilisateur (points, picks...)."""
    user = message.from_user
    user_id_str = str(user.id)
    username = user.username or user.first_name or ""
    gameweek = CURRENT_GAME_WEEK
    year = datetime.datetime.utcnow().year
    month = datetime.datetime.utcnow().month
    res_year = supabase.table("leaderboard_yearly").select("points").eq("user_id", user_id_str).eq("year", year).execute()
    total_points = res_year.data[0]['points'] if res_year.data else 0
    res_month = supabase.table("leaderboard_monthly").select("points").eq("user_id", user_id_str).eq("month", month).execute()
    monthly_points = res_month.data[0]['points'] if res_month.data else 0
    points_data = supabase.table("points").select("points").eq("user_id", user_id_str).execute().data or []
    exacts = sum(1 for p in points_data if p['points'] is not None and p['points'] >= 4)
    burns_used = sum(1 for p in points_data if p['points'] is not None and p['points'] == 0)
    picks_count = len(supabase.table("picks").select("*").eq("user_id", user_id_str).execute().data or [])
    survivor_status = ""
    if gameweek > 0:
        pick_res = supabase.table("picks").select("team").eq("user_id", user_id_str).eq("week", gameweek).execute()
        if not pick_res.data:
            survivor_status = "❌ No pick this GW"
        else:
            pts_res = supabase.table("points").select("points").eq("user_id", user_id_str).eq("week", gameweek).execute()
            if pts_res.data:
                pts = pts_res.data[0]['points']
                survivor_status = "✅ Survived" if pts and pts > 0 else "❌ Eliminated"
            else:
                survivor_status = "⏳ Awaiting results"
    else:
        survivor_status = "❌ No active game"
    username_safe = escape_markdown_v2(username)
    survivor_safe = escape_markdown_v2(survivor_status)
    profile_text = (f"👤 *Profile of @{username_safe}*\n\n"
                    f"🌍 *Global Points:* {total_points}\n"
                    f"📅 *Monthly Points:* {monthly_points}\n"
                    f"🎯 *Exact Score Hits:* {exacts}\n"
                    f"🔥 *Burns Used:* {burns_used}\n"
                    f"✅ *Picks Made:* {picks_count}\n"
                    f"{survivor_safe}")
    bot.reply_to(message, profile_text, parse_mode="MarkdownV2")

# ----------------- Handlers Admin -----------------
@bot.message_handler(commands=['startgameweek'])
def start_gameweek(message):
    """Commande admin pour démarrer une nouvelle GameWeek (demande la liste des matchs)."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Tu n'as pas l'autorisation pour faire ça.")
        return
    global CURRENT_GAME_WEEK
    CURRENT_GAME_WEEK += 1
    msg = bot.reply_to(message, f"✅ Envoie-moi la liste des matchs pour la GameWeek {CURRENT_GAME_WEEK} (ex: Team1 vs Team2, ...)")
    bot.register_next_step_handler(msg, save_gameweek_matches)

def save_gameweek_matches(message):
    """Enregistre les matchs fournis pour la GameWeek courante."""
    if message.text:
        matches_text = message.text
    else:
        return
    matches_list = [m.strip() for m in matches_text.split(',') if m.strip()]
    for match in matches_list:
        if 'vs' not in match:
            bot.reply_to(message, "⚠️ Mauvais format ! Utilise 'Équipe1 vs Équipe2'.")
            return
        team1, team2 = match.split('vs', 1)
        team1 = team1.strip(); team2 = team2.strip()
        supabase.table('matches').insert({"team1": team1, "team2": team2, "week": CURRENT_GAME_WEEK}).execute()
    bot.reply_to(message, f"✅ Matchs enregistrés pour la GameWeek {CURRENT_GAME_WEEK} !")

@bot.message_handler(commands=['add_matches'])
def add_matches_cmd(message):
    """Commande admin pour ajouter des matchs (format direct dans le message)."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Tu n'es pas autorisé à utiliser cette commande.")
        return
    text = message.text.replace('/add_matches', '', 1).strip()
    if not text:
        bot.reply_to(message, "⚠️ Merci de fournir la liste des matchs. Ex: Team1 vs Team2, Team3 vs Team4")
        return
    matches_list = [m.strip() for m in text.split(',') if m.strip()]
    for match in matches_list:
        if 'vs' not in match:
            bot.reply_to(message, "⚠️ Mauvais format ! Utilise 'Équipe1 vs Équipe2'.")
            return
        team1, team2 = match.split('vs', 1)
        team1 = team1.strip(); team2 = team2.strip()
        supabase.table('matches').insert({"team1": team1, "team2": team2, "week": CURRENT_GAME_WEEK}).execute()
    bot.reply_to(message, f"✅ Matchs ajoutés pour la GameWeek {CURRENT_GAME_WEEK} !")

@bot.message_handler(commands=['enter_results'])
def enter_results(message):
    """Commande admin pour entrer les résultats des matchs de la semaine courante."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Tu n'es pas autorisé à utiliser cette commande.")
        return
    text = message.text.replace('/enter_results', '', 1).strip()
    if not text:
        bot.reply_to(message, "⚠️ Merci de fournir les résultats. Ex: Team1 vs Team2 2-0, Team3 vs Team4 1-1")
        return
    results_data = parse_results(text)
    if results_data is None:
        bot.reply_to(message, "⚠️ Format invalide. Utilise: Équipe1 vs Équipe2 score1-score2, ...")
        return
    save_results(results_data)
    update_points_from_results()
    update_leaderboard_monthly()
    update_leaderboard_yearly()
    bot.reply_to(message, "✅ Résultats enregistrés et points mis à jour !")

@bot.message_handler(commands=['set_game_week', 'setweek'])
def set_game_week(message):
    """Commande admin pour définir manuellement la GameWeek courante."""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "🚫 Tu n'es pas autorisé à utiliser cette commande.")
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(message, "⚠️ Usage: /set_game_week <WEEK_NUMBER>")
        return
    global CURRENT_GAME_WEEK
    CURRENT_GAME_WEEK = int(parts[1])
    bot.reply_to(message, f"✅ Game Week has been set to: {CURRENT_GAME_WEEK}")

if __name__ == "__main__":
    logging.info("Bot is running...")
    bot.polling(non_stop=True)
