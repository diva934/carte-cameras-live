#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bench_geoloc.py — banc de mesure de la geolocalisation de photos.

Verite terrain : les cameras Fintraffic publient leurs coordonnees officielles.
On tire un echantillon reproductible (graine fixe), on fait passer chaque image
dans la chaine, et on compare a la position reelle.

  python bench_geoloc.py                    20 cameras, chaine complete
  python bench_geoloc.py -n 8 --sans-vlm    GeoCLIP seul (rapide, sans quota API)
  python bench_geoloc.py --brique geoclip   compare une brique isolee

Le but est de pouvoir dire OUI ou NON a une idee en dix minutes, avec des chiffres.
La grille dense a ete abandonnee grace a ce genre de mesure.
"""
import argparse, base64, io, json, os, random, statistics, sys, time, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
os.chdir(BASE)
STATIONS = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
IMAGE = "https://weathercam.digitraffic.fi/%s.jpg"


MONDE = os.path.join(BASE, "windy_webcams.json")


def echantillon(n, graine, source="monde"):
    """Deux jeux de test :
      monde       25 000 webcams mondiales (urbain, cotier, montagne, rural) — representatif
      fintraffic  cameras routieres finlandaises — cas adverse (foret et bitume, sans repere)
    Mesurer sur le seul jeu finlandais donnait un verdict trop pessimiste."""
    if source == "monde":
        with open(MONDE, encoding="utf-8") as f:
            cams = json.load(f)
        cams = [c for c in cams if c.get("img") and isinstance(c.get("lat"), (int, float))]
        random.Random(graine).shuffle(cams)
        return [{"id": c["id"], "lat": c["lat"], "lng": c["lng"],
                 "nom": (c.get("place") or "")[:40], "img": c["img"]} for c in cams[:n]]
    import earthcam_live_map as app
    data = json.loads(app.http_get(STATIONS))
    feats = [f for f in data["features"]
             if f["properties"].get("collectionStatus") == "GATHERING" and f["properties"].get("presets")]
    random.Random(graine).shuffle(feats)
    out = []
    for f in feats[:n]:
        lng, lat = f["geometry"]["coordinates"][:2]
        out.append({"id": f["properties"]["presets"][0]["id"], "lat": lat, "lng": lng,
                    "nom": (f["properties"].get("name") or "")[:40], "img": None})
    return out


CACHE = os.path.join(BASE, "_bench_cache")


def telecharge(cam_id, path, cache=True, refresh=False, url=None):
    """Les cameras sont en direct : sans cache, deux mesures ne portent pas sur la
    meme image et ne sont pas comparables. Le cache fige le jeu de test."""
    garde = os.path.join(CACHE, cam_id + ".jpg")
    if cache and not refresh and os.path.isfile(garde):
        with open(garde, "rb") as f:
            blob = f.read()
    else:
        req = urllib.request.Request(url or (IMAGE % cam_id), headers={
            "User-Agent": "Mozilla/5.0 (compatible; LivePublicCamMap/bench)",
            "Digitraffic-User": "LivePublicCamMap"})
        with urllib.request.urlopen(req, timeout=40) as r:
            blob = r.read()
        if cache:
            os.makedirs(CACHE, exist_ok=True)
            with open(garde, "wb") as f:
                f.write(blob)
    with open(path, "wb") as f:
        f.write(blob)
    return blob


def mesure(args):
    import earthcam_live_map as app
    import photo_osint as po
    cams = echantillon(args.n, args.graine, args.source)
    print("Banc de mesure : %d cameras, graine %d, brique '%s'\n" % (len(cams), args.graine, args.brique))
    lignes, erreurs, temps = [], [], []
    tmp = os.path.join(BASE, "_bench_tmp.jpg")
    for i, cam in enumerate(cams, 1):
        try:
            blob = telecharge(cam["id"], tmp, cache=not args.sans_cache, refresh=args.rafraichir, url=cam.get("img"))
        except Exception as e:
            print("  %2d/%d %-10s telechargement impossible (%s)" % (i, len(cams), cam["id"], str(e)[:40]))
            continue
        t0 = time.time()
        try:
            if args.brique == "geoclip":
                cands = app.photo_geoclip(tmp, 1)
                pos = (cands[0]["lat"], cands[0]["lng"]) if cands else None
                detail = "%.1f%%" % (cands[0]["score"] * 100) if cands else "-"
            elif args.brique == "streetclip":
                r = po.streetclip_country(tmp)
                pays = (r.get("pays") or [{}])[0]
                pos, detail = None, "%s %.0f%%" % (pays.get("nom", "?"), 100 * pays.get("score", 0))
            elif args.brique == "ocr":
                r = po.ocr_read(tmp)
                pos = None
                detail = ", ".join(t["texte"] for t in (r.get("textes") or [])[:3]) or "(aucun texte)"
            else:
                r = app.photo_locate({"image": base64.b64encode(blob).decode(),
                                      "vlm": not args.sans_vlm, "verify": False,
                                      "streetclip": not args.sans_streetclip})
                best = r.get("best") or {}
                pos = (best.get("lat"), best.get("lng")) if best.get("lat") is not None else None
                detail = (best.get("source") or "-")[:28]
        except Exception as e:
            print("  %2d/%d %-10s ECHEC : %s" % (i, len(cams), cam["id"], str(e)[:60]))
            continue
        dt = time.time() - t0
        temps.append(dt)
        if pos:
            km = app.haversine_km(cam["lat"], cam["lng"], pos[0], pos[1])
            erreurs.append(km)
            lignes.append((cam["id"], km, detail, dt))
            print("  %2d/%d %-10s %8.1f km  %-30s %5.1fs" % (i, len(cams), cam["id"], km, detail, dt))
        else:
            lignes.append((cam["id"], None, detail, dt))
            print("  %2d/%d %-10s %8s     %-30s %5.1fs" % (i, len(cams), cam["id"], "-", detail, dt))
    try:
        os.remove(tmp)
    except OSError:
        pass
    print("\n" + "=" * 72)
    if erreurs:
        erreurs.sort()
        print("  echantillon      : %d mesures" % len(erreurs))
        print("  erreur MEDIANE   : %8.1f km" % statistics.median(erreurs))
        print("  erreur moyenne   : %8.1f km" % (sum(erreurs) / len(erreurs)))
        print("  meilleure / pire : %.1f km / %.1f km" % (erreurs[0], erreurs[-1]))
        for seuil in (1, 5, 25, 100, 500):
            n = sum(1 for e in erreurs if e <= seuil)
            print("  sous %4d km     : %2d/%d (%.0f%%)" % (seuil, n, len(erreurs), 100.0 * n / len(erreurs)))
    else:
        print("  aucune position produite (brique sans coordonnees)")
    if temps:
        print("  temps median     : %.1f s par image" % statistics.median(temps))
    print("=" * 72)
    if args.sortie:
        with open(args.sortie, "w", encoding="utf-8") as f:
            json.dump({"brique": args.brique, "graine": args.graine,
                       "source": args.source,
                       "mesures": [{"id": a, "km": b, "detail": c, "s": round(d, 1)} for a, b, c, d in lignes],
                       "mediane_km": statistics.median(erreurs) if erreurs else None},
                      f, ensure_ascii=False, indent=1)
        print("Resultats ecrits dans", args.sortie)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Banc de mesure de la geolocalisation")
    p.add_argument("-n", type=int, default=20, help="nombre de cameras (defaut 20)")
    p.add_argument("--graine", type=int, default=7, help="graine du tirage, pour comparer a l'identique")
    p.add_argument("--brique", default="complet",
                   choices=["complet", "geoclip", "streetclip", "ocr"],
                   help="chaine complete ou une brique isolee")
    p.add_argument("--sans-vlm", action="store_true", help="sans le modele vision (pas de quota API)")
    p.add_argument("--sans-streetclip", action="store_true", help="sans le second avis StreetCLIP")
    p.add_argument("--sortie", help="fichier JSON de resultats")
    p.add_argument("--sans-cache", action="store_true", help="retelecharger a chaque fois (mesures non comparables)")
    p.add_argument("--rafraichir", action="store_true", help="renouveler les images du cache")
    p.add_argument("--source", default="monde", choices=["monde", "fintraffic"],
                   help="jeu de test : monde (25 000 webcams) ou fintraffic (cas adverse)")
    mesure(p.parse_args())
