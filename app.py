import uuid
import requests
from flask import Flask, render_template_string, redirect, request, abort
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------
LOOTLABS_API_KEY = "TON_API_KEY_LOOT_LABS"
LOOTLABS_TIER_ID = "TON_TIER_ID" # Fourni par Loot Labs
MON_DOMAINE = "https://ton-site-web.com" # Ton URL finale

# Initialisation Firebase (Télécharge ton fichier de clé privée .json depuis Firebase)
cred = credentials.Certificate("path/to/serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# ---------------------------------------------------------
# PAGES WEB
# ---------------------------------------------------------

# 1. Page d'accueil : L'utilisateur clique pour obtenir un code
@app.route('/')
def index():
    html_home = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Obtenir un Code</title>
        <style>
            body { background: #121212; color: white; font-family: Arial; text-align: center; margin-top: 100px; }
            .btn { background: #ff007f; color: white; padding: 15px 30px; text-decoration: none; font-weight: bold; border-radius: 5px; font-size: 18px; }
        </style>
    </head>
    <body>
        <h1>Prêt à récupérer ton code unique ?</h1>
        <p style="color: #aaa; margin-bottom: 40px;">Passe la vérification publicitaire pour débloquer ton lot.</p>
        <a class="btn" href="/generer-lien">👉 Débloquer mon Code</a>
    </body>
    </html>
    """
    return render_template_string(html_home)


# 2. Génération dynamique du lien Loot Labs avec Token unique
@app.route('/generer-lien')
def generer_lien():
    # Génération d'un token unique impossible à deviner
    unique_token = str(uuid.uuid4())
    
    # URL de redirection finale après la pub Loot Labs
    target_url = f"{MON_DOMAINE}/redeem?token={unique_token}"
    
    # Enregistrement du token dans Firebase (il est actif et non expiré)
    db.collection("tokens_actifs").document(unique_token).set({
        "expire": False
    })
    
    # Appel à l'API de Loot Labs pour créer le lien court monétisé
    # (Vérifie la structure exacte de l'API dans ta documentation Loot Labs)
    api_url = "https://api.lootlabs.gg/v1/links" 
    headers = {"Authorization": f"Bearer {LOOTLABS_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "tier_id": LOOTLABS_TIER_ID,
        "target_url": target_url,
        "title": f"Redeem-{unique_token[:8]}"
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        data = response.json()
        loot_link = data.get("short_link") # Récupère le lien court généré par Loot Labs
        
        # On redirige l'utilisateur vers le lien Loot Labs (il va se manger les pubs)
        return redirect(loot_link)
    except Exception as e:
        return f"Erreur lors de la génération du lien publicitaire : {str(e)}", 500


# 3. Page de Redeem (Incontournable & Usage Unique)
@app.route('/redeem')
def redeem():
    token = request.args.get('token')
    
    if not token:
        abort(403) # Accès interdit si pas de token
        
    # Vérification du token dans Firebase
    token_ref = db.collection("tokens_actifs").document(token)
    token_doc = token_ref.get()
    
    if not token_doc.exists or token_doc.to_dict().get("expire") == True:
        return """
        <body style="background:#121212; color:#ff4a4a; font-family:Arial; text-align:center; margin-top:100px;">
            <h1>Lien expiré ou invalide !</h1>
            <p>Ce jeton de validation a déjà été utilisé ou n'existe pas. Tu dois repasser par l'accueil.</p>
            <a href="/" style="color:white;">Retourner à l'accueil</a>
        </body>
        """, 403

    # LE TOKEN EST VALIDE -> On le "brûle" immédiatement pour qu'il soit à usage unique
    token_ref.update({"expire": True})
    
    # On va chercher UN code secret non utilisé dans la base de données
    codes_ref = db.collection("codes_secrets").where("utilise", "==", False).limit(1).get()
    
    if not codes_ref:
        return """
        <body style="background:#121212; color:white; font-family:Arial; text-align:center; margin-top:100px;">
            <h1>Plus de codes disponibles !</h1>
            <p>Reviens plus tard, notre stock est vide.</p>
        </body>
        """
        
    doc_code = codes_ref[0]
    code_secret = doc_code.to_dict().get("valeur")
    
    # Marquer le code secret comme utilisé pour que personne d'autre ne l'ait
    db.collection("codes_secrets").document(doc_code.id).update({"utilise": True})
    
    # Affichage sécurisé du code à l'écran
    html_redeem = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ton Code Unique</title>
        <style>
            body {{ background: #121212; color: white; font-family: Arial; text-align: center; margin-top: 100px; }}
            .box {{ border: 3px dashed #00ffcc; padding: 20px; display: inline-block; font-size: 28px; font-weight: bold; font-family: monospace; background: #1a1a1a; letter-spacing: 2px; border-radius: 10px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <h1>Félicitations !</h1>
        <p>Voici ton code unique récupéré avec succès :</p>
        <div class="box">{code_secret}</div>
        <p style="color: #666; font-size: 13px; margin-top: 30px;">Ce code ainsi que ton lien d'accès viennent d'être détruits. Note-le bien.</p>
    </body>
    </html>
    """
    return render_template_string(html_redeem)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
