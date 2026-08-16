# Carte Cameras Live — dossier technique complet

Document destiné à être fourni tel quel à un assistant IA pour comprendre le projet
et proposer des modifications. Tout ce qui suit décrit le code réellement en place,
avec les chiffres mesurés sur la machine de développement.

---

## 1. Ce qu'est l'application

Une application de bureau qui est en réalité **un site web servi en local**. Un serveur
HTTP Python sert une page et 32 routes d'API ; une fenêtre native (`pywebview`) l'affiche.
Il n'y a aucun framework : pas de React, pas de FastAPI. Le front est du JavaScript
vanilla avec Leaflet, le back du `http.server` de la bibliothèque standard.

Trois grandes fonctions :

1. **Une carte mondiale de caméras publiques** agrégées depuis huit sources
2. **Une géolocalisation de photo** — on dépose une image, l'app dit où elle a été prise
3. **Un assistant conversationnel** qui voit ce que l'app affiche et peut la piloter

Plus deux fonctions annexes : détection/suivi d'objets par YOLO sur un flux, et un
module d'enquête (dossiers, rapports, floutage).

---

## 2. Fichiers et volumétrie

| Fichier | Lignes | Rôle |
|---|---|---|
| `earthcam_live_map.py` | 3 667 | Serveur, 32 routes, 16 collecteurs, chaîne de géolocalisation, assistant |
| `web/app.js` | 1 025 | Tout le front : carte, panneaux, fenêtres caméra, chat |
| `web/app.css` | 298 | Styles |
| `web/index.html` | 138 | Structure |
| `web/demo.js` | 203 | Mode démonstration scripté (pour filmer une vidéo) |
| `photo_osint.py` | 569 | OCR, forensique, soleil, météo, Overpass, appariement, floutage |
| `detect_stream.py` | 587 | Sous-processus de détection/suivi YOLO sur un flux |
| `bench_geoloc.py` | 170 | Banc de mesure de la précision sur vérité terrain |

Le front est servi en fichiers statiques depuis `web/`. **Modifier le CSS ou le JS ne
demande pas de redémarrer Python**, un rafraîchissement du navigateur suffit.

---

## 3. La carte et les caméras

### Sources agrégées

| Source | Type de flux | Volume approximatif |
|---|---|---|
| SkylineWebcams | HLS via proxy | ~1 900 |
| WebCamTaxi | pages avec lecteur intégré (souvent YouTube) | ~2 200 |
| WebcamHopper | HLS ou YouTube | ~1 000 |
| WhatsUpCams | HLS direct | ~470 |
| TfL Londres | MP4 | ~880 |
| Fintraffic Finlande | images JPEG | ~810 |
| 511NY New York | HLS | variable |
| EarthCam USA | YouTube | ~30 |

Chaque source a son thread collecteur (`wuc_loop`, `skyline_loop`, `webcam_taxi_loop`,
`webcam_hopper_loop`, `tfl_loop`, `fin_loop`, `nydot_loop`, `earth_loop`) qui remplit un
dictionnaire d'état et écrit un cache JSON. Au premier lancement, les catalogues se
remplissent en deux à trois minutes ; ensuite le cache sert de démarrage à chaud.

### Autres couches

- **Câbles sous-marins** (`cables_load`) — GeoJSON affiché sur la carte
- **Événements des dernières 24 h** — quatre collecteurs : `events_loop` (NASA EONET
  météo + GDELT actualités géolocalisées), `gdacs_loop` (catastrophes), `quake_loop`
  (séismes USGS), `firms_loop` (anomalies thermiques NASA FIRMS), `acled_loop` (conflits)
- **Affinage de position** (`refine_positions_loop`) — géocode les titres d'événements
  pour les placer plus précisément que la ville

### Interface

- Rail d'icônes à gauche (56 px) qui ouvre un panneau coulissant : Caméras, Sources,
  Localiser une photo, Assistant, Légende
- Barre de recherche flottante en haut à droite avec rond de profil
- Carte plein écran, jamais recouverte
- Fenêtres caméra déplaçables, avec zoom par sélection rectangulaire
- Vue ville 3D (MapLibre + bâtiments OpenStreetMap extrudés) au clic sur la carte

---

## 4. La géolocalisation de photo

C'est la fonction la plus élaborée. Chaîne à trois étages, puis vérification.

### Étage 1 — observation

- **GPS EXIF** s'il existe : réponse exacte immédiate
- **OCR de scène** (RapidOCR, modèles PP-OCR en ONNX) : lit les panneaux et enseignes.
  Deux passes — l'image entière, puis un recadrage agrandi ×4 de chaque zone détectée.
  Mesure : « Tie 25 Vihti, Myllylampi » passe de 0,93 en bloc à trois jetons propres à
  0,96–1,00. Coût : 0,7 s par image, sur CPU.
- **Modèle vision** (par défaut `gemma-4-31B-it` chez SambaNova) : transcrit les textes
  bruts et relève les indices — langue, plaques, côté de circulation, végétation,
  architecture. Il lui est explicitement interdit de conclure un pays à partir d'un
  seul toponyme.

### Étage 2 — hypothèses

- **GeoCLIP** : CLIP ViT-L/14 comparé à une galerie de 100 000 coordonnées apprises.
  Sortie : top-5 lat/lng avec probabilité. ~4 s sur GPU.
- **StreetCLIP** : second avis indépendant, classe la photo par pays en zero-shot.
  Licence CC-BY-NC-4.0, usage non commercial.
- **Toponymes** : les mots lus sur les panneaux sont géocodés un par un via Nominatim,
  puis recoupés. Deux noms distincts qui tombent à moins de 40 km l'un de l'autre
  constituent une preuve forte.

### Étage 3 — arbitrage

Un modèle texte (`gpt-oss-120b`, repli `DeepSeek-V3.2`) reçoit les textes bruts, les
indices, les candidats et les toponymes, et tranche. Règles imposées : le rang 1 de
GeoCLIP est le choix par défaut, un seul toponyme n'est pas une preuve décisive, et il
peut répondre **rang 0** signifiant « aucun candidat ne tient » — auquel cas la lecture
des panneaux devient la réponse.

### Étage 4 — vérification

- **OpenStreetMap via Overpass** : les lieux et numéros de route lus existent-ils
  réellement autour de la position retenue ? Mesure : 4 correspondances au bon endroit,
  0 sur une hypothèse fausse. Tourne en tâche de fond car les serveurs publics mettent
  40 à 60 s aux heures pleines.
- **Météo historique** (Open-Meteo, sans clé) : s'il n'a pas neigé ce jour-là à cet
  endroit alors que la photo montre de la neige, l'hypothèse est signalée
- **Position du soleil** (algorithme NOAA, aucun réseau) : cohérence entre l'heure EXIF,
  la latitude et les ombres visibles
- **Caméras publiques proches** : croisement avec le catalogue de l'app
- **Appariement géométrique** (SuperPoint + LightGlue, fournis par `transformers`) :
  compare la photo à l'image live d'une caméra voisine. Mesure : 892 correspondances
  sur une même scène, 0 entre deux lieux différents.

### Précision mesurée

Banc de 25 webcams mondiales tirées au sort, position officielle connue
(`python bench_geoloc.py -n 25`) :

| | Erreur médiane | < 100 km | < 1 km |
|---|---|---|---|
| GeoCLIP seul | 258 km | 24 % | 8 % |

**La chaîne complète ne déplace pas la médiane.** Elle transforme les cas où un panneau
est lisible : sur une caméra où GeoCLIP se trompait de 1 655 km, la lecture des panneaux
ramène la réponse à **271 mètres**. Quand aucun texte n'est lisible — 7 cas sur 10 sur
des routes forestières — elle n'apporte rien. C'est une amélioration de distribution,
pas de moyenne.

Mesure abandonnée : un raffinement par grille dense autour des candidats GeoCLIP
n'apporte rien (1 208 → 1 200 km de moyenne). Le code existe mais est désactivé
(`CARTE_GEOCLIP_REFINE=1` pour le réactiver).

---

## 5. L'assistant conversationnel

Panneau de chat façon messagerie : messages de l'utilisateur à droite, réponses à
gauche, bulles avec horodatage, indicateur de saisie animé.

### Ce qu'il voit

- **Une caméra ouverte** : le serveur capture l'image courante du flux et l'envoie au
  modèle vision avec la question. La capture est faite **côté serveur** car un canvas
  navigateur alimenté par un autre domaine est inexportable (canvas « tainted »).
  Résolution des flux : image directe, MP4 via OpenCV, HLS avec en-tête Referer,
  YouTube via yt-dlp, WebCamTaxi via son embed. Seuls les lecteurs tiers opaques
  échouent, avec un message explicite.
- **Une photo analysée** : la photo et toute l'analyse (textes OCR, candidats,
  vérifications, météo, soleil)
- **Rien** : il répond à partir des seuls éléments d'analyse et dit qu'une image
  serait nécessaire

### Ce qu'il peut faire — outils (function calling)

| Outil | Effet |
|---|---|
| `compter_cameras` | Compte les caméras d'un pays, région ou ville |
| `chercher_cameras` | Liste les caméras correspondant à un lieu ou mot-clé |
| `ouvrir_camera` | Ouvre une caméra à l'écran et centre la carte |
| `aller_a` | Déplace la carte sur un lieu nommé |
| `etat_carte` | Totaux par catalogue, événements, position actuelle |

Le modèle enchaîne les outils seul : « ouvre-moi une caméra à Venise » déclenche une
recherche puis une ouverture. Les catalogues étant libellés en anglais, la description
de l'outil indique au modèle de réessayer en anglais si une recherche en français ne
donne rien.

Comptage sur le catalogue réel : Japon 335, Italie 277, Croatie 186, Espagne 148,
Allemagne 71, total 5 596. Le comptage par pays se fait sur le **dernier segment** du
champ lieu, sinon « Italie » attrape « Little Italy, New York ».

---

## 6. Détection et suivi (YOLO)

Bouton « SUIVI LIVE (POST-IT) » sur chaque fenêtre caméra. Lance `detect_stream.py`
en sous-processus, qui sert un post-it sur le port 8772 : `/frame.jpg`, `/stream.mjpg`,
`/meta.json`.

- Détection YOLO + suivi ByteTrack, identifiants temporaires par session
- Classes suivies : personnes, véhicules, animaux (COCO)
- Le front dessine des rectangles verts sur la vidéo et des post-its flottants autour
  du cadre, reliés par des fils, avec vignette et étiquette
- Super-résolution Real-ESRGAN si disponible, sinon agrandissement classique

**Réglages importants issus du débogage :**

- L'auto-installation d'`onnxruntime-gpu` par Ultralytics est désactivée
  (`YOLO_AUTOINSTALL=false`) : elle bloquait 30 s à chaque lancement et échouait
- Le modèle léger `yolo26n.pt` est imposé au sous-processus : `yolo11l.pt` met plus de
  100 s à charger quand GeoCLIP occupe déjà la carte, contre 16 s pour le nano.
  Contrepartie : le nano étiquette parfois des voitures comme des trains.
  `CARTE_YOLO=yolo11l.pt` rétablit la précision au prix de l'attente.
- L'image du post-it est servie tant qu'elle a moins de 30 s (contre 1,5 s avant) :
  une caméra de type image ne se rafraîchit pas plus vite, le navigateur ne recevait
  que des 404
- La sortie du sous-processus est écrite dans `detect_stream.log` ; elle était jetée
  auparavant, ce qui rendait toute panne invisible

---

## 7. Module d'enquête

- **Dossiers** : chaque analyse sauvegardée dans `enquetes/<horodatage>-<lieu>/` avec
  la photo, le JSON complet, un rapport HTML autonome et une ligne de journal
- **Rapport HTML** : photo incluse en base64, verdict, raisonnement, textes lus,
  indices, zones candidates, vérification terrain, chronolocalisation, caméras proches,
  authenticité du fichier, sources citées
- **Traitement par lot** : un dossier entier d'images analysé en tâche de fond
- **Authenticité** : métadonnées EXIF étendues (via exifread, ou ExifTool s'il est sur
  le PATH), détection de logiciel de retouche ou de génération, analyse ELA et tables
  de quantification JPEG
- **Anonymisation** : floutage des personnes et véhicules via YOLO avant partage.
  Testé : 6 objets floutés sur une image de trafic

---

## 8. Configuration

### Variables d'environnement

| Variable | Effet |
|---|---|
| `CARTE_ROLE` | `complet` (défaut), `site` (VPS, délègue le GPU), `worker` (poste GPU) |
| `CARTE_BIND` | Interface d'écoute. Hors `127.0.0.1`, le mode public s'active |
| `CARTE_TOKEN` | Jeton d'accès, obligatoire en mode public |
| `CARTE_IA_URL` / `CARTE_IA_TOKEN` | Adresse du poste de calcul quand le rôle est `site` |
| `CARTE_ORIGINES` | Origines autorisées en CORS (front hébergé ailleurs) |
| `CARTE_VLM_PROVIDER` / `_MODEL` / `_KEY` / `_URL` | Fournisseur du modèle vision |
| `CARTE_ARBITER_MODEL` | Modèle texte d'arbitrage |
| `CARTE_YOLO` | Force un modèle YOLO précis |
| `CARTE_GEOCLIP_REFINE` | Réactive la grille dense (mesurée inutile) |

### `keys.json`

Clés reconnues : `vlm_provider`, `vlm_model`, `vlm_key`, `vlm_url`, `arbiter_model`,
`arbiter_fallback`, `role`, `bind`, `site_token`, `ia_url`, `ia_token`, `origines`,
`firms`, `acled_key`, `acled_email`, `aisstream`. Le fichier n'est jamais versionné.

### Mode public

Dès que l'écoute sort de `127.0.0.1` : jeton obligatoire (page de connexion, cookie 30
jours, ou en-tête `Authorization`), et trois routes coupées — `/detect`, `/detect-stop`
(lancent des sous-processus) et `/api/photo-batch` (lit un dossier arbitraire du disque).

### Déploiement en trois rôles

Le rôle `site` tourne sur un VPS sans GPU : il porte la page, les catalogues, les
événements, l'assistant et les dossiers, et délègue `/api/geolocate` et
`/api/photo-anonymize` au poste équipé du GPU via un tunnel. Le VPS n'a besoin ni de
PyTorch, ni de CUDA, ni de transformers — `opencv-python-headless` et `yt-dlp` suffisent.

---

## 9. Routes de l'API

**GET** — `/api/status`, `/api/earthcam`, `/api/skyline`, `/api/webcamtaxi`,
`/api/webcamhopper`, `/api/whatsupcams`, `/api/tfl`, `/api/finland`, `/api/nydot`,
`/api/events`, `/api/cables`, `/api/airports`, `/api/ais`, `/api/planes`,
`/api/flight-route`, `/api/geo-status`, `/api/llm-status`, `/api/photo-cases`,
`/api/photo-report`, `/api/photo-progress`, `/api/photo-verify`, `/api/photo-batch`,
`/api/skyline-stream`, `/api/skyline-proxy`, `/api/webcamtaxi-stream`,
`/api/webcamhopper-stream`, `/detect`, `/detect-stop`, `/translate`

**POST** — `/api/geolocate`, `/api/chat`, `/api/photo-save`, `/api/photo-anonymize`,
`/api/photo-batch`

`/api/geolocate` accepte `progressif: true` : il rend un jeton immédiatement et publie
chaque étape, ce qui permet d'afficher les résultats au fil de l'eau (GeoCLIP à 4 s,
OCR à 5 s, verdict à 25 s) au lieu d'attendre la fin.

---

## 10. Dépendances

**Socle** (suffit pour la carte, les caméras, l'assistant, le mode site) :
`opencv-python-headless`, `yt-dlp`, `pywebview`.

**Analyse de photo**, sur poste avec GPU NVIDIA : `torch` et `torchvision` en CUDA 12.1,
`geoclip` (installé avec `--no-deps`), `transformers<5`, `geopy`, `pandas`,
`rapidocr-onnxruntime`, `exifread`, `ultralytics`.

**Contraintes non évidentes :**

- `transformers` doit rester en 4.x. En 5.x, `CLIPModel.get_image_features` renvoie un
  objet au lieu d'un tenseur et GeoCLIP casse.
- StreetCLIP n'est publié qu'en `.bin` et transformers 4.57 refuse `torch.load` sous
  torch < 2.6 : le state dict est chargé à la main plutôt que de toucher à
  l'installation CUDA.
- `onnxruntime` et `onnxruntime-gpu` partagent le même module : désinstaller l'un casse
  l'autre.
- Carte de 6 Go : GeoCLIP (~1,7 Go) + StreetCLIP + YOLO ne tiennent pas ensemble.
  Un garde-fou bascule StreetCLIP et LightGlue sur CPU sous 2 Go libres.

---

## 11. Limites connues

- **Un seul utilisateur à la fois.** L'état est global : une détection, un lot, une
  vue. À plusieurs simultanément, ça se marche dessus.
- **Le palier gratuit SambaNova ne tient pas un traitement par lot.** Un banc de 25
  images avec modèle vision sature en 429. Une cascade multi-fournisseurs
  (SambaNova → Cloudflare → Gemini) est la solution évidente, non implémentée.
- **Les serveurs Overpass publics sont lents** aux heures pleines (40 à 60 s).
- **Le petit modèle YOLO confond des voitures avec des trains.**
- **Aucune prédiction.** Le système décrit une situation, il ne l'anticipe pas.
- Le module Python fait 3 667 lignes et mélange huit sujets ; un découpage en modules
  (`sources/`, `geoloc.py`, `assistant.py`, `serveur.py`) reste à faire.

---

## 12. Limite fonctionnelle assumée

L'application **n'identifie aucune personne** : ni reconnaissance faciale, ni recherche
de visage, ni agrégation de profils, ni identité persistante suivie d'une caméra à
l'autre. Elle décrit des lieux, des scènes, des dates et vérifie des images. Le prompt
système de l'assistant refuse explicitement les demandes d'identification. Le floutage
automatique existe pour que les rapports soient partageables.

Une version enrichie de ré-identification inter-caméras avec identifiants persistants
avait été ajoutée puis retirée ; elle est conservée dans `sauvegarde_version_15aout/`.

---

## 13. Pistes de modification, avec points d'entrée

| Idée | Où intervenir | Difficulté |
|---|---|---|
| Cascade multi-fournisseurs pour l'IA | `vlm_post()` et `photo_chat()` dans `earthcam_live_map.py` | moyenne |
| Découper le Python en modules | tout le fichier, prévoir des tests d'abord | élevée |
| Multi-utilisateur | isoler l'état global par session | élevée |
| Vérification par imagerie de rue | `photo_osint.py`, ajouter Mapillary (jeton gratuit) + `match_images()` déjà écrit | moyenne |
| Imagerie satellite | Copernicus/Sentinel, compte gratuit | moyenne |
| Indicateur « chargement du modèle » pendant le suivi | `attachPersonPostit()` dans `web/app.js` | faible |
| Zones de surveillance avec historique | nouveaux collecteurs + stockage | élevée |
| Réactiver avions et navires | `main()`, les threads `planes_loop`, `ais_loop` existent mais ne démarrent plus | faible |
| Exécutable Windows | PyInstaller | moyenne |
| Cache disque des analyses | `photo_locate()` | faible |

---

## 14. Comment le lancer

```
python earthcam_live_map.py
```

Ou `installer.bat` puis `lancer.bat` sous Windows. La carte et les caméras fonctionnent
sans aucune clé. L'assistant demande une clé API gratuite. L'analyse de photo demande
en plus les dépendances GPU.

Mode démonstration pour filmer : `http://localhost:8770/?demo=1`, onze plans enchaînés,
espace pour mettre en pause.

Banc de mesure : `python bench_geoloc.py -n 25`.
