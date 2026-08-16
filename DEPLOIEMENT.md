# Passer en version site — VPS + IA restée à la maison

L'application est déjà un site web : un serveur HTTP qui sert une page et 33 routes d'API.
`pywebview` n'est qu'une fenêtre autour. Il n'y a rien à réécrire, seulement à répartir.

## L'architecture retenue

```
   Internet                    VPS (~5 €/mois)              Ton PC (RTX 3050)
   ────────                    ───────────────              ─────────────────
   navigateur  ──HTTPS──▶  role = site                      role = worker
                           • page web + carte               • GeoCLIP  (GPU)
                           • catalogues de caméras          • StreetCLIP
                           • événements, câbles             • OCR, YOLO, LightGlue
                           • assistant + outils
                           • dossiers d'enquête
                                    │
                                    └──── tunnel ─────────▶ /api/geolocate
                                                            /api/photo-anonymize
```

Le VPS tourne 24h/24. L'analyse de photo ne fonctionne que quand ton PC est allumé —
le reste du site (carte, caméras, assistant, événements) marche en permanence.

## Trois rôles, une seule base de code

| `CARTE_ROLE` | Usage | Ce qui tourne |
|---|---|---|
| `complet` (défaut) | ton PC aujourd'hui | tout, fenêtre native |
| `site` | le VPS | tout sauf le GPU, délégué au worker |
| `worker` | ton PC en mode serveur | uniquement les traitements GPU |

Sans variable d'environnement, **rien ne change** : `complet`, écoute sur `127.0.0.1`,
aucun jeton demandé.

## Les clés en hébergement

`keys.json` n'est jamais versionné : sur un hébergeur, il n'existe donc pas. Les clés
se donnent alors par variables d'environnement, dans le tableau de bord de l'hébergeur.
Une variable renseignée l'emporte sur `keys.json`.

| Variable | Remplace la clé | Sert à |
|---|---|---|
| `CARTE_VLM_KEY` | `vlm_key` | assistant et géolocalisation de photo |
| `CARTE_WINDY_KEY` | `windy` | rafraîchir le catalogue Windy |
| `CARTE_FIRMS_KEY` | `firms` | foyers d'incendie |
| `CARTE_ACLED_KEY` / `CARTE_ACLED_EMAIL` | `acled_key` / `acled_email` | événements de conflit |
| `CARTE_AIS_KEY` | `aisstream` | navires |
| `CARTE_NY511_KEY` | `ny511` | caméras trafic de New York |

Le catalogue Windy voyage compressé dans le dépôt (`windy_webcams.json.gz`, 2,7 Mo
pour 69 407 caméras) : un déploiement neuf les affiche immédiatement, sans clé. La clé
ne sert qu'à le régénérer, une fois par semaine.

**Mémoire.** Catalogues complets chargés, le serveur occupe environ 500 Mo. Une
instance à 512 Mo est donc trop juste ; prévoir 1 Go.

## 1. Sur ton PC — le poste de calcul

```
set CARTE_ROLE=worker
set CARTE_IA_TOKEN=un-secret-long-et-aleatoire
python earthcam_live_map.py
```

Aucun collecteur ne démarre, aucune fenêtre ne s'ouvre : il ne sert que
`/api/geolocate` et `/api/photo-anonymize`. GeoCLIP est préchargé au démarrage.

Expose-le au VPS par un tunnel sortant (Cloudflare Tunnel ou Tailscale) — **n'ouvre
aucun port sur ta box**. Tu obtiens une URL du type `https://ia-maison.example.com`.

## 2. Sur le VPS — le site

Installation minimale, sans PyTorch ni CUDA :

```
pip install pywebview==0 --no-deps  # inutile, à ne pas installer
pip install opencv-python-headless yt-dlp
```

Le VPS n'a besoin ni de `torch`, ni de `geoclip`, ni de `transformers`, ni de
`rapidocr`. Copie `earthcam_live_map.py`, `photo_osint.py`, `keys.json`, le dossier
**`web/`** (le front) et les caches JSON des catalogues.

Le front étant devenu des fichiers statiques, tu peux le confier à ton reverse proxy
ou à un CDN plutôt qu'à Python :

```
# Caddy
handle /app.* { root * /opt/carte/web; file_server }
handle { reverse_proxy 127.0.0.1:8770 }
```

```
export CARTE_ROLE=site
export CARTE_BIND=0.0.0.0
export CARTE_TOKEN=le-mot-de-passe-du-site
export CARTE_IA_URL=https://ia-maison.example.com
export CARTE_IA_TOKEN=un-secret-long-et-aleatoire
python3 earthcam_live_map.py
```

Puis un reverse proxy (Caddy ou nginx) devant, pour le HTTPS et le nom de domaine.

## Ce que le mode public active automatiquement

Dès que `CARTE_BIND` sort de `127.0.0.1` :

- **Jeton obligatoire.** Sans `CARTE_TOKEN`, l'app refuse de servir plutôt que de
  s'exposer sans protection. Page de connexion, cookie 30 jours, ou en-tête
  `Authorization: Bearer …` pour les appels API.
- **Routes locales coupées** (403) : `/detect` et `/detect-stop` (lancent des
  sous-processus), `/api/photo-batch` (lit un dossier arbitraire du disque).
- **Pas de fenêtre native**, l'app tourne en serveur.

## Ce qui reste à surveiller

**Un seul utilisateur à la fois.** L'état est global : une seule détection YOLO, un
seul lot en cours, une seule vue avions. À plusieurs simultanément, ça se marchera
dessus. Il faudra découper cet état par session avant d'ouvrir à d'autres personnes.

**Le quota SambaNova est partagé.** Chaque visiteur consomme le même palier gratuit.

**La bande passante.** Le VPS ne relaie que les pages et les API ; les flux vidéo des
caméras vont directement du fournisseur au navigateur du visiteur, sauf pour Skyline
qui passe par `/api/skyline-proxy`. Surveille ce point si tu ouvres largement.

**Les conditions d'utilisation.** Rediffuser publiquement des flux de webcams tiers
n'a pas le même statut qu'un usage personnel. À vérifier avant d'ouvrir le site au
public, pas seulement à des proches.

## Vérifié

Architecture testée en deux processus séparés : le site délègue `/api/geolocate` au
worker, reçoit 5 candidats et 7 textes OCR, puis complète le résultat avec ses propres
catalogues de caméras — ce que le worker ne peut pas faire, puisqu'il ne les a pas.
