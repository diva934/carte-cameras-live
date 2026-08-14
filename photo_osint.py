#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
photo_osint.py — briques d'analyse OSINT d'une photo, utilisees par earthcam_live_map.py

  metadata_full(path)      metadonnees completes (EXIF / XMP / IPTC, appareil, logiciel)
  jpeg_forensics(path)     indices de retouche : tables de quantification, ELA, bruit
  sun_analysis(...)        chronolocalisation : position du soleil, coherence des ombres
  weather_check(...)       meteo historique du jour et du lieu (Open-Meteo, sans cle)
  overpass_verify(...)     le terrain contient-il vraiment ce qui est ecrit sur les panneaux
  anonymize(path, out)     floutage des personnes et des vehicules avant archivage

Aucune de ces fonctions n'identifie de personne : elles portent sur le lieu,
la date et l'authenticite de l'image.
"""
import json, math, os, re, time, urllib.parse, urllib.request

UA = "LivePublicCamMap/1.0 (analyse OSINT locale)"
# kumi en premier : le serveur principal est souvent sature aux heures pleines
OVERPASS_URLS = ("https://overpass.kumi.systems/api/interpreter",
                 "https://overpass-api.de/api/interpreter")
METEO_URL = "https://archive-api.open-meteo.com/v1/archive"


def _get(url, timeout=25, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- OCR de scene
# RapidOCR = modeles PP-OCR (PaddleOCR) servis par ONNX Runtime : pas de paddlepaddle
# a installer sous Windows, 0,7 s par image en CPU.
_OCR = {"net": None, "err": None}


def ocr_engine():
    if _OCR["net"] is None and not _OCR["err"]:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR["net"] = RapidOCR()
        except Exception as e:
            _OCR["err"] = str(e)[:200]
    return _OCR["net"]


def ocr_read(path, second_pass=True):
    """Lecture des panneaux et enseignes. Deux passes : l'image entiere, puis un
    recadrage agrandi de chaque zone detectee — mesure : 'Tie 25 Vihti, Myllylampi'
    passe de 0.93 en bloc a trois jetons propres a 0.96-1.00."""
    net = ocr_engine()
    if net is None:
        return {"erreur": _OCR["err"] or "OCR indisponible", "textes": []}
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return {"erreur": "image illisible", "textes": []}
        H, W = img.shape[:2]
        first, _ = net(path)
        found = {}

        def keep(txt, score):
            t = str(txt).strip()
            if len(t) < 2 or score < 0.55:
                return
            prev = found.get(t.lower())
            if prev is None or score > prev["score"]:
                found[t.lower()] = {"texte": t, "score": round(float(score), 2)}

        for box, txt, score in (first or []):
            keep(txt, score)
        if second_pass:
            for box, txt, score in (first or [])[:8]:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                mx, my = (max(xs) - min(xs)) * 0.45, (max(ys) - min(ys)) * 0.9
                x1, y1 = int(max(0, min(xs) - mx)), int(max(0, min(ys) - my))
                x2, y2 = int(min(W, max(xs) + mx)), int(min(H, max(ys) + my))
                crop = img[y1:y2, x1:x2]
                if crop.size == 0:
                    continue
                big = cv2.resize(crop, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
                again, _ = net(big)
                for _b, t2, s2 in (again or []):
                    keep(t2, s2)
        textes = sorted(found.values(), key=lambda x: -x["score"])[:14]
        return {"textes": textes, "moteur": "RapidOCR / PP-OCR"}
    except Exception as e:
        return {"erreur": str(e)[:200], "textes": []}


# ---------------------------------------------------------------- metadonnees
CAM_TAGS = {271: "marque", 272: "modele", 305: "logiciel", 306: "date_fichier",
            42036: "objectif", 42033: "numero_serie", 36867: "date_prise_de_vue",
            33434: "temps_pose", 33437: "ouverture", 34855: "iso", 37386: "focale",
            274: "orientation", 40962: "largeur", 40963: "hauteur"}
EDITORS = re.compile(r"photoshop|lightroom|gimp|snapseed|picsart|facetune|midjourney|"
                     r"stable\s*diffusion|dall|firefly|canva|remini", re.I)


def metadata_full(path):
    """Tout ce que le fichier raconte sur lui-meme. Le champ 'logiciel' est le plus
    parlant : il trahit une retouche ou une generation."""
    out = {"exif": {}, "xmp": None, "alertes": []}
    try:
        from PIL import Image
        with Image.open(path) as im:
            out["format"] = im.format
            out["taille"] = list(im.size)
            out["mode"] = im.mode
            exif = im.getexif()
            for tag, name in CAM_TAGS.items():
                if tag in exif:
                    value = exif[tag]
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", "replace")
                    out["exif"][name] = str(value)[:160]
            xmp = getattr(im, "info", {}).get("XML:com.adobe.xmp") or ""
            if xmp:
                out["xmp"] = str(xmp)[:1500]
    except Exception as e:
        out["erreur"] = str(e)[:200]
        return out
    # exifread lit les blocs proprietaires (MakerNote) que PIL ignore ;
    # si l'utilisateur a installe exiftool, on prefere celui-ci, c'est la reference.
    try:
        import shutil, subprocess
        binary = shutil.which("exiftool")
        if binary:
            raw = subprocess.run([binary, "-j", "-n", path], capture_output=True,
                                 timeout=25, text=True).stdout
            data = (json.loads(raw) or [{}])[0]
            out["exiftool"] = {k: str(v)[:120] for k, v in data.items()
                               if k not in ("SourceFile", "Directory", "FileName")}
            out["exif"].update({k.lower(): str(v)[:160] for k, v in data.items()
                                if k in ("Make", "Model", "Software", "LensModel",
                                         "SerialNumber", "CreateDate")})
        else:
            import exifread
            with open(path, "rb") as f:
                tags = exifread.process_file(f, details=False)
            extra = {}
            for key, val in tags.items():
                short = key.split(" ", 1)[-1]
                if short in ("Make", "Model", "Software", "LensModel", "BodySerialNumber",
                             "DateTimeOriginal", "Artist", "Copyright", "HostComputer"):
                    extra[short.lower()] = str(val)[:160]
            if extra:
                out["exif"].update(extra)
                out["lecteur"] = "exifread"
    except Exception:
        pass
    blob = " ".join([str(v) for v in out["exif"].values()] + [str(out.get("xmp") or "")])
    hit = EDITORS.search(blob)
    if hit:
        out["alertes"].append("logiciel de retouche ou de generation detecte : " + hit.group(0))
    if not out["exif"]:
        out["alertes"].append("aucune metadonnee : image nettoyee, capture d'ecran, ou re-encodee")
    if out["exif"].get("date_prise_de_vue"):
        out["date"] = out["exif"]["date_prise_de_vue"]
    return out


# ---------------------------------------------------------------- forensique
def jpeg_forensics(path):
    """Indices (jamais preuves) d'une image retouchee ou re-encodee.
    ELA : une zone recompressee reagit differemment a une nouvelle compression."""
    res = {"alertes": [], "ela_max": None, "ela_moyen": None, "tables_quant": None}
    try:
        import numpy as np
        from PIL import Image, ImageChops
        with Image.open(path) as im:
            if im.format != "JPEG":
                res["note"] = "analyse ELA pertinente surtout sur du JPEG (ici %s)" % im.format
            qt = getattr(im, "quantization", None)
            if qt:
                res["tables_quant"] = len(qt)
                base = sum(sum(t) for t in qt.values()) / max(1, sum(len(t) for t in qt.values()))
                res["qualite_estimee"] = round(max(0.0, min(100.0, 100.0 - base * 1.6)), 1)
                if base < 3:
                    res["alertes"].append("compression tres faible : image probablement re-enregistree "
                                          "en qualite maximale par un logiciel")
            rgb = im.convert("RGB")
            tmp = path + ".ela.jpg"
            rgb.save(tmp, "JPEG", quality=90)
            with Image.open(tmp) as again:
                diff = ImageChops.difference(rgb, again)
            arr = np.asarray(diff, dtype="float32")
            res["ela_max"] = round(float(arr.max()), 1)
            res["ela_moyen"] = round(float(arr.mean()), 2)
            # une zone nettement plus lumineuse que le reste = recompression locale
            gray = arr.mean(axis=2)
            h, w = gray.shape
            bs = max(16, min(h, w) // 12)
            blocks = [gray[y:y + bs, x:x + bs].mean()
                      for y in range(0, h - bs + 1, bs) for x in range(0, w - bs + 1, bs)]
            if blocks:
                blocks.sort()
                med = blocks[len(blocks) // 2]
                top = blocks[-1]
                res["ecart_bloc"] = round(float(top - med), 2)
                if med > 0.3 and top > med * 6 and top > 12:
                    res["alertes"].append("une zone reagit tres differemment du reste a la "
                                          "recompression : retouche locale possible")
        try:
            os.remove(tmp)
        except OSError:
            pass
    except Exception as e:
        res["erreur"] = str(e)[:200]
    return res


# ---------------------------------------------------------------- soleil
def sun_position(lat, lng, when):
    """Azimut et hauteur du soleil (algorithme NOAA simplifie). when = datetime UTC."""
    import datetime
    day = when.timetuple().tm_yday
    hour = when.hour + when.minute / 60.0 + when.second / 3600.0
    gamma = 2 * math.pi / 365.0 * (day - 1 + (hour - 12) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    time_offset = eqtime + 4 * lng
    tst = hour * 60 + time_offset
    ha = math.radians(tst / 4.0 - 180.0)
    la = math.radians(lat)
    cos_zen = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    cos_zen = max(-1.0, min(1.0, cos_zen))
    zenith = math.acos(cos_zen)
    elevation = 90.0 - math.degrees(zenith)
    try:
        cos_az = ((math.sin(la) * math.cos(zenith) - math.sin(decl))
                  / (math.cos(la) * math.sin(zenith)))
        azimuth = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        azimuth = 180.0 - azimuth if ha > 0 else 180.0 + azimuth
    except ZeroDivisionError:
        azimuth = 0.0
    return {"azimut": round(azimuth % 360, 1), "hauteur": round(elevation, 1)}


def parse_exif_date(value):
    import datetime
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(str(value).strip()[:19], fmt)
        except (ValueError, TypeError):
            continue
    return None


def sun_analysis(lat, lng, date_str, ombres_visibles=None):
    """Chronolocalisation : ou etait le soleil, et est-ce compatible avec les ombres vues."""
    when = parse_exif_date(date_str)
    if when is None or lat is None or lng is None:
        return None
    sun = sun_position(lat, lng, when)
    out = {"date": when.strftime("%Y-%m-%d %H:%M"), "azimut": sun["azimut"],
           "hauteur": sun["hauteur"], "coherent": None}
    if sun["hauteur"] < -6:
        out["moment"] = "nuit"
    elif sun["hauteur"] < 6:
        out["moment"] = "aube ou crepuscule"
    elif sun["hauteur"] < 25:
        out["moment"] = "soleil bas (ombres longues)"
    else:
        out["moment"] = "soleil haut (ombres courtes)"
    if ombres_visibles is not None:
        attendu = sun["hauteur"] > 3
        out["coherent"] = bool(ombres_visibles) == attendu
        if not out["coherent"]:
            out["alerte"] = ("des ombres marquees alors que le soleil est sous l'horizon"
                             if ombres_visibles else
                             "aucune ombre alors que le soleil est haut")
    return out


# ---------------------------------------------------------------- meteo
def weather_check(lat, lng, date_str, observations=None):
    """Meteo reellement observee ce jour-la a cet endroit (Open-Meteo, archive, sans cle).
    Sert a confirmer ou a infirmer une hypothese de lieu ou de date."""
    when = parse_exif_date(date_str)
    if when is None or lat is None or lng is None:
        return None
    day = when.strftime("%Y-%m-%d")
    url = (METEO_URL + "?" + urllib.parse.urlencode({
        "latitude": round(lat, 3), "longitude": round(lng, 3),
        "start_date": day, "end_date": day, "timezone": "UTC",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,cloud_cover_mean"}))
    try:
        d = json.loads(_get(url, timeout=20)).get("daily") or {}
        pick = lambda k: (d.get(k) or [None])[0]
        out = {"date": day, "t_max": pick("temperature_2m_max"), "t_min": pick("temperature_2m_min"),
               "pluie_mm": pick("precipitation_sum"), "neige_cm": pick("snowfall_sum"),
               "nuages_pct": pick("cloud_cover_mean")}
    except Exception as e:
        return {"erreur": str(e)[:160]}
    resume = []
    if out["neige_cm"]:
        resume.append("neige (%.1f cm)" % out["neige_cm"])
    if out["pluie_mm"]:
        resume.append("precipitations (%.1f mm)" % out["pluie_mm"])
    if out["t_max"] is not None:
        resume.append("%.0f a %.0f degres" % (out["t_min"], out["t_max"]))
    if out["nuages_pct"] is not None:
        resume.append("couverture nuageuse %.0f%%" % out["nuages_pct"])
    out["resume"] = ", ".join(resume) or "donnees indisponibles"
    if observations:
        texte = " ".join(observations).lower()
        neige_vue = any(w in texte for w in ("neige", "enneig", "snow"))
        neige_reelle = bool(out["neige_cm"])
        if neige_vue != neige_reelle and out["neige_cm"] is not None:
            out["alerte"] = ("de la neige est visible mais il n'en est pas tombe ce jour-la"
                             if neige_vue else
                             "il a neige ce jour-la mais aucune neige n'est visible")
            out["coherent"] = False
        else:
            out["coherent"] = True
    return out


# ---------------------------------------------------------------- Overpass
def _overpass(query):
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last = None
    for url in OVERPASS_URLS:
        try:
            return json.loads(_get(url, timeout=40, data=body))
        except Exception as e:
            last = e
    raise last


def overpass_verify(lat, lng, noms=None, refs=None, rayon_km=15):
    """Le terrain contient-il ce que les panneaux annoncent ?
    noms : toponymes lus. refs : numeros de route lus (ex. 25).
    Une correspondance a cet endroit precis est une preuve tres forte."""
    noms = [n for n in (noms or []) if len(n) >= 3][:6]
    refs = [str(r) for r in (refs or []) if str(r).strip()][:4]
    if not noms and not refs:
        return None
    radius = int(rayon_km * 1000)
    parts = []
    for n in noms:
        # correspondance exacte : l'index des noms est utilise, la requete reste rapide.
        # Une regex sur un grand rayon fait expirer l'API publique.
        esc = n.replace('"', '').replace('\\', '')
        parts.append('nwr(around:%d,%f,%f)["name"="%s"];' % (radius, lat, lng, esc))
        if esc[:1].isupper():
            parts.append('nwr(around:%d,%f,%f)["name"="%s"];' % (radius, lat, lng, esc.capitalize()))
    for r in refs:
        esc = r.replace('"', '').replace('\\', '')
        parts.append('way(around:%d,%f,%f)["ref"~"(^|;)[A-Za-z ]*%s($|;)"];' % (radius, lat, lng, esc))
    query = "[out:json][timeout:25];(" + "".join(parts) + ");out tags center 30;"
    try:
        data = _overpass(query)
    except Exception as e:
        return {"erreur": str(e)[:160]}
    trouves, vus = [], set()
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        label = tags.get("name") or tags.get("ref") or ""
        if not label or label.lower() in vus:
            continue
        vus.add(label.lower())
        center = el.get("center") or {}
        trouves.append({"nom": label[:80],
                        "type": tags.get("highway") or tags.get("place") or el.get("type"),
                        "lat": round(el.get("lat", center.get("lat", 0.0)), 5),
                        "lng": round(el.get("lon", center.get("lon", 0.0)), 5)})
    attendus = [x.lower() for x in noms + refs]
    confirmes = [t for t in trouves if any(a in t["nom"].lower() or t["nom"].lower() in a
                                           for a in attendus)]
    return {"cherches": noms + refs, "trouves": trouves[:12], "confirmes": len(confirmes),
            "verdict": ("confirme" if confirmes else ("aucune correspondance" if trouves
                        else "rien trouve dans le rayon"))}


def road_refs(textes):
    """Numeros de route lisibles sur les panneaux (Tie 25, A7, E18, RN 4...)."""
    refs = []
    for t in (textes or []):
        for m in re.findall(r"\b(?:tie|vag|väg|road|route|rn|rd|autoroute|hwy|[AENDM])\s*[-]?\s*(\d{1,4})\b",
                            str(t), re.I):
            refs.append(m)
        for m in re.findall(r"\b([AENDM]\s?\d{1,3})\b", str(t)):
            refs.append(m.replace(" ", ""))
    out, seen = [], set()
    for r in refs:
        if r.lower() not in seen:
            seen.add(r.lower())
            out.append(r)
    return out[:4]


# ---------------------------------------------------------------- StreetCLIP
# Second avis independant de GeoCLIP : entraine sur 1,1 M d'images de rue, il classe
# une photo par pays en zero-shot. Licence CC-BY-NC-4.0 : usage non commercial.
_SCLIP = {"model": None, "proc": None, "err": None, "device": "cpu"}
PAYS = ["France", "Allemagne", "Espagne", "Italie", "Portugal", "Royaume-Uni", "Irlande",
        "Belgique", "Pays-Bas", "Suisse", "Autriche", "Pologne", "Tchequie", "Suede",
        "Norvege", "Finlande", "Danemark", "Estonie", "Russie", "Ukraine", "Grece",
        "Turquie", "Etats-Unis", "Canada", "Mexique", "Bresil", "Argentine", "Chili",
        "Japon", "Coree du Sud", "Chine", "Inde", "Thailande", "Indonesie", "Australie",
        "Nouvelle-Zelande", "Afrique du Sud", "Maroc", "Egypte", "Israel"]
PAYS_EN = {"France": "France", "Allemagne": "Germany", "Espagne": "Spain", "Italie": "Italy",
           "Portugal": "Portugal", "Royaume-Uni": "the United Kingdom", "Irlande": "Ireland",
           "Belgique": "Belgium", "Pays-Bas": "the Netherlands", "Suisse": "Switzerland",
           "Autriche": "Austria", "Pologne": "Poland", "Tchequie": "Czechia", "Suede": "Sweden",
           "Norvege": "Norway", "Finlande": "Finland", "Danemark": "Denmark", "Estonie": "Estonia",
           "Russie": "Russia", "Ukraine": "Ukraine", "Grece": "Greece", "Turquie": "Turkey",
           "Etats-Unis": "the United States", "Canada": "Canada", "Mexique": "Mexico",
           "Bresil": "Brazil", "Argentine": "Argentina", "Chili": "Chile", "Japon": "Japan",
           "Coree du Sud": "South Korea", "Chine": "China", "Inde": "India",
           "Thailande": "Thailand", "Indonesie": "Indonesia", "Australie": "Australia",
           "Nouvelle-Zelande": "New Zealand", "Afrique du Sud": "South Africa",
           "Maroc": "Morocco", "Egypte": "Egypt", "Israel": "Israel"}


def gpu_libre_go():
    """VRAM libre en Go, 0 si pas de GPU. Sur une carte 6 Go, GeoCLIP (1,7 Go) + YOLO +
    Real-ESRGAN saturent vite : les modeles secondaires vont sur le CPU plutot que
    de faire tomber toute l'application."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        libre, _total = torch.cuda.mem_get_info()
        return libre / (1024 ** 3)
    except Exception:
        return 0.0


def choisir_device(besoin_go=2.0):
    return "cuda" if gpu_libre_go() >= besoin_go else "cpu"


def streetclip_country(path, top_k=3):
    """Classement par pays, independant de GeoCLIP. Deux modeles qui s'accordent,
    c'est une preuve ; deux qui divergent, c'est un signal d'incertitude."""
    if _SCLIP["err"]:
        return {"erreur": _SCLIP["err"]}
    try:
        import torch
        from PIL import Image
        if _SCLIP["model"] is None:
            from transformers import CLIPModel, CLIPConfig, CLIPProcessor
            from huggingface_hub import hf_hub_download
            # StreetCLIP n'est publie qu'en .bin, et transformers 4.57 refuse torch.load
            # sous torch < 2.6. On charge le state dict nous-memes plutot que de toucher
            # a l'installation torch/CUDA qui fait tourner GeoCLIP et YOLO.
            cfg = CLIPConfig.from_pretrained("geolocal/StreetCLIP")
            model = CLIPModel(cfg)
            weights = hf_hub_download("geolocal/StreetCLIP", "pytorch_model.bin")
            state = torch.load(weights, map_location="cpu", weights_only=True)
            missing, unexpected = model.load_state_dict(state, strict=False)
            if len(missing) > 40:
                raise RuntimeError("poids StreetCLIP incompatibles (%d manquants)" % len(missing))
            _SCLIP["model"] = model
            _SCLIP["proc"] = CLIPProcessor.from_pretrained("geolocal/StreetCLIP")
            dev = choisir_device(2.2)
            if dev == "cuda":
                _SCLIP["model"] = _SCLIP["model"].to("cuda")
            _SCLIP["device"] = dev
            _SCLIP["model"].eval()
        prompts = ["A Street View photo in %s." % PAYS_EN[p] for p in PAYS]
        with Image.open(path) as im:
            inputs = _SCLIP["proc"](text=prompts, images=im.convert("RGB"),
                                    return_tensors="pt", padding=True)
        device = next(_SCLIP["model"].parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            logits = _SCLIP["model"](**inputs).logits_per_image.softmax(dim=-1)[0]
        order = torch.topk(logits, min(top_k, len(PAYS)))
        return {"pays": [{"nom": PAYS[i], "score": round(float(s), 4)}
                         for s, i in zip(order.values.tolist(), order.indices.tolist())],
                "modele": "StreetCLIP (CC-BY-NC-4.0)"}
    except Exception as e:
        _SCLIP["err"] = str(e)[:200]
        return {"erreur": _SCLIP["err"]}


# ---------------------------------------------------------------- appariement
# SuperPoint + LightGlue sont fournis par transformers : on peut confronter la photo
# a une image de reference (camera publique proche) et compter les correspondances.
_GLUE = {"model": None, "proc": None, "err": None}


def match_images(path_a, path_b, min_score=0.6):
    """Nombre de points caracteristiques communs entre deux images.
    Beaucoup de correspondances coherentes = meme endroit, pas une ressemblance."""
    if _GLUE["err"]:
        return {"erreur": _GLUE["err"]}
    try:
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor, AutoModel
        if _GLUE["model"] is None:
            _GLUE["proc"] = AutoImageProcessor.from_pretrained("ETH-CVG/lightglue_superpoint")
            _GLUE["model"] = AutoModel.from_pretrained("ETH-CVG/lightglue_superpoint")
            if choisir_device(1.2) == "cuda":
                _GLUE["model"] = _GLUE["model"].to("cuda")
            _GLUE["model"].eval()
        with Image.open(path_a) as a, Image.open(path_b) as b:
            pair = [[a.convert("RGB"), b.convert("RGB")]]
            inputs = _GLUE["proc"](pair, return_tensors="pt")
        device = next(_GLUE["model"].parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            out = _GLUE["model"](**inputs)
        scores = out.matching_scores[0]
        matches = out.matches[0]
        valid = ((matches > -1) & (scores > min_score))
        n = int(valid.sum().item())
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
        return {"correspondances": n, "score_moyen": round(float(scores[valid].mean().item()), 3) if n else 0.0,
                "verdict": ("meme lieu (tres probable)" if n >= 30 else
                            ("scene proche" if n >= 12 else "aucune correspondance"))}
    except Exception as e:
        _GLUE["err"] = str(e)[:200]
        return {"erreur": _GLUE["err"]}


# ---------------------------------------------------------------- anonymisation
_YOLO = {"net": None, "err": None}
BLUR_CLASSES = {0: "personne", 1: "velo", 2: "voiture", 3: "moto", 5: "bus", 7: "camion"}


def anonymize(path, out_path, classes=(0, 2, 3, 5, 7), force=45):
    """Floute personnes et vehicules avant archivage ou partage d'un rapport.
    Le floutage porte sur la boite detectee : c'est volontairement large."""
    try:
        import cv2
        if _YOLO["net"] is None and not _YOLO["err"]:
            try:
                from ultralytics import YOLO
                here = os.path.dirname(os.path.abspath(__file__))
                weights = os.path.join(here, "yolo26n.pt")
                _YOLO["net"] = YOLO(weights if os.path.exists(weights) else "yolov8n.pt")
            except Exception as e:
                _YOLO["err"] = str(e)[:200]
        if _YOLO["err"]:
            return {"ok": False, "erreur": _YOLO["err"]}
        img = cv2.imread(path)
        if img is None:
            return {"ok": False, "erreur": "image illisible"}
        res = _YOLO["net"].predict(img, conf=0.25, verbose=False, classes=list(classes))
        n = 0
        for r in res:
            for box in (r.boxes or []):
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
                if x2 - x1 < 4 or y2 - y1 < 4:
                    continue
                zone = img[y1:y2, x1:x2]
                k = max(9, (min(zone.shape[:2]) // 3) | 1)
                img[y1:y2, x1:x2] = cv2.GaussianBlur(zone, (k, k), force)
                n += 1
        cv2.imwrite(out_path, img)
        return {"ok": True, "floutes": n, "fichier": out_path}
    except Exception as e:
        return {"ok": False, "erreur": str(e)[:200]}
