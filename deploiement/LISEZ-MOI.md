# Déployer l'application en site web

## Ce que le déploiement apporte — et ce qu'il n'apporte pas

**Il apporte** : un site accessible de partout, 24 h/24, partageable, qui ne dépend plus
de ton PC allumé pour la carte, les caméras et l'assistant.

**Il n'allège pas ton PC pour l'affichage.** La carte se dessine dans ton navigateur,
les flux vidéo sont décodés par ta machine. Que le serveur soit chez toi ou à Francfort
ne change rien à ça. Mesuré : le serveur pèse 454 Mo, le navigateur 2 040 Mo.

Ce que le déploiement retire vraiment de ta machine : les 454 Mo du serveur et les
16 collecteurs qui interrogent les sources en continu.

## Ce qui tourne où

```
   VPS (~5 €/mois, sans GPU)          Ton PC (facultatif)
   ─────────────────────────          ───────────────────
   • carte et interface               • GeoCLIP, StreetCLIP
   • 5 596 caméras, catalogues        • analyse de photo
   • événements, câbles               • floutage
   • assistant + ses outils
   • dossiers d'enquête
            │
            └── tunnel ──────────────▶ CARTE_IA_URL
```

Sans `CARTE_IA_URL`, tout fonctionne **sauf** l'analyse de photo. La carte, les caméras
et l'assistant n'ont besoin d'aucun GPU.

## Installation, en trois étapes

### 1. Un VPS

N'importe quel serveur Debian ou Ubuntu à 4–6 €/mois suffit : 1 vCPU, 2 Go de RAM,
20 Go de disque. Hetzner, OVH, Scaleway, Ionos. Fais pointer un nom de domaine
(un sous-domaine suffit) vers son adresse IP.

### 2. Installer

Copie `installer-vps.sh` sur le serveur, puis :

```bash
sudo bash installer-vps.sh mondomaine.fr
```

Le script installe Python et ses deux dépendances (`opencv-python-headless`, `yt-dlp` —
**ni PyTorch ni CUDA**), crée un utilisateur dédié, génère un jeton d'accès aléatoire,
installe le service systemd et configure Caddy avec HTTPS automatique.

Il affiche le jeton à la fin. Note-le.

### 3. Envoyer le code

Depuis Windows :

```bat
deploiement\envoyer.bat root@adresse-du-vps
```

Puis sur le serveur : `systemctl restart carte`.

## Sécurité

Dès que le rôle est `site`, l'application **exige un jeton**, même en écoutant sur
`127.0.0.1` derrière le reverse proxy — c'était un piège : se fier à l'adresse d'écoute
seule aurait laissé le service ouvert à tous.

Trois routes sont coupées automatiquement : `/detect` et `/detect-stop` (elles lancent
des sous-processus) et `/api/photo-batch` (elle lit un dossier arbitraire du disque).

Le front est servi directement par Caddy, sans passer par Python.

## Brancher l'analyse de photo

Sur ton PC :

```bat
set CARTE_ROLE=worker
set CARTE_IA_TOKEN=le-jeton-affiche-par-le-script
python earthcam_live_map.py
```

Expose-le au VPS par un tunnel sortant — Cloudflare Tunnel ou Tailscale — **sans jamais
ouvrir de port sur ta box**. Puis renseigne l'URL obtenue dans
`/etc/systemd/system/carte.service`, ligne `CARTE_IA_URL`, et `systemctl daemon-reload
&& systemctl restart carte`.

## Limites à connaître

**Un seul utilisateur à la fois.** L'état est global : une détection, un lot, une vue.
À plusieurs simultanément, ça se marche dessus. C'est le chantier à faire avant
d'ouvrir à d'autres personnes.

**Le quota de l'API d'IA est partagé** entre tous les visiteurs.

**Les conditions d'utilisation des fournisseurs de webcams.** Rediffuser publiquement
leurs flux n'a pas le même statut qu'un usage personnel. À vérifier avant d'ouvrir
au-delà de tes proches.

## Vérifier que ça tourne

```bash
systemctl status carte
journalctl -u carte -f
curl -H "Authorization: Bearer LE_JETON" https://mondomaine.fr/api/status
```
