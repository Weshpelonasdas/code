import os
import uuid
import json
import requests
from flask import Flask, render_template_string, redirect, request, abort
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION VIA ENVIROMENT VARIABLES (RENDER)
# ---------------------------------------------------------
LOOTLABS_API_KEY = os.environ.get("LOOTLABS_API_KEY")
LOOTLABS_TIER_ID = os.environ.get("LOOTLABS_TIER_ID")
# Note : MON_DOMAINE doit être ton URL Render (ex: https://mon-site.onrender.com)
MON_DOMAINE = os.environ.get("MON_DOMAINE") 

# Initialisation Firebase sécurisée via Variable d'environnement
# Tu colleras le contenu complet de ton fichier JSON Firebase dans la variable FIREBASE_CONFIG sur Render
firebase_config_env = os.environ.get("FIREBASE_CONFIG")

if firebase_config_env:
    cred_dict = json.loads(firebase_config_env)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
else:
    # Pour tes tests en local si tu as le fichier json sous la main
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ---------------------------------------------------------
# PAGES WEB
# ---------------------------------------------------------

# 1. Page d'accueil
@app.route('/')
def index():
    html_home = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Obtenir un Code</title>
        <style>
            body { background: #121212; color: white; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin-top: 150px; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            h1 { color: #fff; font-size: 32px; }
            p { color: #bbb; font-size: 18px; margin-bottom: 40px; }
            .btn { background: #ff007f; color: white; padding: 15px 40px; text-decoration: none; font-weight: bold; border-radius: 30px; font-size: 18px; transition: 0.3s; box-shadow: 0 4px 15px rgba(255, 0, 127, 0.4); }
            .btn:hover { background: #e0006c; box-shadow: 0 6px 20px rgba(255, 0, 127, 0.6); }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Prêt à récupérer ton code unique ?</h1>
            <p>Complète la courte vérification publicitaire pour débloquer ton lot instantanément.</p>
            <br><br>
            <a class="btn" href="/generer-lien">👉 Débloquer mon Code</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_home)


# 2. Génération du lien Loot Labs avec Token unique
@app.route('/generer-lien')
def generer_lien():
    if not LOOTLABS_API_KEY or not MON_DOMAINE:
        return "Erreur de configuration du serveur (Variables d'environnement manquantes).", 500

    # Création du token unique (UUID v4)
    unique_token = str(uuid.uuid4())
    
    # URL vers laquelle Loot Labs doit renvoyer l'utilisateur après la pub
    target_url = f"{MON_DOMAINE.rstrip('/')}/redeem?token={unique_token}"
    
    # Enregistrement du token dans Firebase en mode "valide"
    db.collection("tokens_actifs").document(unique_token).set({
        "expire": False
    })
    
    # Requête vers l'API Loot Labs pour générer le lien raccourci
    api_url = "https://api.lootlabs.gg/v1/links" 
    headers = {
        "Authorization": f"Bearer {LOOTLABS_API_KEY}", 
        "Content-Type": "application/json"
    }
    payload = {
        "tier_id": int(LOOTLABS_TIER_ID) if LOOTLABS_TIER_ID.isdigit() else LOOTLABS_TIER_ID,
        "target_url": target_url,
        "title": f"Redeem-{unique_token[:8]}"
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        data = response.json()
        
        # Récupération du lien généré
        loot_link = data.get("short_link")
        
        if not loot_link:
            return f"Erreur de l'API Loot Labs : {data}", 400
            
        # Redirection de l'utilisateur vers la page de pub
        return redirect(loot_link)
        
    except Exception as e:
        return f"Erreur lors de la génération du lien : {str(e)}", 500


# 3. Page de Redeem (Incontournable & Usage Unique)
@app.route('/redeem')
def redeem():
    token = request.args.get('token')
    
    if not token:
        abort(403) # Accès refusé si aucun token n'est fourni
        
    # Vérification du token dans Firestore
    token_ref = db.collection("tokens_actifs").document(token)
    token_doc = token_ref.get()
    
    if not token_doc.exists or token_doc.to_dict().get("expire") == True:
        return """
        <body style="background:#121212; color:#ff4a4a; font-family:Arial; text-align:center; margin-top:150px;">
            <h1>Lien expiré ou invalide !</h1>
            <p style="color:#aaa;">Ce jeton d'accès a déjà été validé ou n'existe pas. Tu dois repasser par l'accueil.</p>
            <br>
            <a href="/" style="color:white; text-decoration:underline;">Retourner à l'accueil</a>
        </body>
        """, 403

    # LE TOKEN EST BON : On le détruit immédiatement dans la base de données
    token_ref.update({"expire": True})
    
    # Recherche d'un code secret disponible (utilise == False)
    codes_ref = db.collection("codes_secrets").where("utilise", "==", False).limit(1).get()
    
    if not codes_ref:
        return """
        <body style="background:#121212; color:white; font-family:Arial; text-align:center; margin-top:150px;">
            <h1>Plus de codes en stock !</h1>
            <p style="color:#aaa;">Désolé, notre réserve de codes est vide pour le moment. Repasse plus tard !</p>
        </body>
        """
        
    doc_code = codes_ref[0]
    code_secret = doc_code.to_dict().get("valeur")
    
    # Marquage du code secret comme consommé
    db.collection("codes_secrets").document(doc_code.id).update({"utilise": True})
    
    # Affichage du code à l'écran
    html_redeem = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Ton Code Unique</title>
        <style>
            body {{ background: #121212; color: white; font-family: Arial, sans-serif; text-align: center; margin-top: 120px; }}
            .box {{ border: 3px dashed #00ffcc; padding: 25px 40px; display: inline-block; font-size: 32px; font-weight: bold; font-family: 'Courier New', Courier, monospace; background: #1a1a1a; letter-spacing: 3px; border-radius: 10px; margin-top: 20px; color: #00ffcc; box-shadow: 0 0 15px rgba(0, 255, 204, 0.2); }}
            p {{ color: #aaa; }}
        </style>
    </head>
    <body>
        <h1>Félicitations !</h1>
        <p>Voici ton code unique obtenu avec succès :</p>
        <div class="box">{code_secret}</div>
        <p style="color: #666; font-size: 14px; margin-top: 40px;">⚠️ Ce lien de validation et ce code viennent d'être désactivés. Note-le bien avant de fermer la page.</p>
    </body>
    </html>
    """
    return render_template_string(html_redeem)

if __name__ == '__main__':
    # Géré par Gunicorn sur Render, mais utile pour tes tests locaux
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
