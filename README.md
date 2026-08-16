# Carte Cameras Live

Carte mondiale de caméras publiques, avec géolocalisation de photo et assistant conversationnel.
Tout tourne en local : aucune donnée n'est envoyée ailleurs, sauf les appels explicites au
modèle de langage.

## Ce que ça fait

**Carte** — agrège des caméras publiques de sept sources (SkylineWebcams, WebcamHopper,
WhatsUpCams, TfL Londres, Fintraffic Finlande, 511NY et Windy Webcams), plus les câbles
sous-marins et les événements des dernières 24 h (ACLED, GDELT, GDACS, USGS, NASA FIRMS).
Les sources qui aboutissent à YouTube ne sont pas intégrées.

**Géolocalisation de photo** — chaîne à trois étages :

1. **Observation** — OCR de scène (RapidOCR / PP-OCR) lit les panneaux ; un modèle vision
   relève les indices (langue, plaques, végétation, côté de circulation)
2. **Hypothèses** — GeoCLIP propose 5 zones, StreetCLIP donne un second avis, les toponymes
   lus sont géocodés et recoupés entre eux
3. **Arbitrage** — un modèle texte tranche entre les zones, avec la possibilité de toutes
   les rejeter si les preuves désignent ailleurs

Puis vérification : OpenStreetMap (les lieux lus existent-ils vraiment ici ?), météo
historique du jour, position du soleil, caméras publiques proches, appariement géométrique.

**Assistant** — conversation sur ce que l'application voit. Il capture l'image de la caméra
ouverte, répond dessus, et dispose d'outils pour compter les caméras d'un pays, en chercher,
en ouvrir une, déplacer la carte.

**Enquête** — dossiers horodatés, rapports HTML autonomes avec chaîne de preuves,
traitement par lot, floutage automatique des personnes et véhicules avant partage.

## Ce que ça ne fait pas

Aucune identification de personne : ni reconnaissance faciale, ni recherche de visage, ni
agrégation de profils. L'application décrit des lieux, des scènes et des dates. Le floutage
automatique est là pour que les rapports soient partageables.

## Démarrage

**Windows** — double-clic sur `installer.bat`, puis sur `lancer.bat`.
Guide détaillé pour un testeur : [INSTALLATION.md](INSTALLATION.md).

**Autres systèmes**

```bash
pip install -r requirements.txt
cp keys.example.json keys.json     # puis renseigner au moins vlm_key
python earthcam_live_map.py
```

Les cinq catalogues principaux fonctionnent sans clé (511NY reste optionnel). Une clé
Webcams API gratuite active Windy ; le collecteur évite la troncature des grands pays
par un découpage géographique et conserve un cache local dédupliqué. Pour forcer une
extraction complète :

```bash
python earthcam_live_map.py --extract-windy
```

L'assistant demande une clé API gratuite ; l'analyse de photo demande en plus PyTorch CUDA,
GeoCLIP et RapidOCR (lignes commentées de `requirements.txt`).

## Architecture

```
web/                  front statique (index.html, app.css, app.js)
earthcam_live_map.py  serveur, 37 routes API, collecteurs
photo_osint.py        OCR, forensique, soleil, météo, Overpass, appariement, floutage
detect_stream.py      détection YOLO + suivi ByteTrack sur un flux
bench_geoloc.py       banc de mesure sur vérité terrain
```

Trois rôles via `CARTE_ROLE` : `complet` (tout en local), `site` (VPS, délègue le GPU),
`worker` (poste GPU). Voir [DEPLOIEMENT.md](DEPLOIEMENT.md).

## Précision mesurée

Banc de 25 webcams mondiales tirées au sort, position officielle connue
(`python bench_geoloc.py -n 25`) :

| | Erreur médiane | < 100 km | < 1 km |
|---|---|---|---|
| GeoCLIP seul | 258 km | 24 % | 8 % |

La chaîne complète ne déplace pas la médiane — elle transforme les cas où un panneau est
lisible. Sur une caméra où GeoCLIP se trompait de 1 655 km, la lecture des panneaux
ramène la réponse à **271 mètres**. Quand aucun texte n'est lisible, elle n'apporte rien :
c'est une amélioration de distribution, pas de moyenne.

## Licence et usage

Projet personnel. Les flux de caméras appartiennent à leurs fournisseurs respectifs et
restent soumis à leurs conditions d'utilisation — un usage personnel n'équivaut pas à une
rediffusion publique. StreetCLIP est sous licence CC-BY-NC-4.0 (usage non commercial).
