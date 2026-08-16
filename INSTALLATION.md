# Installation — pour tester l'application

Testé sur une machine sans rien : un clone vierge démarre et remplit ses catalogues
tout seul, aucun fichier de données n'est nécessaire.

## Ce qu'il faut avant

**Python 3.10 ou plus**, depuis [python.org](https://www.python.org/downloads/).
Pendant l'installation, coche bien **« Add Python to PATH »** — c'est la seule erreur
qui bloque tout.

Rien d'autre. Pas de compte, pas de carte bancaire, pas de GPU.

## Installation

1. Télécharge le projet : bouton vert **Code → Download ZIP**, puis décompresse-le
   (ou `git clone` si tu es à l'aise avec git)
2. Double-clique sur **`installer.bat`** et laisse-le finir — quelques minutes la
   première fois
3. Double-clique sur **`lancer.bat`**

La carte s'ouvre. **Garde la fenêtre noire ouverte** : c'est elle qui fait tourner
l'application. Pour arrêter, ferme-la.

Au premier lancement, les catalogues se remplissent progressivement — les caméras
apparaissent sur la carte au fur et à mesure, compte deux à trois minutes.

## Ce qui marche tout de suite

- La carte mondiale et ses milliers de caméras publiques, en direct
- La recherche de lieu, les câbles sous-marins, les événements des dernières 24 h
- La vue ville en 3D (clic sur la carte)

## Ce qui demande une clé gratuite

L'**assistant** et la **géolocalisation de photo** appellent un modèle d'IA. Sans clé,
le reste de l'application fonctionne, ces deux fonctions affichent simplement une erreur.

Pour les activer :

1. Crée un compte gratuit sur [cloud.sambanova.ai](https://cloud.sambanova.ai) et
   récupère une clé API
2. Ouvre `keys.json` avec le Bloc-notes
3. Colle la clé entre les guillemets de `"vlm_key": ""`
4. Relance `lancer.bat`

La clé reste sur ta machine, elle n'est jamais envoyée ailleurs qu'à SambaNova.

## Ce qui demande une carte graphique NVIDIA

La géolocalisation de photo utilise deux modèles locaux (GeoCLIP, StreetCLIP) plus un
moteur OCR. Ils ne sont **pas** installés par défaut, parce qu'ils pèsent plusieurs Go.

Sans eux : l'assistant fonctionne, l'analyse de photo non.

Pour les ajouter, avec une carte NVIDIA :

```bat
.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
.venv\Scripts\python.exe -m pip install "transformers<5" geopy pandas rapidocr-onnxruntime exifread ultralytics
.venv\Scripts\python.exe -m pip install geoclip --no-deps
```

`transformers<5` est obligatoire : en version 5, GeoCLIP ne fonctionne plus.

## Si ça coince

**« Python n'est pas reconnu »** — Python absent du PATH. Réinstalle-le en cochant
« Add Python to PATH ».

**La fenêtre s'ouvre puis se ferme aussitôt** — lance `lancer.bat` depuis un terminal
pour voir le message d'erreur, ou envoie une capture du contenu de la fenêtre.

**La carte est vide** — normal les deux premières minutes, les catalogues se chargent.
Au-delà, vérifie ta connexion : l'application interroge des sites publics.

**Le port 8770 est déjà pris** — une autre instance tourne déjà, ou un autre logiciel
occupe ce port. Ferme l'autre fenêtre noire.

## Vie privée

Tout tourne en local. Les seules données qui sortent de la machine sont les requêtes
aux sites de caméras publiques, à OpenStreetMap pour le géocodage, et — si tu as mis
une clé — les images que tu envoies explicitement à l'assistant.

L'application ne fait aucune identification de personne, et elle sait flouter
automatiquement les personnes et véhicules avant qu'un rapport soit partagé.
