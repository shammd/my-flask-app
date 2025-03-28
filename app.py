import requests
import re
from flask import Flask, render_template, request

app = Flask(__name__)

API_KEY = "5d69bc9b523544498039a1c0772dee9d"
VISION_URL = "https://dv1615-apimanagement-lab.azure-api.net/vision/v3.0/analyze?visualFeatures=Tags"
TRANSLATE_URL = "https://dv1615-apimanagement-lab.azure-api.net/translator/text/v3.0/translate?from=en&to=sv"
LAGER_API_URL = "https://dv1615-docker-webapp-lab-hgdqcqggaaa9gbhu.northeurope-01.azurewebsites.net/v2/products/everything"

HEADERS = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Content-Type": "application/json"
}

def translate_tag(tag_name):
    """Översätter en tagg från engelska till svenska"""
    body = [{"Text": tag_name}]
    try:
        response = requests.post(TRANSLATE_URL, headers=HEADERS, json=body, timeout=5)
        response.raise_for_status()
        translation_data = response.json()
        return translation_data[0]['translations'][0]['text']
    except requests.exceptions.RequestException:
        return tag_name  

def fetch_products():
    """Hämtar alla produkter från Lager-API"""
    try:
        response = requests.get(LAGER_API_URL, timeout=10)
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.exceptions.RequestException as e:
        print(f"Fel vid hämtning av produkter: {e}")
        raise 

def match_products(tags, products):
    """Matchar taggar mot produkter baserat på namn och beskrivning"""
    matched_products = []
    tag_names = [tag['name'].lower() for tag in tags]
    
    for product in products:
        product_name = (product.get("name") or "").lower()
        product_description = (product.get("description") or "").lower()
        match_score = 0
        
        for tag in tag_names:
            if re.search(r'\b' + re.escape(tag) + r'\b', product_name):
                match_score += 2
            if re.search(r'\b' + re.escape(tag) + r'\b', product_description):
                match_score += 1

        if match_score > 0:
            product['match_score'] = match_score
            matched_products.append(product)

    return sorted(matched_products, key=lambda x: x.get('match_score', 0), reverse=True)

@app.route('/image_search', methods=["GET", "POST"])
def image_search():
    """Huvudfunktion för bildsökning"""
    image_url = ""
    tags = []
    matched_products = []
    error = None
    loading = False

    if request.method == "POST":
        image_url = request.form.get("image-url", "").strip()
        if image_url:
            loading = True  

    elif request.method == "GET":
        image_url = request.args.get("image-url", "").strip()

    if image_url:
        if not (image_url.startswith('http://') or image_url.startswith('https://')): 
            error = "Ogiltig URL. Ange en fullständig webbadress (börjar med http:// eller https://)"
        else:
            try:
                vision_response = requests.post(
                    VISION_URL,
                    headers=HEADERS,
                    json={"url": image_url},
                    timeout=15
                )
                vision_response.raise_for_status()
                vision_data = vision_response.json()
                
                if "tags" in vision_data:
                    tags = [{
                        'name': translate_tag(tag['name']),
                        'confidence': tag['confidence']
                    } for tag in vision_data["tags"] if tag["confidence"] >= 0.97] 

                if tags:
                    try:
                        products = fetch_products()
                        matched_products = match_products(tags, products)
                    except requests.exceptions.RequestException as e:
                        error = f"Kunde inte hämta produkter från lagret: {str(e)}"

            except requests.exceptions.HTTPError as http_err:
                if http_err.response.status_code == 429:
                    error = "För många förfrågningar. Vänta en stund och försök igen."
                else:
                    error = f"Fel från bildanalys-tjänsten: {str(http_err)}"
            except requests.exceptions.Timeout:
                error = "Tidsgräns uppnådd vid analys av bild. Försök igen senare."
            except requests.exceptions.RequestException as e:
                error = f"Nätverksfel: {str(e)}"
            finally:
                loading = False

    return render_template(
        "index.html",
        image_url=image_url,
        tags=tags,
        matched_products=matched_products,
        error=error,
        loading=loading
    )

if __name__ == "__main__":
    app.run(debug=True)
