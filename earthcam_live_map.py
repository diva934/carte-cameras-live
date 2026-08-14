#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Public Cam Map — vraies cameras publiques temps reel (reseaux ouverts, sans cle) :
  - WhatsUpCams : webcams video HLS (Europe)
  - TfL JamCams : ~880 cameras trafic de Londres (video MP4)
  - Fintraffic Digitraffic : ~810 cameras route/meteo de Finlande (images HD)
  - Cables de telecommunication sous-marins (TeleGeography)
Detection YOLO26 + ByteTrack dans un post-it superpose a la video.

Usage : python earthcam_live_map.py   ->  fenetre app "Carte Cameras Live"
"""
import json, re, time, threading, webbrowser, urllib.parse, urllib.request, urllib.error, subprocess, sys, os, html as html_lib, concurrent.futures, csv, io, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8770
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
GEOCACHE_FILE = "geocache.json"
WUC_CACHE_FILE = "whatsupcams.json"
SKY_CACHE_FILE = "skylinewebcams.json"
TAXI_CACHE_FILE = "webcamtaxi.json"
HOPPER_CACHE_FILE = "webcamhopper.json"
PLANES_CACHE_FILE = "planes.json"
PLANES_USAGE_FILE = "planes_usage.json"
AIRPORTS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "airports_major.json")
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"

WUC_BASE = "https://www.whatsupcams.com/en/webcams/"
TFL_URL = "https://api.tfl.gov.uk/Place/Type/JamCam"
FIN_URL = "https://tie.digitraffic.fi/api/weathercam/v1/stations"
CABLES_URL = "https://www.submarinecablemap.com/api/v3/cable/cable-geo.json"
SKY_BASE = "https://www.skylinewebcams.com/"
SKY_INDEX = SKY_BASE + "en/webcam.html"
TAXI_BASE = "https://www.webcamtaxi.com/"
TAXI_ALL = TAXI_BASE + "en/webcams.html"
TAXI_MAP = TAXI_BASE + "en/map.html"
HOPPER_BASE = "https://www.webcamhopper.com/"
HOPPER_COUNTRIES = HOPPER_BASE + "countries.html"
TAXI_FALLBACKS = {
    "/en/turkey/mugla-province/fethiye-cam.html": (36.6514, 29.1231),
    "/en/turkey/mugla-province/icmeler-central-square.html": (36.7931, 28.2324),
    "/en/norway/oslo-county/oslo-skyline-cam.html": (59.9139, 10.7522),
    "/en/norway/oslo-county/views-of-norway-multicam.html": (59.9139, 10.7522),
    "/en/rolling-cams/beaches.html": (32.7607, -16.9595),
    "/en/rolling-cams/madeira-island.html": (32.7607, -16.9595),
}

WUC = {"cams": [], "updated": 0, "error": None}
TFL = {"cams": [], "updated": 0, "error": None}
FIN = {"cams": [], "updated": 0, "error": None}
EARTH = {"cams": [], "updated": 0, "error": None}
SKY = {"cams": [], "updated": 0, "error": None}
TAXI = {"cams": [], "updated": 0, "error": None}
HOPPER = {"cams": [], "updated": 0, "error": None}
NYDOT = {"cams": [], "updated": 0, "error": None}
NYDOT_CACHE_FILE = "nysdot_cams.json"
PLANES = {"list": [], "updated": 0, "error": None, "source": "", "retry_at": 0, "center": [50.0, 8.0]}
PLANES_VIEW = {"lat": 50.0, "lng": 8.0, "radius": 250.0, "active_until": 0, "version": 0}
PLANES_USAGE = {"day": "", "airplanes_live": 0}
AIS_DB = {}                                   # mmsi -> [lat, lng, cog, sog, name, type, ts]
AIS = {"updated": 0, "error": None}
AIRPORTS = {"list": [], "updated": 0, "error": None, "source": "OurAirports"}
LLM_MODEL = os.environ.get("CARTE_LLM_MODEL", "qwen3:4b-instruct")
LLM_URL = "http://127.0.0.1:11434"
FLIGHT_ROUTE_CACHE = {}
EVENTS = {"list": [], "updated": 0}
CABLES = {"geojson": None}
EARTH_URL = "https://www.youtube.com/@earthcam/streams?hl=en&gl=US"
LANDMARKS = {
    "times square": (40.7580, -73.9855, "New York, NY"),
    "brooklyn bridge": (40.7061, -73.9969, "New York, NY"),
    "world trade center": (40.7127, -74.0134, "New York, NY"),
    "lincoln harbor": (40.7715, -74.0170, "New York, NY"),
    "statue of liberty": (40.6892, -74.0445, "New York, NY"),
    "liberty bell": (39.9496, -75.1503, "Philadelphia, PA"),
    "independence hall": (39.9489, -75.1500, "Philadelphia, PA"),
    "washington monument": (38.8895, -77.0353, "Washington, D.C."),
    "bourbon street": (29.9584, -90.0644, "New Orleans, LA"),
    "new orleans": (29.9511, -90.0715, "New Orleans, LA"),
    "abbey road": (51.5320, -0.1774, "London, UK"),
}
GENERIC = re.compile(r"\b(live|cam|camera|view|in\s*4k|4k|hd|webcam|streaming|"
                     r"paddock|balcony|aquarium|watering hole|animals and wildlife|"
                     r"marine|reef|beach)\b", re.I)
LOCK = threading.Lock()
DETECT = [None]   # un seul suivi de personne a la fois
DETECT_TOKEN = [None]

CC = {"hr": "Croatie", "it": "Italie", "at": "Autriche", "gr": "Grece", "es": "Espagne",
      "fr": "France", "de": "Allemagne", "ch": "Suisse", "si": "Slovenie", "me": "Montenegro",
      "ba": "Bosnie", "pt": "Portugal", "br": "Bresil", "au": "Australie", "eg": "Egypte",
      "nl": "Pays-Bas", "be": "Belgique", "pl": "Pologne", "cz": "Tchequie", "ie": "Irlande",
      "dk": "Danemark", "al": "Albanie", "cn": "Chine", "us": "Etats-Unis", "gb": "Royaume-Uni"}


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json, text/html, */*",
        "Accept-Encoding": "gzip",   # Digitraffic (Finlande + AIS) renvoie 406 sans gzip
        "Digitraffic-User": "LivePublicCamMap",
        "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+000"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            import gzip
            try:
                data = gzip.decompress(data)
            except Exception:
                pass
        return data.decode("utf-8", "replace")


def airports_load():
    cached = _load(AIRPORTS_CACHE_FILE, {})
    if isinstance(cached, dict) and isinstance(cached.get("list"), list):
        with LOCK:
            AIRPORTS.update(cached)
    # Une actualisation hebdomadaire suffit pour les coordonnees aeroportuaires.
    schema_ok = bool(AIRPORTS["list"] and isinstance(AIRPORTS["list"][0], list) and len(AIRPORTS["list"][0]) >= 14)
    if schema_ok and time.time() - float(AIRPORTS.get("updated") or 0) < 604800:
        return
    try:
        text = http_get(AIRPORTS_URL, timeout=45)
        runway_text = http_get(RUNWAYS_URL, timeout=45)
        runways = {}
        for row in csv.DictReader(io.StringIO(runway_text)):
            if row.get("closed") == "1":
                continue
            ident = row.get("airport_ident", "")
            try:
                length_ft = int(float(row.get("length_ft") or 0))
            except (TypeError, ValueError):
                length_ft = 0
            headings = []
            for key in ("le_heading_degT", "he_heading_degT", "le_heading_deg", "he_heading_deg"):
                try:
                    value = round(float(row.get(key)), 1)
                    if value not in headings:
                        headings.append(value)
                except (TypeError, ValueError):
                    pass
            info = runways.setdefault(ident, {"length": 0, "lighted": False, "headings": [], "paved": False})
            info["length"] = max(info["length"], length_ft)
            info["lighted"] = info["lighted"] or row.get("lighted") == "1"
            info["headings"] = list(dict.fromkeys(info["headings"] + headings))[:12]
            surface = str(row.get("surface") or "").upper()
            info["paved"] = info["paved"] or any(x in surface for x in ("ASP", "CON", "PEM", "BIT"))
        out = []
        for row in csv.DictReader(io.StringIO(text)):
            airport_type = row.get("type", "")
            scheduled = row.get("scheduled_service", "") == "yes"
            if airport_type == "closed_airport":
                continue
            if airport_type not in ("large_airport", "medium_airport") and not scheduled:
                continue
            try:
                lat = round(float(row.get("latitude_deg", "")), 6)
                lng = round(float(row.get("longitude_deg", "")), 6)
            except (TypeError, ValueError):
                continue
            runway = runways.get(row.get("ident", ""), {})
            out.append([
                row.get("ident", ""), row.get("iata_code", ""), row.get("name", ""),
                row.get("municipality", ""), lat, lng, airport_type,
                row.get("elevation_ft", ""), row.get("iso_country", ""), scheduled,
                int(runway.get("length") or 0), bool(runway.get("lighted")),
                runway.get("headings") or [], bool(runway.get("paved"))
            ])
        snapshot = {"list": out, "updated": int(time.time()), "error": None, "source": "OurAirports"}
        with LOCK:
            AIRPORTS.update(snapshot)
        _save(AIRPORTS_CACHE_FILE, snapshot)
        print("[Aeroports] %d charges" % len(out))
    except Exception as e:
        with LOCK:
            AIRPORTS["error"] = str(e)
        print("[Aeroports] erreur:", e)


def airports_loop():
    while True:
        airports_load()
        with LOCK:
            ready = bool(AIRPORTS["list"])
        time.sleep(604800 if ready else 60)


def local_llm_status():
    try:
        req = urllib.request.Request(LLM_URL + "/api/tags", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        models = [str(x.get("name") or "") for x in (data.get("models") or [])]
        installed = any(x == LLM_MODEL or x.split(":")[0] == LLM_MODEL.split(":")[0] for x in models)
        return {"online": True, "installed": installed, "model": LLM_MODEL, "models": models}
    except Exception as e:
        return {"online": False, "installed": False, "model": LLM_MODEL, "models": [], "error": str(e)}


def local_llm_analyze(payload):
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    facts = {
        "aircraft": str(payload.get("aircraft") or "")[:80],
        "icao": str(payload.get("icao") or "")[:20],
        "position": payload.get("position"),
        "altitude_ft": payload.get("altitude_ft"),
        "speed_kmh": payload.get("speed_kmh"),
        "heading_deg": payload.get("heading_deg"),
        "vertical_rate_fpm": payload.get("vertical_rate_fpm"),
        "signal_age_sec": payload.get("signal_age_sec"),
        "anomaly_score": payload.get("score"),
        "evidence": [str(x)[:220] for x in evidence[:8]],
        "nearby_losses": payload.get("nearby_losses"),
    }
    system = (
        "Tu es un analyste de donnees aeronautiques prudent. Explique en francais les anomalies ADS-B "
        "uniquement a partir des faits fournis. Ne presente jamais un brouillage, un spoofing, une action "
        "militaire ou une urgence comme certain. Distingue clairement observation, hypotheses et limites. "
        "Utilise le mot aeronef, jamais le mot anglais aircraft. Reponds en 3 a 5 phrases courtes, sans "
        "markdown, et termine par un niveau de confiance."
    )
    body = json.dumps({
        "model": LLM_MODEL, "stream": False,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
        "options": {"temperature": 0.1, "num_predict": 220, "num_ctx": 4096}
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(LLM_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8", "replace"))
    text = str(((data.get("message") or {}).get("content") or "")).strip()
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.I).strip()
    if not text:
        raise RuntimeError("reponse LLM vide")
    return {"ok": True, "text": text[:1800], "model": LLM_MODEL}


def flight_route_lookup(callsign):
    callsign = re.sub(r"[^A-Z0-9]", "", str(callsign or "").upper())[:12]
    if len(callsign) < 3:
        return {"ok": False, "callsign": callsign, "error": "indicatif absent"}
    now = time.time()
    with LOCK:
        cached = FLIGHT_ROUTE_CACHE.get(callsign)
        if cached and now - cached[0] < (21600 if cached[1].get("ok") else 1800):
            return dict(cached[1])
    try:
        url = "https://api.adsbdb.com/v0/callsign/" + urllib.parse.quote(callsign)
        data = planes_http_json(url, "ADSBDB", timeout=12)
        route = ((data.get("response") or {}).get("flightroute") or {})
        origin, destination = route.get("origin") or {}, route.get("destination") or {}
        if not origin or not destination:
            raise ValueError("route inconnue")
        result = {"ok": True, "callsign": callsign, "route": {
            "callsign": route.get("callsign") or callsign,
            "airline": route.get("airline") or {}, "origin": origin,
            "midpoint": route.get("midpoint"), "destination": destination,
            "source": "ADSBDB"
        }}
    except Exception as e:
        result = {"ok": False, "callsign": callsign, "error": str(e)[:180]}
    with LOCK:
        FLIGHT_ROUTE_CACHE[callsign] = (now, result)
    return dict(result)


# ---------------- geocache (pour WhatsUpCams) ----------------
def _load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

GEOCACHE = _load(GEOCACHE_FILE, {})

def geocode(place):
    key = place.lower().strip()
    if not key:
        return None
    if key in GEOCACHE:
        c = GEOCACHE[key]
        return (c[0], c[1]) if c[0] is not None else None
    try:
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": place, "format": "json", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": "LivePublicCamMap/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            arr = json.loads(r.read().decode("utf-8", "replace"))
        time.sleep(1.1)
        if arr:
            la, lo = float(arr[0]["lat"]), float(arr[0]["lon"])
            GEOCACHE[key] = [la, lo]; _save(GEOCACHE_FILE, GEOCACHE)
            return la, lo
    except Exception:
        pass
    GEOCACHE[key] = [None, None]; _save(GEOCACHE_FILE, GEOCACHE)
    return None


# ---------------- WhatsUpCams (HLS video) ----------------
def wuc_city_country(cid):
    cc = cid[:2]
    body = cid.split("_", 1)[1] if "_" in cid else cid
    city = re.sub(r"\d+$", "", body)
    city = re.sub(r"([a-z])([A-Z])", r"\1 \2", city)
    return city, CC.get(cc, cc.upper())

def wuc_scrape_ids():
    regions = set()
    try:
        home = http_get(WUC_BASE)
        for c in set(re.findall(r'href="(https://www\.whatsupcams\.com/en/webcams/[a-z-]+/)"', home)):
            try:
                h = http_get(c, timeout=20)
                for reg in re.findall(r'href="(https://www\.whatsupcams\.com/en/webcams/[a-z-]+/[a-z-]+/)"', h):
                    regions.add(reg)
            except Exception:
                pass
    except Exception:
        pass
    ids = {}
    for reg in regions:
        try:
            h = http_get(reg, timeout=20)
            for cid in set(re.findall(r'[a-z]{2}_[a-z]+\d{2,}', h)):
                if cid != "pl_fy2021":
                    ids[cid] = True
        except Exception:
            pass
    return list(ids.keys())

def wuc_loop():
    while True:
        try:
            ids = wuc_scrape_ids()
            out = []
            for cid in ids:
                city, country = wuc_city_country(cid)
                g = geocode(city + ", " + country)
                if not g:
                    continue
                out.append({"id": cid, "src": "hls", "title": city.title(),
                            "place": country, "lat": g[0], "lng": g[1]})
                with LOCK:
                    WUC["cams"] = list(out)
            with LOCK:
                WUC["cams"] = out; WUC["updated"] = int(time.time())
            if out:
                _save(WUC_CACHE_FILE, out)
            print("[WhatsUpCams] %d cameras" % len(out))
        except Exception as e:
            with LOCK:
                WUC["error"] = str(e)
            print("[WhatsUpCams] erreur:", e)
        time.sleep(3600)


# ---------------- SkylineWebcams (HLS video) ----------------
def _sky_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()

def _sky_place_part(value):
    return urllib.parse.unquote(value).replace("-", " ").strip().title()

def skyline_catalog():
    home = http_get(SKY_INDEX, timeout=35)
    countries = sorted(set(re.findall(
        r'href=["\']/?en/webcam/([^/"\']+)\.html["\']', home, re.I)))
    found = {}
    card_re = re.compile(
        r'<a\s+href="((?:/)?en/webcam/[^"]+\.html)"[^>]*>\s*'
        r'<div\s+class="cam-[^"]*">(.*?)</div>\s*</a>', re.I | re.S)
    for country_slug in countries:
        page = ""
        error = None
        for attempt in range(3):
            try:
                page = http_get(SKY_BASE + "en/webcam/%s.html" % country_slug, timeout=35)
                break
            except Exception as e:
                error = e
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        if not page:
            print("[Skyline] catalogue %s: %s" % (country_slug, error))
            continue
        for match in card_re.finditer(page):
            path, body = match.group(1).lstrip("/"), match.group(2)
            parts = path.split("/")
            if len(parts) < 6:
                continue
            title_m = re.search(r'<p\s+class="tcam">(.*?)</p>', body, re.I | re.S)
            image_m = re.search(r'<img[^>]+src="([^"]*live(\d+)\.jpg[^"]*)"', body, re.I)
            if not title_m or not image_m:
                continue
            desc_m = re.search(r'<p\s+class="subt">(.*?)</p>', body, re.I | re.S)
            city = _sky_place_part(parts[-2])
            region = _sky_place_part(parts[-3])
            country = _sky_place_part(parts[2])
            url = urllib.parse.urljoin(SKY_BASE, path)
            found[url] = {
                "id": "sky" + image_m.group(2), "src": "skyline",
                "title": _sky_text(title_m.group(1)),
                "place": ", ".join(x for x in (city, country) if x),
                "query": ", ".join(x for x in (city, region, country) if x),
                "url": url, "img": urllib.parse.urljoin(SKY_BASE, image_m.group(1)),
                "desc": _sky_text(desc_m.group(1)) if desc_m else ""
            }
        time.sleep(0.2)
    return list(found.values())

def skyline_stream(page_url):
    if not page_url.startswith(SKY_BASE + "en/webcam/") or not page_url.endswith(".html"):
        return None
    page = http_get(page_url, timeout=25)
    match = re.search(r"source\s*:\s*['\"]([^'\"]+)", page)
    if not match:
        return None
    source = match.group(1).replace("livee.", "live.")
    return urllib.parse.urljoin("https://hd-auth.skylinewebcams.com/", source)

def skyline_proxy_allowed(url):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "hd-auth.skylinewebcams.com" or
        re.fullmatch(r"hddn\d+\.skylinewebcams\.com", host) is not None)

def skyline_loop():
    while True:
        try:
            cached = _load(SKY_CACHE_FILE, [])
            cached_by_url = {c.get("url"): c for c in cached if c.get("url")}
            catalogue = skyline_catalog()
            out = []
            pending = []
            for cam in catalogue:
                old = cached_by_url.get(cam["url"])
                if old and old.get("lat") is not None and old.get("lng") is not None:
                    cam["lat"], cam["lng"] = old["lat"], old["lng"]
                    out.append(cam)
                else:
                    pending.append(cam)
            with LOCK:
                SKY["cams"] = list(out)
            for index, cam in enumerate(pending, 1):
                location = geocode(cam["query"])
                if not location:
                    location = geocode(cam["place"])
                if location:
                    cam["lat"], cam["lng"] = location
                    out.append(cam)
                if index % 20 == 0:
                    with LOCK:
                        SKY["cams"] = list(out)
                    _save(SKY_CACHE_FILE, out)
            with LOCK:
                SKY["cams"] = out; SKY["updated"] = int(time.time()); SKY["error"] = None
            _save(SKY_CACHE_FILE, out)
            print("[Skyline] %d cameras" % len(out))
        except Exception as e:
            with LOCK:
                SKY["error"] = str(e)
            print("[Skyline] erreur:", e)
        time.sleep(21600)


# ---------------- WebCamTaxi (lecteurs video integres) ----------------
def webcam_taxi_catalog():
    map_page = http_get(TAXI_MAP, timeout=70)
    map_match = re.search(
        r'var promise=({"type":"FeatureCollection".*?});\s*;\s*var count=',
        map_page, re.S)
    if not map_match:
        raise RuntimeError("carte WebCamTaxi introuvable")
    geojson = json.loads(map_match.group(1))
    located = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [])
        path = props.get("url")
        if path and len(coords) >= 2:
            located[path] = (float(coords[1]), float(coords[0]))

    all_page = http_get(TAXI_ALL, timeout=70)
    cards = re.findall(r'<div class="nspArt[^>]*>(.*?)</div>', all_page, re.I | re.S)
    found = {}
    for body in cards:
        match = re.search(
            r'<h4[^>]*>\s*<a href=([^\s>]+)[^>]*title="([^"]+)"',
            body, re.I | re.S)
        if not match:
            continue
        path = match.group(1).strip("\"'")
        if not path.startswith("/en/") or not path.endswith(".html"):
            continue
        geos = [_sky_text(x) for x in re.findall(
            r'<a class=geo_link href=[^>]+>(.*?)</a>', body, re.I | re.S)]
        image_match = re.search(r'data-src=([^\s>]+)', body, re.I)
        place = ", ".join(reversed(geos[:2]))
        cam = {
            "id": path, "src": "taxi", "title": _sky_text(match.group(2)),
            "place": place, "query": ", ".join([_sky_text(match.group(2))] + geos[:2]),
            "url": urllib.parse.urljoin(TAXI_BASE, path),
            "img": urllib.parse.urljoin(TAXI_BASE, image_match.group(1).strip("\"'")) if image_match else ""
        }
        if path in located:
            cam["lat"], cam["lng"] = located[path]
        elif path in TAXI_FALLBACKS:
            cam["lat"], cam["lng"] = TAXI_FALLBACKS[path]
        found[path] = cam
    return list(found.values())

def webcam_taxi_embed(page_url):
    if not page_url.startswith(TAXI_BASE + "en/") or not page_url.endswith(".html"):
        return None
    page = http_get(page_url, timeout=35)
    if re.search(r'<div class=offlineCam>', page, re.I):
        return None
    for tag in re.findall(r'<iframe\b[^>]*>', page, re.I):
        match = re.search(r'\bsrc=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))', tag, re.I)
        if not match:
            continue
        source = html_lib.unescape(next(x for x in match.groups() if x)).strip()
        if any(blocked in source.lower() for blocked in (
                "google.com/maps", "doubleclick.net", "googlesyndication.com")):
            continue
        source = urllib.parse.urljoin(page_url, source)
        if urllib.parse.urlparse(source).scheme in ("http", "https"):
            return source
    return None

def webcam_taxi_loop():
    while True:
        try:
            cached = _load(TAXI_CACHE_FILE, [])
            cached_by_url = {cam.get("url"): cam for cam in cached if cam.get("url")}
            cams = webcam_taxi_catalog()
            out = []
            pending = []
            for cam in cams:
                if cam.get("lat") is not None and cam.get("lng") is not None:
                    out.append(cam)
                    continue
                old = cached_by_url.get(cam["url"])
                if old and old.get("lat") is not None and old.get("lng") is not None:
                    cam["lat"], cam["lng"] = old["lat"], old["lng"]
                    out.append(cam)
                else:
                    pending.append(cam)
            with LOCK:
                TAXI["cams"] = list(out)
            _save(TAXI_CACHE_FILE, out)
            for index, cam in enumerate(pending, 1):
                location = geocode(cam["place"])
                if not location:
                    location = geocode(cam["query"])
                if location:
                    cam["lat"], cam["lng"] = location
                    out.append(cam)
                if index % 20 == 0:
                    with LOCK:
                        TAXI["cams"] = list(out)
                    _save(TAXI_CACHE_FILE, out)
            with LOCK:
                TAXI["cams"] = out; TAXI["updated"] = int(time.time()); TAXI["error"] = None
            _save(TAXI_CACHE_FILE, out)
            print("[WebCamTaxi] %d cameras" % len(out))
        except Exception as e:
            with LOCK:
                TAXI["error"] = str(e)
            print("[WebCamTaxi] erreur:", e)
        time.sleep(21600)


# ---------------- WebcamHopper (catalogue mondial) ----------------
def webcam_hopper_index(url):
    page = http_get(url, timeout=45)
    section = re.search(r'<ul class="country-wrap">(.*?)</ul>', page, re.I | re.S)
    if not section:
        raise RuntimeError("index WebcamHopper introuvable")
    rows = []
    pattern = re.compile(
        r'<li><a[^>]+href="([^"]+)"[^>]*>(.*?)'
        r'<span class="pais-cnt">(\d+)</span>', re.I | re.S)
    for href, name, count in pattern.findall(section.group(1)):
        rows.append((urllib.parse.urljoin(url, href), _sky_text(name), int(count)))
    return rows

def webcam_hopper_page(row):
    url, region, expected, country = row
    page = http_get(url, timeout=45)
    start = page.find("<h1")
    if start >= 0:
        page = page[start:]
    cams, seen = [], set()
    for body in re.split(r'<div class="rank-section">', page, flags=re.I)[1:]:
        image = re.search(r'<img[^>]+src="([^"]*/thumb/(\d+)\.jpg)"', body, re.I)
        title = re.search(
            r'<div class="rank-word"><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            body, re.I | re.S)
        if not image or not title:
            continue
        cam_id = image.group(2)
        if cam_id in seen:
            continue
        seen.add(cam_id)
        name = _sky_text(title.group(2))
        location = name.split(" - ", 1)[0].strip()
        place = region if region == country else region + ", " + country
        cams.append({
            "id": cam_id, "src": "hopper", "title": name, "place": place,
            "query": location + ", " + place,
            "url": urllib.parse.urljoin(url, html_lib.unescape(title.group(1)).strip()),
            "img": urllib.parse.urljoin(url, image.group(1))
        })
        if len(cams) >= expected:
            break
    if len(cams) != expected:
        raise RuntimeError("%s: %d/%d cameras" % (region, len(cams), expected))
    return cams

def webcam_hopper_catalog():
    countries = webcam_hopper_index(HOPPER_COUNTRIES)
    jobs = []
    for url, country, count in countries:
        if country == "USA":
            jobs.extend((u, region, n, country) for u, region, n in
                        webcam_hopper_index(HOPPER_BASE + "usa/states.html"))
        elif country == "Japan":
            jobs.extend((u, region, n, country) for u, region, n in
                        webcam_hopper_index(HOPPER_BASE + "japan/prefectures.html"))
        elif url.startswith(HOPPER_BASE):
            jobs.append((url, country, count, country))
    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for cams in pool.map(webcam_hopper_page, jobs):
            for cam in cams:
                found[cam["id"]] = cam
    found["iss"] = {
        "id": "iss", "src": "hopper", "title": "International Space Station",
        "place": "Orbite terrestre", "query": "International Space Station",
        "url": "https://eol.jsc.nasa.gov/ESRS/HDEV/", "img": "",
        "lat": 0.0, "lng": 0.0
    }
    return list(found.values())

def _webcam_hopper_youtube(source):
    parsed = urllib.parse.urlparse(source)
    host = (parsed.hostname or "").lower()
    if host not in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"):
        return None
    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif parsed.path.startswith("/embed/"):
        video_id = parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
    else:
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
    if not video_id or not re.fullmatch(r"[\w-]{11}", video_id):
        page = http_get(source, timeout=35)
        live = re.search(r'"videoId":"([\w-]{11})".{0,3000}?"isLiveNow":true', page, re.S)
        canonical = re.search(
            r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})',
            page, re.I)
        any_video = re.search(r'"videoId":"([\w-]{11})"', page)
        match = live or canonical or any_video
        video_id = match.group(1) if match else None
    if not video_id:
        return None
    return ("https://www.youtube.com/embed/%s?autoplay=1&mute=1&controls=0&"
            "modestbranding=1&rel=0&iv_load_policy=3&fs=0&disablekb=1&playsinline=1") % video_id

def page_video_source(page_url):
    try:
        page = http_get(page_url, timeout=35)
    except Exception:
        return None
    direct = re.search(r'https?://[^"\'<>\s]+?\.(?:m3u8|mp4)(?:\?[^"\'<>\s]*)?', page, re.I)
    if direct:
        url = html_lib.unescape(direct.group(0)).replace("\\/", "/")
        path = urllib.parse.urlparse(url).path.lower()
        return {"url": url, "kind": "hls" if path.endswith(".m3u8") else "video"}
    for tag in re.findall(r'<(?:iframe|video|source)\b[^>]*>', page, re.I):
        match = re.search(r'\bsrc=(?:"([^"]+)"|\'([^\']+)\'|([^\s>]+))', tag, re.I)
        if not match:
            continue
        url = urllib.parse.urljoin(page_url, html_lib.unescape(next(x for x in match.groups() if x)).strip())
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            continue
        path = parsed.path.lower()
        if path.endswith(".m3u8"):
            return {"url": url, "kind": "hls"}
        if path.endswith(".mp4"):
            return {"url": url, "kind": "video"}
        youtube = _webcam_hopper_youtube(url)
        if youtube:
            return {"url": youtube, "kind": "youtube"}
    return None

def webcam_hopper_stream(page_url, cam_id):
    with LOCK:
        cam = next((c for c in HOPPER["cams"]
                    if str(c.get("id")) == str(cam_id) and c.get("url") == page_url), None)
    if not cam:
        return None
    source = page_url
    parsed = urllib.parse.urlparse(page_url)
    if parsed.hostname == "www.webcamhopper.com" and parsed.path.startswith("/map/"):
        clean_url = urllib.parse.urldefrag(page_url)[0]
        page = http_get(clean_url, timeout=35)
        marker = re.search(
            r'<div class="camcnt" id=["\']?' + re.escape(str(cam_id)) + r'["\']?[^>]*>',
            page, re.I)
        section = page[marker.start():] if marker else page
        if marker:
            following = re.search(r'<div class="camcnt" id=', section[marker.end() - marker.start():], re.I)
            if following:
                section = section[:marker.end() - marker.start() + following.start()]
        watch = re.search(
            r'<div class="map-data-watch"><a href="([^"]+)"', section, re.I | re.S)
        if not watch:
            return None
        source = urllib.parse.urljoin(clean_url, html_lib.unescape(watch.group(1)).strip())
    if source.startswith(SKY_BASE + "en/webcam/") and source.endswith(".html"):
        stream = skyline_stream(source)
        if stream:
            return {
                "url": "/api/skyline-proxy?url=" + urllib.parse.quote(stream, safe=""),
                "kind": "hls"
            }
    if source.startswith(TAXI_BASE + "en/") and source.endswith(".html"):
        source = webcam_taxi_embed(source) or source
    youtube = _webcam_hopper_youtube(source)
    if youtube:
        return {"url": youtube, "kind": "youtube"}
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme not in ("http", "https"):
        return None
    path = parsed.path.lower()
    if path.endswith(".html") or path.endswith("/"):
        direct = page_video_source(source)
        if direct:
            return direct
    kind = "hls" if path.endswith(".m3u8") else "video" if path.endswith(".mp4") else "iframe"
    return {"url": source, "kind": kind}

def webcam_hopper_loop():
    while True:
        try:
            cached = _load(HOPPER_CACHE_FILE, [])
            cached_by_id = {str(cam.get("id")): cam for cam in cached}
            catalogue = webcam_hopper_catalog()
            out = []
            for cam in catalogue:
                old = cached_by_id.get(str(cam["id"]))
                if old and old.get("lat") is not None and old.get("lng") is not None:
                    cam["lat"], cam["lng"] = old["lat"], old["lng"]
                elif cam.get("lat") is None or cam.get("lng") is None:
                    location = geocode(cam["query"])
                    if location:
                        cam["lat"], cam["lng"] = location
                if cam.get("lat") is not None and cam.get("lng") is not None:
                    out.append(cam)
            with LOCK:
                HOPPER["cams"] = out
                HOPPER["updated"] = int(time.time())
                HOPPER["error"] = None
            _save(HOPPER_CACHE_FILE, out)
            print("[WebcamHopper] %d cameras" % len(out))
        except Exception as e:
            with LOCK:
                HOPPER["error"] = str(e)
            print("[WebcamHopper] erreur:", e)
        time.sleep(21600)


# ---------------- TfL JamCams (Londres, video MP4) ----------------
def tfl_loop():
    while True:
        try:
            arr = json.loads(http_get(TFL_URL, timeout=30))
            out = []
            for c in arr:
                if not c.get("lat") or not c.get("lon"):
                    continue
                p = {}
                for a in c.get("additionalProperties", []):
                    p[a.get("key")] = a.get("value")
                vid = p.get("videoUrl")
                if not vid:
                    continue
                out.append({"id": c.get("id"), "src": "video",
                            "title": (c.get("commonName") or "TfL JamCam").strip(),
                            "place": "Londres (TfL)", "lat": c["lat"], "lng": c["lon"],
                            "url": vid, "img": p.get("imageUrl")})
            with LOCK:
                TFL["cams"] = out; TFL["updated"] = int(time.time())
            print("[TfL] %d cameras trafic Londres" % len(out))
        except Exception as e:
            with LOCK:
                TFL["error"] = str(e)
            print("[TfL] erreur:", e)
        time.sleep(600)


# ---------------- Fintraffic Digitraffic (Finlande, images HD) ----------------
def fin_loop():
    while True:
        try:
            j = json.loads(http_get(FIN_URL, timeout=30))
            out = []
            for f in j.get("features", []):
                g = f.get("geometry", {}).get("coordinates")
                pr = f.get("properties", {})
                presets = [p for p in pr.get("presets", []) if p.get("inCollection") is not False]
                if not g or not presets:
                    continue
                pid = presets[0].get("id")
                nm = (pr.get("name") or f.get("id") or "Station").replace("_", " ")
                out.append({"id": f.get("id"), "src": "img", "title": nm,
                            "place": "Finlande", "lat": g[1], "lng": g[0],
                            "url": "https://weathercam.digitraffic.fi/%s.jpg" % pid})
            with LOCK:
                FIN["cams"] = out; FIN["updated"] = int(time.time())
            print("[Finlande] %d cameras route" % len(out))
        except Exception as e:
            with LOCK:
                FIN["error"] = str(e)
            print("[Finlande] erreur:", e)
        time.sleep(600)


# ---------------- EarthCam USA (YouTube live, lecteur sans marque) ----------------
def _yt_extract(html):
    i = html.find("var ytInitialData = ")
    if i < 0:
        return None
    start = html.find("{", i)
    depth = 0; ins = False; esc = False
    for j in range(start, len(html)):
        ch = html[j]
        if ins:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': ins = False
        else:
            if ch == '"': ins = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html[start:j + 1]
    return None

def _yt_walk(o, out):
    if isinstance(o, dict):
        lm = o.get("lockupViewModel")
        if isinstance(lm, dict) and lm.get("contentId"):
            title = ""
            try:
                title = lm["metadata"]["lockupMetadataViewModel"]["title"]["content"]
            except Exception:
                pass
            blob = json.dumps(lm, separators=(",", ":"))
            live = ("THUMBNAIL_OVERLAY_BADGE_STYLE_LIVE" in blob) or ('"imageName":"LIVE"' in blob)
            if title:
                out.append({"id": lm["contentId"], "title": title, "live": live})
        for v in o.values():
            _yt_walk(v, out)
    elif isinstance(o, list):
        for v in o:
            _yt_walk(v, out)

def _earth_place(title):
    t = re.sub(r"^\s*EarthCam Live\s*:?\s*", "", title, flags=re.I).strip()
    paren = re.findall(r"\(([^)]+)\)", t)
    cand = paren[-1].strip() if paren else t
    cand = re.sub(r"\([^)]*\)", "", cand).strip()
    if not paren and " - " in cand:
        cand = cand.split(" - ")[-1].strip()
    cand = GENERIC.sub("", cand).strip(" -,")
    return re.sub(r"\s{2,}", " ", cand) or t

def earth_loop():
    while True:
        try:
            data = json.loads(_yt_extract(http_get(EARTH_URL)) or "{}")
            items = []; _yt_walk(data, items)
            seen = set(); out = []
            for it in items:
                if not it["live"] or it["id"] in seen:
                    continue
                seen.add(it["id"])
                place = _earth_place(it["title"])
                tl = it["title"].lower()
                la = lo = None; disp = place
                for name, (a, b, d) in LANDMARKS.items():
                    if name in tl:
                        la, lo, disp = a, b, d; break
                if la is None:
                    g = geocode(place)
                    if g:
                        la, lo = g
                if la is None:
                    continue
                out.append({"id": it["id"], "src": "youtube", "title": _earth_place(it["title"]),
                            "place": disp, "lat": la, "lng": lo})
            with LOCK:
                EARTH["cams"] = out; EARTH["updated"] = int(time.time())
            print("[EarthCam] %d cameras USA" % len(out))
        except Exception as e:
            with LOCK:
                EARTH["error"] = str(e)
            print("[EarthCam] erreur:", e)
        time.sleep(150)


# ---------------- Avions temps reel (OpenSky + Airplanes.live) ----------------
class PlaneHTTPError(Exception):
    def __init__(self, provider, code, retry_after=0):
        super().__init__("%s HTTP %s" % (provider, code))
        self.provider = provider
        self.code = code
        self.retry_after = retry_after


def planes_http_json(url, provider, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": "LivePublicCamMap/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            retry = int(float(e.headers.get("X-Rate-Limit-Retry-After-Seconds") or
                              e.headers.get("Retry-After") or 0))
        except Exception:
            retry = 0
        raise PlaneHTTPError(provider, e.code, retry)


def planes_from_opensky():
    j = planes_http_json("https://opensky-network.org/api/states/all", "OpenSky", timeout=35)
    out = []
    now = time.time()
    for s in (j.get("states") or []):
        if len(s) < 11 or s[8]:
            continue
        la, lo = s[6], s[5]
        if la is None or lo is None:
            continue
        age = max(0.0, min(60.0, now - float(s[3] or s[4] or now)))
        altitude_m = s[7] if s[7] is not None else (s[13] if len(s) > 13 else None)
        altitude_ft = round(float(altitude_m) * 3.28084) if altitude_m is not None else None
        vertical_fpm = round(float(s[11] or 0) * 196.8504) if len(s) > 11 else 0
        out.append([s[0], round(float(la), 6), round(float(lo), 6),
                    round(float(s[10] or 0), 1), round(float(s[9] or 0), 1),
                    (s[1] or "").strip(), round(age, 2), 0.0,
                    "", "", "", altitude_ft, (s[14] or "") if len(s) > 14 else "",
                    vertical_fpm, "", str(s[17]) if len(s) > 17 and s[17] is not None else "",
                    (s[2] or "").strip()])
    return out


def planes_from_airplanes_live(lat, lng, radius):
    radius = max(20.0, min(250.0, float(radius)))
    url = "https://api.airplanes.live/v2/point/%.4f/%.4f/%d" % (lat, lng, int(radius))
    j = planes_http_json(url, "Airplanes.live", timeout=35)
    out = []
    for a in (j.get("ac") or []):
        la, lo = a.get("lat"), a.get("lon")
        if la is None or lo is None or str(a.get("alt_baro", "")).lower() == "ground":
            continue
        try:
            heading = float(a.get("track") or a.get("true_heading") or 0)
            velocity = float(a.get("gs") or 0) * 0.514444  # noeuds -> metres/seconde
            age = max(0.0, min(60.0, float(a.get("seen_pos") or a.get("seen") or 0)))
            turn_rate = float(a.get("track_rate") or 0)
            altitude = a.get("alt_baro") if isinstance(a.get("alt_baro"), (int, float)) else a.get("alt_geom")
            vertical_rate = a.get("baro_rate") if a.get("baro_rate") is not None else a.get("geom_rate")
            out.append([str(a.get("hex") or "").strip(), round(float(la), 6), round(float(lo), 6),
                        round(heading, 2), round(velocity, 2), (a.get("flight") or "").strip(),
                        round(age, 2), round(turn_rate, 3), (a.get("r") or "").strip(),
                        (a.get("t") or "").strip(), (a.get("desc") or "").strip(),
                        round(float(altitude)) if altitude is not None else None,
                        str(a.get("squawk") or ""), round(float(vertical_rate or 0)),
                        str(a.get("emergency") or ""), str(a.get("category") or ""), ""])
        except (TypeError, ValueError):
            continue
    return out


def take_airplanes_live_credit():
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with LOCK:
        if PLANES_USAGE.get("day") != day:
            PLANES_USAGE.update({"day": day, "airplanes_live": 0})
        if int(PLANES_USAGE.get("airplanes_live", 0)) >= 480:
            return False
        PLANES_USAGE["airplanes_live"] = int(PLANES_USAGE.get("airplanes_live", 0)) + 1
        snapshot = dict(PLANES_USAGE)
    _save(PLANES_USAGE_FILE, snapshot)
    return True


def publish_planes(out, source, center, retry_at=0):
    now = int(time.time())
    snapshot = {"list": out, "updated": now, "error": None, "source": source,
                "retry_at": int(retry_at or 0), "center": [round(center[0], 6), round(center[1], 6)]}
    with LOCK:
        PLANES.update(snapshot)
    _save(PLANES_CACHE_FILE, snapshot)
    print("[Avions/%s] %d en vol" % (source, len(out)))


def planes_loop():
    # OpenSky anonyme: une vue mondiale coute 4 credits. 15 minutes evite
    # d'epuiser les 400 credits quotidiens; le 429 impose son propre delai.
    next_opensky = 0
    next_local = 0
    opensky_retry_at = 0
    last_local = 0
    last_view_version = -1
    while True:
        now = time.time()
        if now >= next_opensky:
            try:
                out = planes_from_opensky()
                publish_planes(out, "OpenSky", (0.0, 0.0), 0)
                opensky_retry_at = 0
                next_opensky = now + 900
            except PlaneHTTPError as e:
                delay = max(900, e.retry_after or 900)
                opensky_retry_at = int(now + delay)
                next_opensky = now + delay
                with LOCK:
                    PLANES["error"] = str(e)
                    PLANES["retry_at"] = opensky_retry_at
                print("[Avions/OpenSky] limite, nouvel essai dans %ds" % delay)
            except Exception as e:
                next_opensky = now + 900
                with LOCK:
                    PLANES["error"] = "OpenSky: " + str(e)
                print("[Avions/OpenSky] erreur:", e)

        with LOCK:
            view = dict(PLANES_VIEW)
        active = float(view.get("active_until", 0)) >= now
        view_changed = int(view.get("version", 0)) != last_view_version and now - last_local >= 10
        if active and (now >= next_local or view_changed):
            last_view_version = int(view.get("version", 0))
            last_local = now
            if not take_airplanes_live_credit():
                next_local = now + 3600
                with LOCK:
                    PLANES["error"] = "Quota Airplanes.live du jour atteint"
                time.sleep(2)
                continue
            try:
                out = planes_from_airplanes_live(view["lat"], view["lng"], view["radius"])
                publish_planes(out, "Airplanes.live", (view["lat"], view["lng"]), opensky_retry_at)
                next_local = now + 30  # haute precision seulement tant que la carte est visible
            except PlaneHTTPError as e:
                next_local = now + max(60, e.retry_after or 900)
                with LOCK:
                    PLANES["error"] = str(e)
                print("[Avions/Airplanes.live] limite:", e)
            except Exception as e:
                next_local = now + 60
                with LOCK:
                    PLANES["error"] = "Airplanes.live: " + str(e)
                print("[Avions/Airplanes.live] erreur:", e)
        time.sleep(2)


# ---------------- Evenements (NASA EONET meteo + GDELT infos) ----------------
# Foyers de conflit -> geoloc fine (coord ville/region). L'API geo de GDELT
# etant hors service (404), on localise l'evenement a la ville citee dans le titre,
# sinon on retombe sur le centre du pays.
HOTSPOTS = {
    # Ukraine / Russie
    "kyiv": (50.4501, 30.5234, "Kyiv, Ukraine"), "kiev": (50.4501, 30.5234, "Kyiv, Ukraine"),
    "kharkiv": (49.9935, 36.2304, "Kharkiv, Ukraine"), "kherson": (46.6354, 32.6169, "Kherson, Ukraine"),
    "zaporizhzhia": (47.8388, 35.1396, "Zaporizhzhia, Ukraine"), "mariupol": (47.0951, 37.5413, "Marioupol, Ukraine"),
    "bakhmut": (48.5941, 38.0021, "Bakhmout, Ukraine"), "pokrovsk": (48.2814, 37.1761, "Pokrovsk, Ukraine"),
    "avdiivka": (48.1394, 37.7492, "Avdiivka, Ukraine"), "donetsk": (48.0159, 37.8028, "Donetsk"),
    "luhansk": (48.5740, 39.3078, "Louhansk"), "odesa": (46.4825, 30.7233, "Odessa, Ukraine"),
    "odessa": (46.4825, 30.7233, "Odessa, Ukraine"), "dnipro": (48.4647, 35.0462, "Dnipro, Ukraine"),
    "sumy": (50.9077, 34.7981, "Soumy, Ukraine"), "belgorod": (50.5977, 36.5858, "Belgorod, Russie"),
    "kursk": (51.7304, 36.1926, "Koursk, Russie"), "crimea": (45.0, 34.0, "Crimee"),
    "moscow": (55.7558, 37.6173, "Moscou, Russie"),
    # Proche/Moyen-Orient
    "gaza": (31.5, 34.45, "Gaza"), "rafah": (31.2968, 34.2436, "Rafah, Gaza"),
    "khan younis": (31.3444, 34.3060, "Khan Younes, Gaza"), "khan yunis": (31.3444, 34.3060, "Khan Younes, Gaza"),
    "west bank": (31.95, 35.23, "Cisjordanie"), "jenin": (32.4597, 35.2956, "Jenine, Cisjordanie"),
    "beirut": (33.8938, 35.5018, "Beyrouth, Liban"), "tel aviv": (32.0853, 34.7818, "Tel Aviv"),
    "jerusalem": (31.7683, 35.2137, "Jerusalem"), "damascus": (33.5138, 36.2765, "Damas, Syrie"),
    "aleppo": (36.2021, 37.1343, "Alep, Syrie"), "homs": (34.7324, 36.7137, "Homs, Syrie"),
    "idlib": (35.9306, 36.6339, "Idlib, Syrie"), "baghdad": (33.3152, 44.3661, "Bagdad, Irak"),
    "tehran": (35.6892, 51.3890, "Teheran, Iran"), "isfahan": (32.6539, 51.6660, "Ispahan, Iran"),
    "sanaa": (15.3694, 44.1910, "Sanaa, Yemen"), "hodeidah": (14.7978, 42.9545, "Hodeida, Yemen"),
    "red sea": (18.0, 40.0, "Mer Rouge"),
    # Afrique
    "khartoum": (15.5007, 32.5599, "Khartoum, Soudan"), "omdurman": (15.6445, 32.4777, "Omdourman, Soudan"),
    "el fasher": (13.6279, 25.3494, "El Fasher, Soudan"), "port sudan": (19.6158, 37.2164, "Port-Soudan"),
    "goma": (-1.6792, 29.2228, "Goma, RDC"), "mogadishu": (2.0469, 45.3182, "Mogadiscio, Somalie"),
    "tripoli": (32.8872, 13.1913, "Tripoli, Libye"), "bamako": (12.6392, -8.0029, "Bamako, Mali"),
    # Asie
    "kabul": (34.5553, 69.2075, "Kaboul, Afghanistan"), "taipei": (25.0330, 121.5654, "Taipei, Taiwan"),
    "taiwan strait": (24.5, 119.5, "Detroit de Taiwan"), "pyongyang": (39.0392, 125.7625, "Pyongyang"),
    "south china sea": (12.0, 115.0, "Mer de Chine meridionale"), "east china sea": (29.0, 125.0, "Mer de Chine orientale"),
    "yellow sea": (36.0, 124.0, "Mer Jaune"), "persian gulf": (26.5, 52.0, "Golfe Persique"),
    "strait of hormuz": (26.6, 56.25, "Detroit d'Ormuz"), "red sea": (18.0, 40.0, "Mer Rouge"),
    "malacca strait": (3.0, 101.0, "Detroit de Malacca"), "spratly islands": (10.0, 114.0, "Iles Spratleys"),
    "senkaku": (25.75, 123.48, "Iles Senkaku/Diaoyu"), "diaoyu": (25.75, 123.48, "Iles Senkaku/Diaoyu"),
    "hong kong": (22.3193, 114.1694, "Hong Kong"), "beijing": (39.9042, 116.4074, "Pekin, Chine"),
    "shanghai": (31.2304, 121.4737, "Shanghai, Chine"), "seoul": (37.5665, 126.9780, "Seoul, Coree du Sud"),
    "tokyo": (35.6762, 139.6503, "Tokyo, Japon"), "bangkok": (13.7563, 100.5018, "Bangkok, Thailande"),
    "jakarta": (-6.2088, 106.8456, "Jakarta, Indonesie"), "manila": (14.5995, 120.9842, "Manille, Philippines"),
    "hanoi": (21.0278, 105.8342, "Hanoi, Vietnam"), "new delhi": (28.6139, 77.2090, "New Delhi, Inde"),
    "islamabad": (33.6844, 73.0479, "Islamabad, Pakistan"), "riyadh": (24.7136, 46.6753, "Riyad, Arabie saoudite"),
    "dubai": (25.2048, 55.2708, "Dubai, EAU"), "doha": (25.2854, 51.5310, "Doha, Qatar"),
    "ankara": (39.9334, 32.8597, "Ankara, Turquie"), "istanbul": (41.0082, 28.9784, "Istanbul, Turquie"),
    "brasilia": (-15.7939, -47.8828, "Brasilia, Bresil"), "sao paulo": (-23.5558, -46.6396, "Sao Paulo, Bresil"),
    "rio de janeiro": (-22.9068, -43.1729, "Rio de Janeiro, Bresil"), "bogota": (4.7110, -74.0721, "Bogota, Colombie"),
    "lima": (-12.0464, -77.0428, "Lima, Perou"), "santiago": (-33.4489, -70.6693, "Santiago, Chili"),
}
# noms longs d'abord (match plus specifique)
_HS_ORDER = sorted(HOTSPOTS.keys(), key=len, reverse=True)

def find_hotspot(title):
    tl = (title or "").lower()
    for name in _HS_ORDER:
        if re.search(r"\b" + re.escape(name) + r"\b", tl):
            return name
    return None

NEWS_SOURCE_COUNTRIES = {
    # Asie / Moyen-Orient / Russie
    "afghanistan", "armenia", "azerbaijan", "bahrain", "bangladesh", "bhutan", "brunei", "cambodia",
    "china", "cyprus", "georgia", "india", "indonesia", "iran", "iraq", "israel", "japan", "jordan",
    "kazakhstan", "kuwait", "kyrgyzstan", "laos", "lebanon", "malaysia", "maldives", "mongolia",
    "myanmar", "nepal", "north korea", "oman", "pakistan", "palestine", "philippines", "qatar",
    "russia", "saudi arabia", "singapore", "south korea", "sri lanka", "syria", "taiwan", "tajikistan",
    "thailand", "timor-leste", "turkey", "turkmenistan", "united arab emirates", "uzbekistan",
    "vietnam", "yemen",
    # Amerique du Sud, sans Argentine ni Venezuela
    "bolivia", "brazil", "chile", "colombia", "ecuador", "guyana", "paraguay", "peru", "suriname", "uruguay",
}
NEWS_COUNTRY_ALIASES = {
    "russian federation": "russia", "iran, islamic republic of": "iran", "iran (islamic republic of)": "iran",
    "korea, republic of": "south korea", "republic of korea": "south korea", "korea, south": "south korea",
    "korea, democratic people's republic of": "north korea", "democratic people's republic of korea": "north korea",
    "viet nam": "vietnam", "lao people's democratic republic": "laos", "brunei darussalam": "brunei",
    "myanmar (burma)": "myanmar", "palestinian territory": "palestine", "state of palestine": "palestine",
    "turkiye": "turkey", "u.a.e.": "united arab emirates", "uae": "united arab emirates",
    "bolivia, plurinational state of": "bolivia",
}
NEWS_BLOCKED_SOURCE_COUNTRIES = {"argentina", "venezuela", "united states", "united kingdom", "canada", "australia", "new zealand"}
NEWS_QUERIES = [
    ("monde", '(election OR government OR diplomacy OR summit OR sanctions OR trade OR economy OR inflation OR protest OR strike OR corruption OR climate)'),
    ("securite", '(airstrike OR "military strike" OR missile OR shelling OR troops OR offensive OR clashes OR war OR conflict OR border)'),
    ("crise", '(earthquake OR flood OR cyclone OR wildfire OR drought OR evacuation OR refugees OR outbreak OR emergency)'),
]
LOCATION_COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan",
    "Bahrain", "Bangladesh", "Belarus", "Belgium", "Bolivia", "Brazil", "Cambodia", "Canada", "Chile",
    "China", "Colombia", "Cuba", "Ecuador", "Egypt", "Ethiopia", "France", "Georgia", "Germany", "Ghana",
    "Greece", "Guyana", "Haiti", "India", "Indonesia", "Iran", "Iraq", "Israel", "Japan", "Jordan",
    "Kazakhstan", "Kenya", "Kuwait", "Laos", "Lebanon", "Libya", "Malaysia", "Mali", "Mexico", "Moldova",
    "Mongolia", "Morocco", "Myanmar", "Nepal", "Niger", "Nigeria", "North Korea", "Oman", "Pakistan",
    "Palestine", "Paraguay", "Peru", "Philippines", "Poland", "Qatar", "Romania", "Russia", "Saudi Arabia",
    "Serbia", "Singapore", "Somalia", "South Africa", "South Korea", "Sri Lanka", "Sudan", "Suriname",
    "Syria", "Taiwan", "Thailand", "Turkey", "Ukraine", "United Arab Emirates", "United Kingdom",
    "United States", "Uruguay", "Uzbekistan", "Venezuela", "Vietnam", "Yemen",
]
_LOC_COUNTRY_ORDER = sorted(LOCATION_COUNTRIES, key=len, reverse=True)
PLACE_STOPWORDS = {
    "A", "An", "And", "As", "At", "By", "For", "From", "In", "Into", "Is", "Its", "New", "No", "Not",
    "Of", "On", "Or", "Over", "The", "To", "US", "UN", "EU", "NATO", "ASEAN", "BRICS", "G7", "G20",
    "President", "Minister", "Police", "Court", "Army", "Government", "Parliament", "Market", "Markets",
}

def normalize_country_name(country):
    c = re.sub(r"\s+", " ", (country or "").strip().lower())
    return NEWS_COUNTRY_ALIASES.get(c, c)

def allowed_news_source(country):
    c = normalize_country_name(country)
    return bool(c and c not in NEWS_BLOCKED_SOURCE_COUNTRIES and c in NEWS_SOURCE_COUNTRIES)

def gdelt_json(url):
    raw = http_get(url, timeout=25)
    raw = re.sub(r"[\x00-\x1f]", " ", raw)
    try:
        return json.loads(raw)
    except Exception:
        return json.loads(raw.replace("\\", "\\\\"))

def location_candidates(title):
    title = html_lib.unescape(title or "")
    hs = find_hotspot(title)
    if hs:
        yield HOTSPOTS[hs][2]
    tl = title.lower()
    for country in _LOC_COUNTRY_ORDER:
        if re.search(r"\b" + re.escape(country.lower()) + r"\b", tl):
            yield country
    for match in re.finditer(r"\b(?:in|near|at|around|across|from|over|outside|inside|towards?|after|hits?|strikes?)\s+([A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){0,3})", title):
        cand = re.sub(r"['’]s$", "", match.group(1).strip(" ,.:;()[]{}"))
        parts = [p for p in cand.split() if p not in PLACE_STOPWORDS]
        if parts:
            yield " ".join(parts)

def article_location(article):
    seen = set()
    for cand in location_candidates(article.get("title", "")):
        key = cand.lower()
        if key in seen:
            continue
        seen.add(key)
        hs = find_hotspot(cand)
        if hs:
            lat, lng, disp = HOTSPOTS[hs]
            return lat, lng, disp
        loc = geocode(cand)
        if loc:
            return loc[0], loc[1], cand
    return None

# ---------------- Store d'evenements : persistance 24h, dedup, survit au 429 et au redemarrage ----------------
EONET_URL = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=2&limit=80"
GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP"
USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
ESTORE_FILE = "events.json"
KEYS = _load("keys.json", {}) or {}          # {"firms":"...","acled_key":"...","acled_email":"..."}
ESTORE = {}                                   # id -> evenement (avec _first/_seen/_tag)
EVENT_TTL = 86400                             # un evenement reste 24h apres sa 1re detection

def _ev_id(tag, ev):
    if ev.get("id") not in (None, ""):
        return tag + ":" + str(ev["id"])
    base = "%s|%.3f|%.3f|%s" % (tag, float(ev.get("lat") or 0), float(ev.get("lng") or 0), (ev.get("title") or "")[:48])
    return tag + ":" + str(abs(hash(base)))

def _estore_publish():                        # l'appelant detient LOCK
    lst = sorted(ESTORE.values(), key=lambda e: e.get("_seen", 0), reverse=True)
    EVENTS["list"] = lst
    EVENTS["updated"] = int(time.time())

def store_merge(tag, items, ttl=EVENT_TTL):
    """Fusionne les items d'une source dans le store, sans effacer les autres sources.
    Un 429/echec = on ne rappelle pas cette fonction pour la source -> ses points restent."""
    now = int(time.time())
    with LOCK:
        for ev in items:
            ev = dict(ev); ev["_tag"] = tag
            eid = _ev_id(tag, ev); ev["_id"] = eid
            old = ESTORE.get(eid)
            ev["_first"] = int(old.get("_first", now)) if old else now
            ev["_seen"] = now
            ESTORE[eid] = ev
        for k in [k for k, v in ESTORE.items() if now - int(v.get("_first", now) or now) > ttl]:
            del ESTORE[k]
        _estore_publish()
        snapshot = list(ESTORE.values())
    _save(ESTORE_FILE, snapshot)

def estore_boot():
    now = int(time.time())
    data = _load(ESTORE_FILE, [])
    if isinstance(data, list):
        with LOCK:
            for ev in data:
                if not isinstance(ev, dict):
                    continue
                if now - int(ev.get("_first", now) or now) > EVENT_TTL:
                    continue
                eid = ev.get("_id") or _ev_id(ev.get("_tag", "x"), ev)
                ev["_id"] = eid; ESTORE[eid] = ev
            _estore_publish()


def events_loop():
    while True:
        # --- Meteo / catastrophes naturelles (NASA EONET) ---
        try:
            met = []
            j = json.loads(http_get(EONET_URL, timeout=25))
            for e in j.get("events", []):
                geoms = e.get("geometry") or []
                if not geoms:
                    continue
                g = geoms[-1]
                c = g.get("coordinates")
                if not c or not isinstance(c[0], (int, float)):
                    continue  # ignorer les polygones
                cat = ((e.get("categories") or [{}])[0]).get("title", "Nature")
                src = ((e.get("sources") or [{}])[0]).get("url", e.get("link", ""))
                met.append({"id": "eonet:" + str(e.get("id", "")), "cat": "meteo",
                            "type": cat, "title": e.get("title", cat),
                            "lat": c[1], "lng": c[0], "date": g.get("date", ""),
                            "url": src, "img": "", "desc": e.get("description") or cat,
                            "articles": []})
            store_merge("eonet", met)
        except Exception as ex:
            print("[Events/EONET]", ex)
        # --- Actualite mondiale + securite (GDELT, sources non-occidentales demandees) ---
        try:
            articles = []
            seen_urls = set()
            fetched = 0
            kept_sources = 0
            for idx, (topic, query) in enumerate(NEWS_QUERIES):
                time.sleep(5 if idx == 0 else 8)  # limite GDELT
                q = urllib.parse.quote(query)
                gurl = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + q +
                        "&mode=artlist&format=json&maxrecords=250&timespan=24h&sort=hybridrel")
                d = gdelt_json(gurl)
                fetched += len(d.get("articles", []))
                for a in d.get("articles", []):
                    url = a.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    if not allowed_news_source(a.get("sourcecountry", "")):
                        continue
                    kept_sources += 1
                    a["_topic"] = topic
                    articles.append(a)
            groups = {}
            located = 0
            for a in articles:
                loc = article_location(a)
                if not loc:
                    continue
                located += 1
                key = "loc:%0.2f:%0.2f:%s" % (loc[0], loc[1], loc[2].lower())
                grp = groups.setdefault(key, {"loc": loc, "arts": []})
                grp["arts"].append(a)
            news = []
            for key, grp in groups.items():
                lat, lng, disp = grp["loc"]
                arts = grp["arts"]
                top = arts[:6]
                img = next((x.get("socialimage") for x in top if x.get("socialimage")), "")
                source_summary = ", ".join(sorted({(x.get("sourcecountry") or "").strip() for x in top if x.get("sourcecountry")})[:3])
                main_topic = top[0].get("_topic", "monde")
                cat = "militaire" if main_topic == "securite" else "info"
                news.append({"id": key, "cat": cat, "type": "Actualite mondiale",
                            "title": disp + " - " + str(len(arts)) + " articles",
                            "lat": lat, "lng": lng, "date": top[0].get("seendate", ""),
                            "url": top[0].get("url", ""), "img": img,
                            "desc": (("Sources: " + source_summary + ". ") if source_summary else "") +
                                    " | ".join(x.get("title", "") for x in top[:3]),
                            "articles": [{"t": x.get("title", ""), "u": x.get("url", ""),
                                          "img": x.get("socialimage", "")} for x in top]})
            store_merge("gdelt", news)
            EVENTS["gerr"] = "ok:%d recus, %d sources gardees, %d geolocalises, %d groupes" % (
                fetched, kept_sources, located, len(groups))
        except Exception as ex:
            import traceback
            EVENTS["gerr"] = repr(ex) + " | " + traceback.format_exc()[-300:]
            print("[Events/GDELT-news]", ex)
        with LOCK:
            total = len(EVENTS["list"])
        print("[Events] store=%d evenements actifs" % total)
        time.sleep(1800)


# ---------------- GDACS (catastrophes) + USGS (seismes) — sans cle ----------------
GDACS_TYPE = {"EQ": ("seisme", "Seisme"), "TC": ("catastrophe", "Cyclone tropical"),
              "FL": ("catastrophe", "Inondation"), "DR": ("catastrophe", "Secheresse"),
              "VO": ("catastrophe", "Volcan"), "WF": ("catastrophe", "Feu de foret"),
              "TS": ("catastrophe", "Tsunami")}

def gdacs_loop():
    while True:
        try:
            j = json.loads(http_get(GDACS_URL, timeout=30))
            items = []
            for f in j.get("features", []):
                p = f.get("properties", {}) or {}
                g = f.get("geometry", {}) or {}
                c = g.get("coordinates")
                if not c or len(c) < 2:
                    continue
                al = (p.get("alertlevel") or "").lower()
                if al not in ("orange", "red"):
                    continue  # on ignore les 'green' (bruit de fond)
                et = p.get("eventtype", "")
                cat, label = GDACS_TYPE.get(et, ("catastrophe", et or "Catastrophe"))
                url = ""
                u = p.get("url")
                if isinstance(u, dict):
                    url = u.get("report", "") or u.get("details", "")
                desc = _sky_text(p.get("htmldescription", "")) or (p.get("name") or label)
                items.append({"id": "gdacs:" + str(p.get("eventid") or (str(c[0]) + str(c[1]))),
                              "cat": cat, "type": label + " (" + al.upper() + ")",
                              "title": p.get("name") or label,
                              "lat": c[1], "lng": c[0], "date": p.get("fromdate", ""),
                              "url": url, "img": "", "desc": desc, "articles": []})
            store_merge("gdacs", items)
            print("[GDACS] %d alertes orange/rouge" % len(items))
        except Exception as ex:
            print("[GDACS]", ex)
        time.sleep(900)

def quake_loop():
    while True:
        try:
            j = json.loads(http_get(USGS_URL, timeout=30))
            items = []
            for f in j.get("features", []):
                p = f.get("properties", {}) or {}
                g = f.get("geometry", {}) or {}
                c = g.get("coordinates")
                if not c or len(c) < 2:
                    continue
                mag = p.get("mag")
                if mag is None or mag < 4.5:
                    continue
                t = p.get("time")
                date = ""
                if t:
                    date = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t / 1000.0))
                items.append({"id": "usgs:" + str(f.get("id", "")), "cat": "seisme",
                              "type": "Seisme M%.1f" % mag,
                              "title": "M%.1f - %s" % (mag, p.get("place", "")),
                              "lat": c[1], "lng": c[0], "date": date, "url": p.get("url", ""),
                              "img": "", "desc": "Seisme de magnitude %.1f. %s" % (mag, p.get("place", "")),
                              "articles": []})
            store_merge("usgs", items)
            print("[USGS] %d seismes M>=4.5" % len(items))
        except Exception as ex:
            print("[USGS]", ex)
        time.sleep(600)


# ---------------- NASA FIRMS (feux/frappes) + ACLED (conflits) — cle requise ----------------
# Theatres de conflit surveilles (bbox: ouest, sud, est, nord). FIRMS mondial = trop volumineux.
FIRMS_THEATERS = {
    "Ukraine": (22, 44, 42, 53), "Proche-Orient": (33, 29, 43, 38),
    "Soudan": (22, 8, 39, 22), "Yemen": (42, 12, 54, 19),
    "Sahel": (-12, 10, 20, 25), "Myanmar": (92, 9, 102, 28), "RDC-est": (26, -5, 32, 3),
}

def firms_loop():
    key = KEYS.get("firms")
    if not key:
        print("[FIRMS] pas de cle (keys.json) -> couche inactive")
        return
    while True:
        try:
            items = []
            for name, (w, s, e, n) in FIRMS_THEATERS.items():
                url = ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/%s/VIIRS_SNPP_NRT/%s,%s,%s,%s/1"
                       % (key, w, s, e, n))
                txt = http_get(url, timeout=40)
                clusters = {}
                for r in csv.DictReader(io.StringIO(txt)):
                    conf = (r.get("confidence") or "").lower()
                    if conf in ("l", "low"):
                        continue
                    try:
                        la = float(r["latitude"]); lo = float(r["longitude"]); frp = float(r.get("frp") or 0)
                    except Exception:
                        continue
                    ck = (round(la, 1), round(lo, 1))
                    cl = clusters.setdefault(ck, {"la": 0.0, "lo": 0.0, "frp": 0.0, "n": 0, "date": r.get("acq_date", "")})
                    cl["la"] += la; cl["lo"] += lo; cl["frp"] += frp; cl["n"] += 1
                for (rla, rlo), cl in clusters.items():
                    if cl["frp"] < 15:
                        continue  # ignorer les petits foyers
                    items.append({"id": "firms:%.1f:%.1f" % (rla, rlo), "cat": "feu",
                                  "type": "Anomalie thermique (VIIRS)",
                                  "title": "%s - %d foyers thermiques" % (name, cl["n"]),
                                  "lat": cl["la"] / cl["n"], "lng": cl["lo"] / cl["n"], "date": cl["date"],
                                  "url": "", "img": "",
                                  "desc": ("Detection satellite NASA FIRMS (VIIRS) : %d points chauds cumules, "
                                           "puissance radiative ~%d MW. Proxy possible de frappes ou d'incendies."
                                           % (cl["n"], int(cl["frp"]))), "articles": []})
                time.sleep(1)
            store_merge("firms", items)
            print("[FIRMS] %d clusters de foyers" % len(items))
        except Exception as ex:
            print("[FIRMS]", ex)
        time.sleep(1800)

def acled_loop():
    key = KEYS.get("acled_key"); email = KEYS.get("acled_email")
    if not (key and email):
        print("[ACLED] pas de cle/email (keys.json) -> couche inactive")
        return
    while True:
        try:
            import datetime
            since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            url = ("https://api.acleddata.com/acled/read?key=" + urllib.parse.quote(key) +
                   "&email=" + urllib.parse.quote(email) +
                   "&event_date=" + since + "&event_date_where=%3E%3D&limit=400"
                   "&fields=event_date|latitude|longitude|event_type|sub_event_type|notes|country|location|fatalities|source|event_id_cnty")
            d = json.loads(http_get(url, timeout=45))
            items = []
            for a in d.get("data", []):
                try:
                    la = float(a["latitude"]); lo = float(a["longitude"])
                except Exception:
                    continue
                fat = str(a.get("fatalities", "0") or "0")
                place = a.get("location") or a.get("country", "")
                sub = a.get("sub_event_type") or a.get("event_type", "")
                items.append({"id": "acled:" + str(a.get("event_id_cnty") or (a.get("event_date", "") + place)),
                              "cat": "conflit", "type": a.get("event_type", "Conflit"),
                              "title": (place + " - " + sub).strip(" -"),
                              "lat": la, "lng": lo, "date": a.get("event_date", ""),
                              "url": "", "img": "",
                              "desc": (a.get("notes") or sub) + ((" (%s morts)" % fat) if fat not in ("", "0") else ""),
                              "articles": []})
            store_merge("acled", items)
            print("[ACLED] %d evenements de conflit" % len(items))
        except Exception as ex:
            print("[ACLED]", ex)
        time.sleep(3600)


# ---------------- AIS : trafic maritime mondial temps reel (AISStream, cle + websocket-client) ----------------
def ais_loop():
    key = KEYS.get("aisstream")
    if not key:
        print("[AIS] pas de cle (keys.json 'aisstream') -> couche inactive")
        return
    try:
        import websocket  # websocket-client
    except Exception:
        print("[AIS] librairie 'websocket-client' absente -> lance install_ais.bat, couche inactive")
        return
    sub = json.dumps({"APIKey": key,
                      "BoundingBoxes": [[[-90, -180], [90, 180]]],
                      "FilterMessageTypes": ["PositionReport", "ShipStaticData"]})

    def on_open(ws):
        ws.send(sub)
        print("[AIS] connecte a AISStream")

    def on_message(ws, message):
        try:
            m = json.loads(message)
            mt = m.get("MessageType")
            meta = m.get("MetaData", {}) or {}
            mmsi = meta.get("MMSI") or meta.get("MMSI_String")
            if mmsi is None:
                return
            mmsi = str(mmsi)
            if mt == "PositionReport":
                pr = (m.get("Message", {}) or {}).get("PositionReport", {}) or {}
                la = pr.get("Latitude"); lo = pr.get("Longitude")
                if la is None or lo is None:
                    return
                cog = pr.get("Cog") or 0.0
                sog = pr.get("Sog") or 0.0
                with LOCK:
                    old = AIS_DB.get(mmsi)
                    name = (old[4] if old else "") or (meta.get("ShipName") or "").strip()
                    typ = old[5] if old else 0
                    AIS_DB[mmsi] = [round(la, 5), round(lo, 5), round(float(cog), 1),
                                    round(float(sog), 1), name, typ, time.time()]
                    AIS["updated"] = int(time.time())
            elif mt == "ShipStaticData":
                sd = (m.get("Message", {}) or {}).get("ShipStaticData", {}) or {}
                with LOCK:
                    old = AIS_DB.get(mmsi)
                    if old:
                        old[4] = ((meta.get("ShipName") or sd.get("Name") or old[4]) or "").strip()
                        old[5] = sd.get("Type", old[5]) or old[5]
        except Exception:
            pass

    while True:
        try:
            ws = websocket.WebSocketApp("wss://stream.aisstream.io/v0/stream",
                                        on_open=on_open, on_message=on_message)
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except Exception as ex:
            AIS["error"] = str(ex)
            print("[AIS] deconnecte:", ex)
        time.sleep(5)  # reconnexion


# ---------------- AIS Digitraffic (Baltique) : navires SANS cle ----------------
def ais_digitraffic_loop():
    meta = {}          # mmsi -> (name, shipType)
    last_meta = 0.0
    while True:
        try:
            if time.time() - last_meta > 3600:
                try:
                    vj = json.loads(http_get("https://meri.digitraffic.fi/api/ais/v1/vessels", timeout=30))
                    for v in vj:
                        meta[v.get("mmsi")] = ((v.get("name") or "").strip(), v.get("shipType") or 0)
                    last_meta = time.time()
                except Exception as em:
                    print("[AIS-DT meta]", em)
            j = json.loads(http_get("https://meri.digitraffic.fi/api/ais/v1/locations", timeout=30))
            now = time.time(); n = 0
            with LOCK:
                for f in j.get("features", []):
                    c = (f.get("geometry", {}) or {}).get("coordinates")
                    p = f.get("properties", {}) or {}
                    mmsi = f.get("mmsi") or p.get("mmsi")
                    if not c or mmsi is None:
                        continue
                    nm, ty = meta.get(mmsi, ("", 0))
                    AIS_DB[str(mmsi)] = [round(c[1], 5), round(c[0], 5),
                                         round(float(p.get("cog") or 0), 1), round(float(p.get("sog") or 0), 1),
                                         nm, ty, now]
                    n += 1
                AIS["updated"] = int(now)
            print("[AIS-Digitraffic] %d navires (Baltique)" % n)
        except Exception as e:
            print("[AIS-Digitraffic]", e)
        time.sleep(20)


# ---------------- Affinage de position : geocoder le titre (lieu precis) plutot que la ville ----------------
def refine_positions_loop():
    time.sleep(150)   # laisser les catalogues se charger d'abord
    sources = ((SKY, SKY_CACHE_FILE), (TAXI, TAXI_CACHE_FILE), (HOPPER, HOPPER_CACHE_FILE))
    while True:
        moved = checked = 0
        for state, cache_file in sources:
            with LOCK:
                cams = list(state["cams"])   # memes objets dict -> maj en place
            dirty = False
            for cam in cams:
                if cam.get("fine") or cam.get("lat") is None:
                    continue
                title = re.sub(r"\([^)]*\)", "", cam.get("title") or "").replace(" - ", ", ")
                title = GENERIC.sub("", title).strip(" -,")
                cam["fine"] = 1
                checked += 1
                if len(title) < 5:
                    continue
                g = geocode(title + ", " + (cam.get("place") or ""))
                # garde-fou : on n'accepte que si le lieu reste proche de la ville d'origine (~40 km)
                if g and abs(g[0] - cam["lat"]) < 0.4 and abs(g[1] - cam["lng"]) < 0.4 and \
                        (abs(g[0] - cam["lat"]) > 1e-4 or abs(g[1] - cam["lng"]) > 1e-4):
                    with LOCK:
                        cam["lat"], cam["lng"] = g[0], g[1]
                    moved += 1
                dirty = True
                if checked >= 180:   # limite par cycle (respect Nominatim)
                    break
            if dirty:
                with LOCK:
                    state["updated"] = int(time.time())
                _save(cache_file, cams)
            if checked >= 180:
                break
        if moved or checked:
            print("[Precision] %d titres testes, %d cameras repositionnees" % (checked, moved))
        time.sleep(60 if checked else 1800)


# ---------------- Cables sous-marins ----------------
def cables_load():
    while True:
        try:
            gj = http_get(CABLES_URL, timeout=40)
            json.loads(gj)
            with LOCK:
                CABLES["geojson"] = gj
            print("[Cables] charge")
            return
        except Exception as e:
            print("[Cables] erreur:", e)
            time.sleep(60)


# ---------------- NYSDOT (511NY) : cameras trafic New York en LIVE VIDEO HLS (cle gratuite) ----------------
def nydot_loop():
    key = KEYS.get("ny511")
    if not key:
        print("[NYSDOT] pas de cle (keys.json 'ny511') -> couche inactive")
        return
    cached = _load(NYDOT_CACHE_FILE, [])
    if cached:
        with LOCK:
            NYDOT["cams"] = cached; NYDOT["updated"] = int(time.time())
        print("[NYSDOT] %d cameras (cache)" % len(cached))
    import xml.etree.ElementTree as ET
    url = "https://511ny.org/api/v2/get/cameras?format=xml&key=" + urllib.parse.quote(key)
    while True:
        try:
            root = ET.fromstring(http_get(url, timeout=45))
            out = []
            for c in root.findall("Cameras"):
                try:
                    la = float(c.findtext("Latitude")); lo = float(c.findtext("Longitude"))
                except (TypeError, ValueError):
                    continue
                video = ""
                for view in c.findall(".//View"):
                    vu = (view.findtext("VideoUrl") or "").strip()
                    if vu and vu.lower().split("?")[0].endswith(".m3u8") and view.findtext("Status") != "Disabled":
                        video = vu
                        break
                if not video:
                    continue
                out.append({"id": "ny" + str(c.findtext("Id")), "src": "nydot",
                            "title": (c.findtext("Location") or c.findtext("Roadway") or "NYSDOT cam").strip(),
                            "place": "New York (NYSDOT)", "lat": la, "lng": lo, "url": video})
            with LOCK:
                NYDOT["cams"] = out; NYDOT["updated"] = int(time.time()); NYDOT["error"] = None
            if out:
                _save(NYDOT_CACHE_FILE, out)
            print("[NYSDOT] %d cameras video live" % len(out))
        except Exception as e:
            with LOCK:
                NYDOT["error"] = str(e)
            print("[NYSDOT] erreur:", e)
        time.sleep(6 * 3600)   # liste stable -> rafraichissement toutes les 6h


# ---------------- Reconnaissance de lieu sur photo (GeoCLIP + modele vision local) ----------------
# 1) GPS EXIF s'il existe  -> position exacte
# 2) GeoCLIP (CLIP + galerie de 100 000 coordonnees) -> top-k lat/lng avec probabilite
# 3) Modele vision local (Ollama) -> indices lisibles (panneaux, plaques, vegetation...) + pays/ville
VLM_BASES = {                                 # fournisseurs compatibles OpenAI
    "sambanova": "https://api.sambanova.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
}
VLM_DEFAULT_MODEL = {"sambanova": "gemma-4-31B-it", "ollama": "qwen2.5vl:7b"}
VLM_KEY = os.environ.get("CARTE_VLM_KEY") or KEYS.get("vlm_key") or ""
VLM_PROVIDER = (os.environ.get("CARTE_VLM_PROVIDER") or KEYS.get("vlm_provider")
                or ("sambanova" if VLM_KEY else "ollama")).lower()
VLM_MODEL = (os.environ.get("CARTE_VLM_MODEL") or KEYS.get("vlm_model")
             or VLM_DEFAULT_MODEL.get(VLM_PROVIDER, "qwen2.5vl:7b"))
VLM_BASE = (os.environ.get("CARTE_VLM_URL") or KEYS.get("vlm_url")
            or VLM_BASES.get(VLM_PROVIDER, ""))
# Troisieme etage : un modele texte tranche entre les candidats a partir des indices.
try:
    import photo_osint
except Exception as _e:                       # l'app doit demarrer meme sans le module
    photo_osint = None
    print("photo_osint indisponible :", _e)
ARBITER_MODEL = os.environ.get("CARTE_ARBITER_MODEL") or KEYS.get("arbiter_model") or "gpt-oss-120b"
ARBITER_FALLBACK = KEYS.get("arbiter_fallback") or "DeepSeek-V3.2"
GEOCLIP = {"net": None, "error": None, "device": "cpu"}
GEOCLIP_LOCK = threading.Lock()
REVERSE_CACHE = {}
REVERSE_GATE = threading.Lock()
REVERSE_LAST = [0.0]


def geoclip_model():
    """Charge GeoCLIP une seule fois (GPU si dispo). Retourne None si la librairie manque."""
    with GEOCLIP_LOCK:
        if GEOCLIP["net"] is not None or GEOCLIP["error"]:
            return GEOCLIP["net"]
        try:
            import torch
            from geoclip import GeoCLIP as _GeoCLIP
            net = _GeoCLIP()
            if torch.cuda.is_available():
                net = net.to("cuda")
                GEOCLIP["device"] = "cuda"
            net.eval()
            GEOCLIP["net"] = net
        except Exception as e:
            GEOCLIP["error"] = str(e)[:300]
        return GEOCLIP["net"]


def photo_exif_gps(path):
    """Coordonnees GPS ecrites par l'appareil photo, si la photo n'a pas ete nettoyee."""
    try:
        from PIL import Image, ExifTags
        with Image.open(path) as im:
            exif = im.getexif()
            gps = exif.get_ifd(0x8825) if exif else None
        if not gps:
            return None
        def deg(v):
            d, m, s = [float(x) for x in v]
            return d + m / 60.0 + s / 3600.0
        lat = deg(gps[2]); lng = deg(gps[4])
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lng = -lng
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        return {"lat": round(lat, 6), "lng": round(lng, 6)}
    except Exception:
        return None


def reverse_place(lat, lng):
    """Nom lisible d'une coordonnee (Nominatim, 1 requete/s max, avec cache)."""
    key = "%.3f,%.3f" % (lat, lng)
    if key in REVERSE_CACHE:
        return REVERSE_CACHE[key]
    try:
        with REVERSE_GATE:
            wait = 1.1 - (time.time() - REVERSE_LAST[0])
            if wait > 0:
                time.sleep(wait)
            REVERSE_LAST[0] = time.time()
        u = ("https://nominatim.openstreetmap.org/reverse?format=json&zoom=12&accept-language=fr"
             "&lat=%.5f&lon=%.5f" % (lat, lng))
        j = json.loads(http_get(u, timeout=12))
        a = j.get("address") or {}
        city = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county") or ""
        region = a.get("state") or a.get("region") or ""
        country = a.get("country") or ""
        name = ", ".join([x for x in (city, region, country) if x]) or (j.get("display_name") or "")
    except Exception:
        name = ""
    REVERSE_CACHE[key] = name
    return name


def geoclip_refine(net, path, coords, span=0.25, step=0.01):
    """Second passage : la galerie GeoCLIP n'a que 100 000 points (~40 km d'ecart).
    L'encodeur de position etant continu, on rescore une grille fine autour de chaque
    candidat pour gagner en resolution sans changer de modele."""
    import torch
    from PIL import Image
    device = GEOCLIP["device"]
    with torch.no_grad():
        img = net.image_encoder.preprocess_image(Image.open(path)).to(device)
        out = []
        for lat, lng in coords:
            lat_span = span
            lng_span = span / max(0.25, math_cos_deg(lat))     # grille ~carree au sol
            lats = torch.arange(lat - lat_span, lat + lat_span + 1e-9, step)
            lngs = torch.arange(lng - lng_span, lng + lng_span + 1e-9, step / max(0.25, math_cos_deg(lat)))
            grid = torch.cartesian_prod(lats, lngs).to(device)
            logits = net.forward(img, grid)[0]
            best = int(torch.argmax(logits).item())
            out.append((float(grid[best][0].item()), float(grid[best][1].item())))
        return out


def math_cos_deg(deg):
    import math
    return abs(math.cos(math.radians(deg)))


# Mesure du 7 aout 2026 sur 8 cameras Fintraffic : la grille dense ne gagne rien
# (erreur moyenne 1208 -> 1200 km, mediane inchangee). La resolution de la galerie
# n'etait pas le facteur limitant : c'est le pouvoir discriminant du modele. Off par defaut.
GEOCLIP_REFINE = str(os.environ.get("CARTE_GEOCLIP_REFINE", "")).lower() in ("1", "true", "oui")


def photo_geoclip(path, top_k=5, refine=GEOCLIP_REFINE):
    """Top-k coordonnees predites par GeoCLIP, de la plus probable a la moins probable."""
    net = geoclip_model()
    if net is None:
        return []
    coords, probs = net.predict(path, top_k)
    coarse = [(float(a), float(b)) for a, b in coords.tolist()]
    fine = coarse
    if refine:
        try:
            fine = geoclip_refine(net, path, coarse)
        except Exception:
            fine = coarse
    out = []
    for (lat, lng), (clat, clng), p in zip(fine, coarse, probs.tolist()):
        item = {"lat": round(lat, 5), "lng": round(lng, 5), "score": round(float(p), 5)}
        if (lat, lng) != (clat, clng):
            item["coarse"] = [round(clat, 5), round(clng, 5)]
            item["shift_km"] = round(haversine_km(clat, clng, lat, lng), 1)
        out.append(item)
    return out


def blob_is_png(b64):
    return b64[:8] == "iVBORw0K"


def vlm_post(url, body, timeout, retries=1):
    """POST vers un fournisseur OpenAI-compatible, avec une reprise sur quota (429)."""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": "Bearer " + VLM_KEY})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                try:
                    wait = float(e.headers.get("Retry-After") or 6)
                except (TypeError, ValueError):
                    wait = 6.0
                time.sleep(min(20.0, max(2.0, wait)))
                continue
            if e.code == 429:
                raise RuntimeError("quota %s atteint (429) : reessaie dans une minute" % VLM_PROVIDER)
            if e.code in (401, 403):
                raise RuntimeError("cle API %s refusee (%d)" % (VLM_PROVIDER, e.code))
            raise


def photo_vlm(b64, hints):
    """Indices visuels + pays/ville devines par le modele vision local (Ollama)."""
    hint_txt = ""
    if hints:
        hint_txt = ("\nUn modele geographique propose ces zones (a confirmer ou infirmer, "
                    "ne les reprends pas aveuglement) : " +
                    " ; ".join("%s (%.4f, %.4f)" % (h.get("place") or "?", h["lat"], h["lng"]) for h in hints[:3]))
    prompt = (
        "Tu es un analyste en geolocalisation d'images. Observe uniquement ce qui est visible : "
        "langue et alphabet des panneaux, format des plaques d'immatriculation, cote de circulation, "
        "style architectural, materiaux, vegetation, relief, meteo, poteaux et cables, marquage au sol, "
        "bornes, enseignes, type de vehicules." + hint_txt +
        "\nReponds STRICTEMENT en JSON avec ces cles : "
        '{"textes_lus": ["texte exact"], "pays": "", "region": "", "ville": "", "lieu_precis": "", '
        '"indices": ["indice 1", "indice 2"], "confiance": "faible|moyenne|elevee"}. '
        "textes_lus : transcris MOT A MOT ce qui est ecrit sur les panneaux, enseignes et plaques, "
        "sans traduire ni corriger, liste vide si rien n'est lisible. "
        "Separe bien l'observation de la deduction : les indices decrivent ce que tu vois, pas tes "
        "conclusions. Ne deduis JAMAIS un pays a partir d'un seul nom de lieu : beaucoup de toponymes "
        "sont communs a plusieurs pays voisins, et certains pays affichent une signalisation bilingue. "
        "Si les indices sont compatibles avec plusieurs pays, laisse le champ pays vide et dis-le dans "
        "les indices. Mets une chaine vide si tu ne sais pas, n'invente jamais un nom precis. "
        "Ecris les indices en francais, 6 maximum, une phrase courte chacun."
    )
    if VLM_PROVIDER == "ollama":
        body = json.dumps({
            "model": VLM_MODEL, "prompt": prompt, "images": [b64], "stream": False,
            "format": "json", "options": {"temperature": 0.1, "num_predict": 420}
        }).encode("utf-8")
        req = urllib.request.Request(LLM_URL + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        raw = str(data.get("response") or "").strip()
    else:
        # fournisseurs compatibles OpenAI (SambaNova, OpenRouter, Groq, Mistral...)
        if not VLM_BASE:
            raise RuntimeError("aucune URL pour le fournisseur %s" % VLM_PROVIDER)
        mime = "image/png" if blob_is_png(b64) else "image/jpeg"
        body = json.dumps({
            "model": VLM_MODEL, "temperature": 0.1,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}}]}]
        }).encode("utf-8")
        data = vlm_post(VLM_BASE + "/chat/completions", body, 120)
        raw = str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    parsed = json.loads(m.group(0)) if m else {}
    ind = parsed.get("indices")
    txt = parsed.get("textes_lus")
    return {
        "textes": [str(x)[:120] for x in (txt if isinstance(txt, list) else [])][:10],
        "pays": str(parsed.get("pays") or "")[:80],
        "region": str(parsed.get("region") or "")[:80],
        "ville": str(parsed.get("ville") or "")[:80],
        "lieu": str(parsed.get("lieu_precis") or "")[:120],
        "indices": [str(x)[:220] for x in (ind if isinstance(ind, list) else [])][:6],
        "confiance": str(parsed.get("confiance") or "")[:20],
        "model": VLM_MODEL, "provider": VLM_PROVIDER,
    }


# Mots frequents sur les panneaux qui ne sont pas des toponymes (multilingue).
TOPO_STOP = set("""tie vag vaeg vag. route rue via strasse strabe street road highway exit ausfahrt
sortie uscita salida centrum centre center zentrum airport aeroport lentoasema flughafen station
gare bahnhof parking parkering city ville stadt town nord sud est ouest north south east west
norr syd ost vast pohjoinen etela ita lansi keskusta all alle tous camion truck bus taxi
autoroute motorway ring boulevard avenue place platz plaza piazza calle strada""".split())


def toponym_leads(textes, country=""):
    """Les noms lus sur les panneaux sont la preuve la plus dure d'une photo. On les
    geocode : deux toponymes distincts qui tombent au meme endroit = position quasi certaine."""
    seen, tokens = set(), []
    for raw in (textes or [])[:8]:
        for part in re.split(r"[,;/|\n\-]+", str(raw)):
            for word in re.findall(r"[^\W\d_][\w'À-ɏ]{3,}", part, re.UNICODE):
                key = word.lower()
                if key in TOPO_STOP or key in seen:
                    continue
                seen.add(key)
                tokens.append(word)
    points = []
    for word in tokens[:6]:
        query = (word + ", " + country) if country else word
        pos = geocode(query) or (geocode(word) if country else None)
        if pos:
            points.append({"nom": word, "lat": round(pos[0], 5), "lng": round(pos[1], 5)})
    cluster = None
    for i, a in enumerate(points):                 # groupe le plus large a moins de 40 km
        members = [a] + [b for j, b in enumerate(points)
                         if j != i and haversine_km(a["lat"], a["lng"], b["lat"], b["lng"]) <= 40]
        if len(members) >= 2 and (cluster is None or len(members) > cluster["n"]):
            cluster = {"lat": round(sum(p["lat"] for p in members) / len(members), 5),
                       "lng": round(sum(p["lng"] for p in members) / len(members), 5),
                       "noms": [p["nom"] for p in members], "n": len(members)}
    return {"points": points, "cluster": cluster} if points else None


def _conf_band(value):
    """Normalise une confiance : accepte faible/moyenne/elevee ou un nombre 0-1."""
    s = str(value or "").strip().lower().replace("é", "e")
    if s.startswith("elev") or s.startswith("haut") or s.startswith("high"):
        return "elevee"
    if s.startswith("moy") or s.startswith("med"):
        return "moyenne"
    if s.startswith("faib") or s.startswith("low"):
        return "faible"
    try:
        v = float(s.replace("%", "").replace(",", "."))
        if v > 1:
            v /= 100.0
        return "elevee" if v >= 0.7 else ("moyenne" if v >= 0.4 else "faible")
    except ValueError:
        return ""


def arbiter_chat(model, question, timeout=60):
    body = json.dumps({"model": model, "temperature": 0.1, "max_tokens": 500,
                       "messages": [{"role": "user", "content": question}]}).encode("utf-8")
    data = vlm_post(VLM_BASE + "/chat/completions", body, timeout)
    return str(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()


def photo_arbitrate(vlm, candidates, leads=None, ocr=None, streetclip=None):
    """Un modele texte choisit le meilleur candidat GeoCLIP au vu des indices visuels.
    Corrige le cas ou GeoCLIP hesite entre deux pays voisins qui se ressemblent."""
    if not VLM_BASE or not VLM_KEY or len(candidates) < 2:
        return None
    indices = (vlm or {}).get("indices") or []
    guess = ", ".join([x for x in ((vlm or {}).get("ville"), (vlm or {}).get("pays")) if x])
    ocr_txt = (ocr or {}).get("textes") or []
    if not indices and not guess and not ocr_txt:
        return None
    listing = [{"rang": i + 1, "lieu": c.get("place") or ("%.4f, %.4f" % (c["lat"], c["lng"])),
                "score": c["score"]} for i, c in enumerate(candidates)]
    question = (
        "Tu arbitres une geolocalisation de photo. Tu ne vois pas l'image : tu disposes des textes lus "
        "sur place, des indices visuels releves par un modele de vision, et de zones candidates "
        "produites par un modele geographique entraine sur des millions de photos geolocalisees.\n"
        "REGLES :\n"
        "1. Le candidat de rang 1 porte la plus forte evidence visuelle globale. C'est ton choix par "
        "defaut : ne t'en ecarte que si une preuve est DECISIVE et sans ambiguite.\n"
        "2. Un seul nom de lieu lu sur un panneau n'est PAS une preuve decisive : les toponymes se "
        "ressemblent entre pays voisins, et plusieurs pays ont une signalisation bilingue. Une langue "
        "clairement identifiee sur plusieurs textes, un format de plaque ou un cote de circulation le sont.\n"
        "3. Le pays propose par le modele de vision est une hypothese faillible, pas un fait. S'il "
        "contredit le rang 1 sans preuve decisive, garde le rang 1.\n"
        "4. Si les preuves se contredisent, garde le rang 1 et mets une confiance faible.\n"
        "5. Si AUCUN candidat n'est compatible avec des preuves solides (par exemple une langue "
        "clairement lue sur les panneaux qui ne correspond a aucune zone proposee), reponds rang 0 "
        "et explique quelle region les preuves designent reellement.\n"
        "6. 'toponymes_concordants_preuve_forte' regroupe des noms lus sur des panneaux differents "
        "qui pointent tous vers la meme zone : c'est la preuve la plus forte dont tu disposes. Si "
        "elle contredit tous les candidats, reponds rang 0.\n"
        "7. 'toponymes_isoles_preuve_faible' liste des mots geocodes un par un. Beaucoup sont des "
        "lectures tronquees ou des homonymes dans un autre pays : ne t'appuie jamais dessus seuls.\n"
        "8. 'ocr_panneaux' vient d'un moteur OCR dedie, avec un score de fiabilite par mot : "
        "c'est plus sur que la lecture du modele de vision. Un mot tronque garde un score eleve, "
        "donc ne conclus jamais sur un seul mot.\n"
        "9. 'streetclip_pays' est un second modele geographique independant de celui qui a produit "
        "les candidats. Quand les deux s'accordent, la confiance monte ; quand ils divergent, "
        "baisse-la.\n"
        'Reponds STRICTEMENT en JSON : {"rang": 1, "raison": "", "confiance": "faible|moyenne|elevee"}. '
        "La raison fait deux phrases maximum, en francais.\n"
        + json.dumps({"ocr_panneaux": (ocr or {}).get("textes") or [],
                      "streetclip_pays": (streetclip or {}).get("pays") or [],
                      "textes_lus": (vlm or {}).get("textes") or [], "indices": indices,
                      "hypothese_faillible_de_la_vision": guess,
                      "toponymes_isoles_preuve_faible": (leads or {}).get("points") or [],
                      "toponymes_concordants_preuve_forte": (leads or {}).get("cluster"),
                      "candidats": listing}, ensure_ascii=False))
    raw = ""
    used = ARBITER_MODEL
    try:
        raw = arbiter_chat(ARBITER_MODEL, question)
    except Exception:
        used = ARBITER_FALLBACK
        raw = arbiter_chat(ARBITER_FALLBACK, question)
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    parsed = json.loads(m.group(0))
    try:
        rank = int(parsed.get("rang") or 0)
    except (TypeError, ValueError):
        rank = 0
    if not 0 <= rank <= len(candidates):
        return None
    return {"rang": rank, "raison": str(parsed.get("raison") or "")[:400],
            "confiance": _conf_band(parsed.get("confiance")), "model": used,
            "rejette": rank == 0}


def haversine_km(a_lat, a_lng, b_lat, b_lng):
    import math
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def cameras_near(lat, lng, km=30, limit=6):
    """Croisement avec le catalogue de l'app : une camera publique proche du lieu suppose
    permet de comparer la scene en direct. Personne d'autre ne peut faire ca."""
    out = []
    with LOCK:
        catalogues = (("USA (live)", EARTH), ("Skyline", SKY), ("WebCamTaxi", TAXI),
                      ("WebcamHopper", HOPPER), ("WhatsUpCams", WUC), ("Londres", TFL),
                      ("Finlande", FIN), ("New York", NYDOT))
        for label, state in catalogues:
            for c in list(state["cams"]):
                try:
                    d = haversine_km(lat, lng, float(c["lat"]), float(c["lng"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if d <= km:
                    out.append({"source": label, "titre": str(c.get("title") or "")[:80],
                                "lieu": str(c.get("place") or "")[:60],
                                "lat": round(float(c["lat"]), 5), "lng": round(float(c["lng"]), 5),
                                "km": round(d, 1), "src": c.get("src"), "url": c.get("url")})
    out.sort(key=lambda x: x["km"])
    return out[:limit]


# Les serveurs Overpass publics repondent en 40 a 60 s aux heures pleines : la
# verification terrain tourne en tache de fond et l'interface la recupere ensuite.
VERIFY_JOBS = {}
VERIFY_LOCK = threading.Lock()


def verify_terrain_async(token, lat, lng, noms, refs):
    try:
        out = photo_osint.overpass_verify(lat, lng, noms, refs)
    except Exception as e:
        out = {"erreur": str(e)[:200]}
    with VERIFY_LOCK:
        VERIFY_JOBS[token] = {"status": "done", "result": out, "t": time.time()}
        for old in [k for k, v in VERIFY_JOBS.items() if time.time() - v.get("t", 0) > 1800]:
            VERIFY_JOBS.pop(old, None)


def photo_verifications(result, tmp_path):
    """Etage de verification : on confronte l'hypothese au terrain, a la meteo et au soleil.
    Chaque brique peut infirmer une hypothese, ce qu'aucun modele ne sait faire seul."""
    if photo_osint is None:
        return {"erreur": "module photo_osint absent"}
    checks = {}
    vlm = result.get("vlm") or {}
    textes = vlm.get("textes") or []
    best = result.get("best")
    meta = result.get("metadata") or {}
    date = meta.get("date") or (meta.get("exif") or {}).get("date_prise_de_vue")
    jobs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        if best:
            noms = [p["nom"] for p in ((result.get("leads") or {}).get("points") or [])]
            for extra in (vlm.get("ville"), vlm.get("lieu")):
                if extra and extra not in noms:
                    noms.append(extra)
            refs = photo_osint.road_refs(textes)
            if noms or refs:
                token = "%x" % time.time_ns()
                with VERIFY_LOCK:
                    VERIFY_JOBS[token] = {"status": "pending", "t": time.time()}
                threading.Thread(target=verify_terrain_async,
                                 args=(token, best["lat"], best["lng"], noms, refs),
                                 daemon=True).start()
                result["verify_token"] = token
                checks["terrain"] = {"status": "en cours",
                                     "cherches": noms + refs}
            jobs["cameras"] = pool.submit(cameras_near, best["lat"], best["lng"])
            if date:
                jobs["meteo"] = pool.submit(photo_osint.weather_check, best["lat"], best["lng"],
                                            date, vlm.get("indices"))
        for name, fut in jobs.items():
            try:
                checks[name] = fut.result(timeout=30)
            except Exception as e:
                checks[name] = {"erreur": str(e)[:160]}
    # Appariement geometrique contre l'image live d'une camera publique proche :
    # 892 correspondances sur une meme scene, 0 entre deux lieux differents.
    cams = checks.get("cameras") or []
    if tmp_path and cams:
        for cam in cams[:2]:
            url = cam.get("url") or ""
            if not (url.startswith("https://") and url.split("?")[0].lower().endswith((".jpg", ".jpeg"))):
                continue
            ref = tmp_path + ".ref.jpg"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                           "Digitraffic-User": "LivePublicCamMap"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    with open(ref, "wb") as f:
                        f.write(r.read())
                m = photo_osint.match_images(tmp_path, ref)
                m["camera"] = cam.get("titre") or cam.get("lieu")
                m["km"] = cam.get("km")
                checks["appariement"] = m
            except Exception as e:
                checks["appariement"] = {"erreur": str(e)[:160]}
            finally:
                try:
                    os.remove(ref)
                except OSError:
                    pass
            break
    if best and date:
        indices = " ".join(vlm.get("indices") or []).lower()
        ombres = None
        if "ombre" in indices:
            ombres = "sans ombre" not in indices and "pas d'ombre" not in indices
        try:
            checks["soleil"] = photo_osint.sun_analysis(best["lat"], best["lng"], date, ombres)
        except Exception as e:
            checks["soleil"] = {"erreur": str(e)[:160]}
    return checks


def photo_best_answer(result):
    """Reponse finale unique, pour que l'interface et les mesures disent la meme chose.
    Ordre : GPS de la photo > candidat retenu par l'arbitre > lecture des panneaux."""
    exif = result.get("exif")
    if exif:
        return {"lat": exif["lat"], "lng": exif["lng"], "place": exif.get("place", ""),
                "source": "GPS EXIF", "precision": "exacte"}
    arb = result.get("arbiter") or {}
    cands = result.get("candidates") or []
    if arb.get("rang") and 1 <= arb["rang"] <= len(cands):
        c = cands[arb["rang"] - 1]
        return {"lat": c["lat"], "lng": c["lng"], "place": c.get("place", ""),
                "source": "zone GeoCLIP retenue par l'arbitre", "precision": "zone"}
    vlm = result.get("vlm") or {}
    cluster = (result.get("leads") or {}).get("cluster")
    vpos = vlm.get("lat") is not None and vlm.get("lng") is not None
    if arb.get("rejette") or not cands:
        # le geocodage de la phrase complete est plus precis qu'un barycentre de villes,
        # mais on ne le suit que si les toponymes recoupes le confirment (ou n'existent pas).
        if vpos and (not cluster or haversine_km(vlm["lat"], vlm["lng"],
                                                 cluster["lat"], cluster["lng"]) <= 25):
            return {"lat": vlm["lat"], "lng": vlm["lng"], "place": vlm.get("query", ""),
                    "source": "lecture des panneaux", "precision": "lieu nomme"}
        if cluster:
            return {"lat": cluster["lat"], "lng": cluster["lng"],
                    "place": " + ".join(cluster["noms"]),
                    "source": "toponymes concordants", "precision": "zone"}
        if vpos:
            return {"lat": vlm["lat"], "lng": vlm["lng"], "place": vlm.get("query", ""),
                    "source": "lecture des panneaux", "precision": "lieu nomme"}
    if cands:
        c = cands[0]
        return {"lat": c["lat"], "lng": c["lng"], "place": c.get("place", ""),
                "source": "meilleur score GeoCLIP", "precision": "zone"}
    return None


CASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enquetes")
CASE_LOG = os.path.join(CASE_DIR, "journal.jsonl")


def case_slug(text):
    s = re.sub(r"[^\w\s-]", "", str(text or "sans-lieu"), flags=re.UNICODE).strip().lower()
    return (re.sub(r"[\s_-]+", "-", s) or "sans-lieu")[:40]


def case_save(payload):
    """Dossier d'enquete : la photo, l'analyse complete et une ligne de journal horodatee.
    La tracabilite de la methode compte autant que le resultat."""
    raw = str(payload.get("image") or "")
    if "," in raw[:64]:
        raw = raw.split(",", 1)[1]
    result = payload.get("result") or {}
    best = result.get("best") or {}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    case_id = stamp + "-" + case_slug(best.get("place"))
    folder = os.path.join(CASE_DIR, case_id)
    os.makedirs(folder, exist_ok=True)
    if raw:
        with open(os.path.join(folder, "photo.jpg"), "wb") as f:
            f.write(base64.b64decode(re.sub(r"\s+", "", raw), validate=False))
    entry = {"id": case_id, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
             "lieu": best.get("place"), "lat": best.get("lat"), "lng": best.get("lng"),
             "source": best.get("source"), "note": str(payload.get("note") or "")[:500]}
    with open(os.path.join(folder, "analyse.json"), "w", encoding="utf-8") as f:
        json.dump({"dossier": entry, "analyse": result}, f, ensure_ascii=False, indent=1)
    os.makedirs(CASE_DIR, exist_ok=True)
    with open(CASE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    report = case_report(case_id, result, entry, raw)
    entry.update({"ok": True, "dossier_path": folder, "rapport": report})
    return entry


def _rows(pairs):
    return "".join("<tr><th>%s</th><td>%s</td></tr>" % (html_lib.escape(str(k)),
                   html_lib.escape(str(v))) for k, v in pairs if v not in (None, "", []))


def case_report(case_id, result, entry, b64=""):
    """Rapport HTML autonome : photo incluse, chaine de preuves, sources citees."""
    best = result.get("best") or {}
    vlm = result.get("vlm") or {}
    arb = result.get("arbiter") or {}
    checks = result.get("checks") or {}
    meta = result.get("metadata") or {}
    parts = ["""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Rapport %s</title><style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 20px;background:#0d1117;color:#c9d1d9;line-height:1.6}
h1{font-size:22px;border-bottom:1px solid #30363d;padding-bottom:12px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:2px;color:#8b949e;margin-top:32px}
table{border-collapse:collapse;width:100%%;margin:10px 0}th,td{border:1px solid #21262d;padding:7px 10px;text-align:left;font-size:13px;vertical-align:top}
th{color:#8b949e;font-weight:500;width:210px;font-size:11px;text-transform:uppercase;letter-spacing:1px}
img{max-width:100%%;border:1px solid #30363d;border-radius:6px}
.verdict{border:1px solid #d9a648;background:rgba(217,166,72,.08);border-radius:8px;padding:16px;margin:16px 0}
.verdict b{font-size:18px;color:#f0f6fc;display:block;margin-bottom:6px}
.ok{color:#3fb950}.ko{color:#f85149}
ul{padding-left:20px}li{margin:4px 0;font-size:13px}
footer{margin-top:40px;padding-top:14px;border-top:1px solid #21262d;color:#6e7681;font-size:11px}
code{background:#161b22;padding:2px 6px;border-radius:4px;font-size:12px;color:#d9a648}
</style></head><body>""" % html_lib.escape(case_id)]
    parts.append("<h1>Rapport de geolocalisation &mdash; %s</h1>" % html_lib.escape(case_id))
    parts.append('<div class="verdict"><b>%s</b>%s<br><small>Source : %s</small></div>' % (
        html_lib.escape(str(best.get("place") or "Lieu indetermine")),
        ("%.5f, %.5f" % (best["lat"], best["lng"])) if best.get("lat") is not None else "",
        html_lib.escape(str(best.get("source") or ""))))
    if arb.get("raison"):
        parts.append("<h2>Raisonnement</h2><p>%s</p>" % html_lib.escape(arb["raison"]))
    if b64:
        parts.append('<h2>Photo analysee</h2><img src="data:image/jpeg;base64,%s" alt="">' % b64)
    if vlm.get("textes"):
        parts.append("<h2>Textes lus sur place</h2><ul>%s</ul>" %
                     "".join("<li><code>%s</code></li>" % html_lib.escape(str(t)) for t in vlm["textes"]))
    if vlm.get("indices"):
        parts.append("<h2>Indices visuels</h2><ul>%s</ul>" %
                     "".join("<li>%s</li>" % html_lib.escape(str(x)) for x in vlm["indices"]))
    cands = result.get("candidates") or []
    if cands:
        parts.append("<h2>Zones candidates (GeoCLIP)</h2><table>" + "".join(
            "<tr><th>#%d &mdash; %.1f%%</th><td>%s<br>%.5f, %.5f</td></tr>" % (
                i + 1, c["score"] * 100, html_lib.escape(str(c.get("place") or "")), c["lat"], c["lng"])
            for i, c in enumerate(cands)) + "</table>")
    terrain = checks.get("terrain") or {}
    if terrain.get("verdict"):
        cls = "ok" if terrain.get("confirmes") else "ko"
        parts.append('<h2>Verification OpenStreetMap</h2><p class="%s">%s &mdash; %d correspondance(s)</p><ul>%s</ul>' % (
            cls, html_lib.escape(str(terrain["verdict"])), terrain.get("confirmes", 0),
            "".join("<li>%s</li>" % html_lib.escape(str(t.get("nom"))) for t in (terrain.get("trouves") or [])[:8])))
    meteo, soleil = checks.get("meteo") or {}, checks.get("soleil") or {}
    if meteo.get("resume") or soleil.get("moment"):
        parts.append("<h2>Chronolocalisation</h2><table>" + _rows([
            ("Meteo relevee", meteo.get("resume")), ("Coherence meteo", meteo.get("coherent")),
            ("Moment de la journee", soleil.get("moment")),
            ("Azimut du soleil", soleil.get("azimut")), ("Hauteur du soleil", soleil.get("hauteur")),
            ("Coherence des ombres", soleil.get("coherent"))]) + "</table>")
    if checks.get("cameras"):
        parts.append("<h2>Cameras publiques proches</h2><table>" + "".join(
            "<tr><th>%s km</th><td>%s (%s)</td></tr>" % (c["km"], html_lib.escape(str(c.get("titre") or "")),
            html_lib.escape(str(c.get("source") or ""))) for c in checks["cameras"]) + "</table>")
    parts.append("<h2>Authenticite du fichier</h2><table>" + _rows(
        list((meta.get("exif") or {}).items()) +
        [("Format", meta.get("format")), ("Taille", meta.get("taille")),
         ("Alertes", " ; ".join((meta.get("alertes") or []) +
                                ((result.get("forensics") or {}).get("alertes") or [])))]) + "</table>")
    parts.append("""<footer>Genere le %s par Carte Cameras Live.
Sources : GeoCLIP (modele), %s (lecture d'image), %s (arbitrage), Nominatim et OpenStreetMap
(geocodage et verification terrain), Open-Meteo (meteo historique).<br>
Ce rapport presente des estimations : les scores et les correspondances sont des indices,
pas des preuves. Rien dans cette analyse ne vise a identifier une personne.</footer></body></html>""" % (
        html_lib.escape(entry.get("date", "")), html_lib.escape(VLM_MODEL), html_lib.escape(ARBITER_MODEL)))
    path = os.path.join(CASE_DIR, case_id, "rapport.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return path


def case_list(limit=50):
    out = []
    try:
        with open(CASE_LOG, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out[::-1][:limit]


BATCH = {"status": "idle", "done": 0, "total": 0, "results": [], "error": None}


def batch_run(folder, options):
    exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    try:
        files = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
                 if f.lower().endswith(exts)][:40]
    except OSError as e:
        with LOCK:
            BATCH.update({"status": "error", "error": str(e)[:200]})
        return
    with LOCK:
        BATCH.update({"status": "running", "done": 0, "total": len(files), "results": [], "error": None})
    for path in files:
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            r = photo_locate({"image": b64, "vlm": options.get("vlm", True),
                              "verify": False})
            best = r.get("best") or {}
            row = {"fichier": os.path.basename(path), "lieu": best.get("place"),
                   "lat": best.get("lat"), "lng": best.get("lng"), "source": best.get("source")}
            if options.get("save"):
                try:
                    row["dossier"] = case_save({"image": b64, "result": r})["id"]
                except Exception:
                    pass
        except Exception as e:
            row = {"fichier": os.path.basename(path), "erreur": str(e)[:160]}
        with LOCK:
            BATCH["results"].append(row)
            BATCH["done"] += 1
    with LOCK:
        BATCH["status"] = "done"


CATALOGUES = (("youtube", "USA (live)", "EARTH"), ("skyline", "SkylineWebcams", "SKY"),
              ("taxi", "WebCamTaxi", "TAXI"), ("hopper", "WebcamHopper", "HOPPER"),
              ("hls", "WhatsUpCams", "WUC"), ("video", "Londres trafic", "TFL"),
              ("img", "Finlande", "FIN"), ("nydot", "New York trafic", "NYDOT"))


def _sans_accents(texte):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(texte or "").lower())
                   if unicodedata.category(c) != "Mn")


def catalogue_cameras():
    """Toutes les cameras chargees, tous catalogues confondus."""
    out = []
    with LOCK:
        for src, label, nom in CATALOGUES:
            for c in list(globals()[nom]["cams"]):
                d = dict(c)
                d.setdefault("src", src)
                d["catalogue"] = label
                out.append(d)
    return out


def _variantes_pays(terme):
    """France -> france ; Italie -> italy : les catalogues melangent le francais et l'anglais."""
    base = _sans_accents(terme)
    variantes = {base}
    try:
        table = getattr(photo_osint, "PAYS_EN", {}) or {}
        for fr, en in table.items():
            en_court = _sans_accents(en).replace("the ", "")
            if _sans_accents(fr) == base or en_court == base:
                variantes.add(_sans_accents(fr))
                variantes.add(en_court)
    except Exception:
        pass
    return {v for v in variantes if v}


def _pays_de(place):
    """Le pays est le dernier segment de 'Pays de la Loire, France'."""
    parts = [p.strip() for p in str(place or "").split(",") if p.strip()]
    return _sans_accents(parts[-1]) if parts else ""


def outil_compter_cameras(cible=None):
    cams = catalogue_cameras()
    if not cible:
        detail = {}
        for c in cams:
            detail[c.get("catalogue", "?")] = detail.get(c.get("catalogue", "?"), 0) + 1
        return {"total": len(cams), "par_catalogue": detail}
    mots = _variantes_pays(cible)

    def compte(test):
        trouves, detail, exemples = 0, {}, []
        for c in cams:
            if test(c):
                trouves += 1
                detail[c.get("catalogue", "?")] = detail.get(c.get("catalogue", "?"), 0) + 1
                if len(exemples) < 5:
                    exemples.append(str(c.get("title") or "")[:60])
        return trouves, detail, exemples

    # 1) correspondance stricte sur le pays : sinon "Italie" attrape "Little Italy, NY"
    trouves, detail, exemples = compte(lambda c: _pays_de(c.get("place")) in mots)
    mode = "pays exact"
    if not trouves:                       # 2) sinon recherche libre (region, ville, mot-cle)
        trouves, detail, exemples = compte(
            lambda c: any(mot in _sans_accents((c.get("place") or "") + " " + (c.get("title") or ""))
                          for mot in mots))
        mode = "recherche libre"
    return {"recherche": cible, "mode": mode, "total_trouve": trouves, "par_catalogue": detail,
            "exemples": exemples, "total_catalogue": len(cams)}


def outil_chercher_cameras(requete, limite=8):
    mots = _variantes_pays(requete) | {_sans_accents(requete)}
    limite = max(1, min(20, int(limite or 8)))
    res = []
    for c in catalogue_cameras():
        champ = _sans_accents((c.get("place") or "") + " " + (c.get("title") or ""))
        if any(mot in champ for mot in mots):
            res.append({"titre": str(c.get("title") or "")[:70],
                        "lieu": str(c.get("place") or "")[:50],
                        "catalogue": c.get("catalogue"), "src": c.get("src"),
                        "lat": c.get("lat"), "lng": c.get("lng")})
            if len(res) >= limite:
                break
    return {"requete": requete, "resultats": res, "nombre": len(res)}


def outil_etat_carte(vue=None):
    cams = catalogue_cameras()
    detail = {}
    for c in cams:
        detail[c.get("catalogue", "?")] = detail.get(c.get("catalogue", "?"), 0) + 1
    etat = {"cameras_total": len(cams), "par_catalogue": detail}
    with LOCK:
        etat["evenements_24h"] = len(EVENTS["list"])
    if isinstance(vue, dict) and vue.get("lat") is not None:
        etat["vue_actuelle"] = {"lat": round(float(vue.get("lat") or 0), 4),
                                "lng": round(float(vue.get("lng") or 0), 4),
                                "zoom": vue.get("zoom")}
    return etat


def executer_outil(nom, args, vue):
    """Execute un outil demande par le modele. Renvoie (resultat, action pour l'interface)."""
    if nom == "compter_cameras":
        return outil_compter_cameras(args.get("pays") or args.get("texte")), None
    if nom == "chercher_cameras":
        return outil_chercher_cameras(args.get("requete", ""), args.get("limite", 8)), None
    if nom == "etat_carte":
        return outil_etat_carte(vue), None
    if nom == "aller_a":
        pos = geocode(str(args.get("lieu") or "")[:120])
        if not pos:
            return {"trouve": False, "lieu": args.get("lieu")}, None
        return ({"trouve": True, "lieu": args.get("lieu"),
                 "lat": round(pos[0], 5), "lng": round(pos[1], 5)},
                {"type": "aller_a", "lat": pos[0], "lng": pos[1],
                 "zoom": int(args.get("zoom") or 9), "lieu": args.get("lieu")})
    if nom == "ouvrir_camera":
        titre = _sans_accents(args.get("titre", ""))
        if titre:
            for c in catalogue_cameras():
                if titre in _sans_accents(c.get("title") or ""):
                    cam = {k: c.get(k) for k in ("src", "id", "url", "title", "place", "lat", "lng")}
                    return ({"ouverte": True, "camera": cam.get("title"), "lieu": cam.get("place")},
                            {"type": "ouvrir_camera", "cam": cam})
        return {"ouverte": False, "raison": "aucune camera de ce titre dans le catalogue"}, None
    return {"erreur": "outil inconnu"}, None


CHAT_OUTILS = [
    {"type": "function", "function": {
        "name": "compter_cameras",
        "description": "Compte les cameras publiques du catalogue, au total ou pour un pays, "
                       "une region ou une ville donnee.",
        "parameters": {"type": "object", "properties": {
            "pays": {"type": "string",
                     "description": "Pays, region ou ville. Omettre pour le total general."}}}}},
    {"type": "function", "function": {
        "name": "chercher_cameras",
        "description": "Liste les cameras correspondant a un lieu ou un mot-cle, avec leurs "
                       "coordonnees. A appeler avant d'ouvrir une camera. Les libelles du "
                       "catalogue sont souvent en anglais (Venice, Munich, Athens) : si une "
                       "recherche en francais ne donne rien, reessaie en anglais.",
        "parameters": {"type": "object", "properties": {
            "requete": {"type": "string"}, "limite": {"type": "integer"}},
            "required": ["requete"]}}},
    {"type": "function", "function": {
        "name": "ouvrir_camera",
        "description": "Ouvre une camera a l'ecran et centre la carte dessus. Utiliser le titre "
                       "exact renvoye par chercher_cameras.",
        "parameters": {"type": "object", "properties": {
            "titre": {"type": "string"}}, "required": ["titre"]}}},
    {"type": "function", "function": {
        "name": "aller_a",
        "description": "Deplace la carte sur un lieu nomme (ville, pays, monument).",
        "parameters": {"type": "object", "properties": {
            "lieu": {"type": "string"}, "zoom": {"type": "integer"}}, "required": ["lieu"]}}},
    {"type": "function", "function": {
        "name": "etat_carte",
        "description": "Etat general : nombre de cameras par catalogue, evenements en cours, "
                       "position actuelle de la carte.",
        "parameters": {"type": "object", "properties": {}}}},
]

CHAT_SYSTEM = (
    "Tu es l'assistant d'une application de cartographie de cameras publiques et de "
    "geolocalisation de photos. Tu reponds en francais, brievement, sur ce que tu VOIS dans "
    "l'image fournie et sur les elements d'analyse qui t'accompagnent.\n"
    "Tu disposes d'outils pour interroger et piloter l'application : compter et chercher des "
    "cameras dans le catalogue, en ouvrir une a l'ecran, deplacer la carte. Utilise-les des "
    "que la question porte sur le contenu de la carte ou demande une action, plutot que de "
    "repondre de memoire. Pour ouvrir une camera, cherche-la d'abord puis ouvre-la avec son "
    "titre exact. Les chiffres que tu annonces doivent venir des outils, jamais d'une estimation.\n"
    "Regles :\n"
    "- Distingue toujours ce que tu lis reellement de ce que tu supposes. Si un texte est "
    "flou, partiel ou hors champ, dis-le au lieu de completer par imagination.\n"
    "- Si l'image ne permet pas de repondre, dis-le en une phrase et indique ce qui manque. "
    "Ne parle d'image que si la question portait sur le contenu visuel : pour un comptage ou "
    "une action, reponds simplement, sans commenter l'absence d'image.\n"
    "- INTERDICTION ABSOLUE : quand tu ouvres une camera avec un outil, tu ne recois AUCUNE "
    "image. Annonce uniquement le titre et le lieu de la camera ouverte. Ne decris ni la vue, "
    "ni la meteo, ni les batiments, ni les bateaux : tu ne les vois pas. Termine en proposant "
    "a l'utilisateur de te poser une question sur cette image.\n"
    "- Tu peux decrire des lieux, des enseignes, des vehicules, la meteo, l'heure apparente. "
    "Tu ne cherches jamais a identifier une personne physique, meme si on te le demande : "
    "dis simplement que tu ne fais pas ca et propose de decrire la scene autrement.\n"
    "- Pas de markdown, pas de listes a puces, trois phrases maximum sauf demande contraire."
)


def chat_context_resume(context):
    """Resume l'analyse en cours pour que le modele texte sache de quoi on parle."""
    if not isinstance(context, dict) or not context:
        return ""
    best = context.get("best") or {}
    vlm = context.get("vlm") or {}
    checks = context.get("checks") or {}
    resume = {
        "camera_ouverte": context.get("camera"),
        "reponse_actuelle": {"lieu": best.get("place"), "source": best.get("source"),
                             "lat": best.get("lat"), "lng": best.get("lng")} if best else None,
        "textes_lus": [t.get("texte") for t in ((context.get("ocr") or {}).get("textes") or [])][:10],
        "indices_visuels": (vlm.get("indices") or [])[:6],
        "zones_candidates": [{"lieu": c.get("place"), "score": c.get("score")}
                             for c in (context.get("candidates") or [])[:3]],
        "verification_terrain": (checks.get("terrain") or {}).get("verdict"),
        "meteo": (checks.get("meteo") or {}).get("resume"),
        "soleil": (checks.get("soleil") or {}).get("moment"),
    }
    resume = {k: v for k, v in resume.items() if v}
    return json.dumps(resume, ensure_ascii=False) if resume else ""


def resolve_youtube_stream(video_id):
    """URL de flux direct d'une video YouTube (yt-dlp), comme le fait detect_stream.py."""
    try:
        import yt_dlp
    except Exception:
        return None
    opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True,
            "no_warnings": True, "format": "best[height<=720]/best"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=%s" % video_id, download=False)
        if info.get("url"):
            return info["url"]
        for f in reversed(info.get("formats") or []):
            if f.get("url"):
                return f["url"]
    except Exception:
        pass
    return None


def resolve_camera_stream(src, url, cam_id=None, profondeur=0):
    """Traduit une camera du catalogue en source exploitable : (genre, url, referer).
    genre = 'image' ou 'video'. Reprend les memes resolveurs que l'ouverture d'une camera."""
    src = str(src or "").lower()
    url = str(url or "")
    low = url.split("?", 1)[0].lower()
    if profondeur > 2:
        return None, None, None
    m = re.search(r"(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/|[?&]v=)([\w-]{6,})", url)
    if m or src in ("youtube", "earthcam"):
        vid = m.group(1) if m else (cam_id or "")
        direct = resolve_youtube_stream(vid) if re.match(r"^[\w-]{6,}$", vid or "") else None
        return ("video", direct, None) if direct else (None, None, None)
    if low.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "image", url, None
    if low.endswith((".mp4", ".m3u8")):
        return "video", url, SKY_BASE if "skyline" in low else None
    if src == "hls" and cam_id and re.match(r"^[\w-]+$", cam_id):
        # WhatsUpCams repartit ses flux sur cdn-001 a cdn-010 : on cherche celui qui repond,
        # comme le fait le lecteur cote navigateur.
        for i in range(1, 11):
            essai = "https://cdn-%03d.whatsupcams.com/hls/%s.m3u8" % (i, cam_id)
            try:
                req = urllib.request.Request(essai, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=6) as r:
                    if r.status == 200 and b"#EXTM3U" in r.read(200):
                        return "video", essai, None
            except Exception:
                continue
        return None, None, None
    if src == "skyline" or SKY_BASE in url:
        flux = skyline_stream(url)
        return ("video", flux, SKY_BASE) if flux else (None, None, None)
    if src == "taxi" or TAXI_BASE in url:
        embed = webcam_taxi_embed(url)
        return resolve_camera_stream("", embed, cam_id, profondeur + 1) if embed else (None, None, None)
    if src == "hopper" or HOPPER_BASE in url:
        st = webcam_hopper_stream(url, cam_id)
        cible = (st or {}).get("url") or ""
        if cible.startswith("/api/skyline-proxy") and "url=" in cible:
            cible = urllib.parse.unquote(cible.split("url=", 1)[1])
            return "video", cible, SKY_BASE
        return resolve_camera_stream("", cible, cam_id, profondeur + 1) if cible else (None, None, None)
    return None, None, None


def frame_from_hls(url, referer=None):
    """Certains flux HLS exigent un Referer, que OpenCV ne sait pas envoyer. On telecharge
    alors le dernier segment a la main et on le decode."""
    import cv2
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    def get(u):
        with urllib.request.urlopen(urllib.request.Request(u, headers=headers), timeout=20) as r:
            return r.read()
    playlist = get(url).decode("utf-8", "replace")
    for _ in range(2):                            # playlist maitre -> variante
        lignes = [l.strip() for l in playlist.splitlines() if l.strip() and not l.startswith("#")]
        if not lignes:
            return None
        cible = urllib.parse.urljoin(url, lignes[-1])
        if cible.split("?")[0].lower().endswith(".m3u8"):
            url, playlist = cible, get(cible).decode("utf-8", "replace")
            continue
        segment = get(cible)
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_frame_tmp.ts")
        with open(chemin, "wb") as f:
            f.write(segment)
        try:
            cap = cv2.VideoCapture(chemin)
            ok, frame = cap.read()
            for _i in range(3):
                ok2, f2 = cap.read()
                if ok2:
                    ok, frame = ok2, f2
            cap.release()
            if ok and frame is not None:
                good, buf = cv2.imencode(".jpg", frame)
                if good:
                    return buf.tobytes()
        finally:
            try:
                os.remove(chemin)
            except OSError:
                pass
        return None
    return None


def camera_frame(src, url, cam_id=None):
    """Image courante d'une camera, recuperee cote serveur : le navigateur ne peut pas
    exporter un canvas alimente par une source d'un autre domaine (canvas 'tainted')."""
    try:
        genre, cible, referer = resolve_camera_stream(src, url, cam_id)
    except Exception as e:
        return None, "resolution du flux impossible (%s)" % str(e)[:80]
    if not genre or not cible:
        return None, "flux non resolu pour cette camera"
    try:
        if genre == "image":
            req = urllib.request.Request(cible, headers={
                "User-Agent": UA, "Digitraffic-User": "LivePublicCamMap",
                "Referer": referer or SKY_BASE})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read(), None
        import cv2
        cap = cv2.VideoCapture(cible)
        ok, frame = False, None
        try:
            for _ in range(5):                    # les premieres trames sont souvent noires
                ok2, f2 = cap.read()
                if ok2:
                    ok, frame = True, f2
        finally:
            cap.release()
        if ok and frame is not None:
            good, buf = cv2.imencode(".jpg", frame)
            if good:
                return buf.tobytes(), None
        blob = frame_from_hls(cible, referer)     # repli : segment HLS telecharge a la main
        return (blob, None) if blob else (None, "flux video illisible")
    except Exception as e:
        return None, str(e)[:150]


def photo_chat(payload):
    """Conversation sur ce que l'application voit : image de camera capturee a l'instant,
    ou photo analysee, ou simplement le resultat d'analyse quand il n'y a pas d'image."""
    question = str(payload.get("question") or "").strip()[:1200]
    if not question:
        raise ValueError("question vide")
    raw = str(payload.get("image") or "")
    if "," in raw[:64]:
        raw = raw.split(",", 1)[1]
    b64 = re.sub(r"\s+", "", raw)
    note_image = None
    cam = payload.get("camera") if isinstance(payload.get("camera"), dict) else None
    if not b64 and cam:
        blob, note_image = camera_frame(cam.get("src"), cam.get("url"), cam.get("id"))
        if blob:
            b64 = base64.b64encode(blob).decode()
    resume = chat_context_resume(payload.get("context"))
    history = payload.get("history") if isinstance(payload.get("history"), list) else []
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    for turn in history[-6:]:
        role = "assistant" if turn.get("role") == "assistant" else "user"
        texte = str(turn.get("text") or "")[:1500]
        if texte:
            messages.append({"role": role, "content": texte})
    entete = ("Elements d'analyse disponibles : " + resume + "\n") if resume else ""
    if b64 and VLM_PROVIDER != "ollama":
        mime = "image/png" if blob_is_png(b64) else "image/jpeg"
        messages.append({"role": "user", "content": [
            {"type": "text", "text": entete + "Question : " + question},
            {"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mime, b64)}}]})
        modele = VLM_MODEL
    else:
        messages.append({"role": "user", "content": entete + "Question : " + question +
                         ("\n(Aucune image disponible : reponds a partir des elements ci-dessus, "
                          "et dis si l'image serait necessaire.)" if not b64 else "")})
        modele = ARBITER_MODEL
    # Boucle d'agent : le modele peut appeler les outils de l'application (compter,
    # chercher, ouvrir une camera, deplacer la carte) avant de formuler sa reponse.
    vue = payload.get("vue") if isinstance(payload.get("vue"), dict) else None
    actions, outils_utilises = [], []
    texte = ""
    for tour in range(4):
        requete = {"model": modele, "temperature": 0.2, "max_tokens": 700, "messages": messages}
        if not b64:                      # le modele vision de SambaNova n'accepte pas les outils
            requete["tools"] = CHAT_OUTILS
            requete["tool_choice"] = "auto"
        data = vlm_post(VLM_BASE + "/chat/completions", json.dumps(requete).encode("utf-8"), 120)
        message = (data.get("choices") or [{}])[0].get("message") or {}
        appels = message.get("tool_calls") or []
        texte = str(message.get("content") or "").strip()
        if not appels:
            break
        messages.append({"role": "assistant", "content": message.get("content") or "",
                         "tool_calls": appels})
        for appel in appels[:4]:
            fonction = (appel.get("function") or {})
            nom = fonction.get("name") or ""
            try:
                args = json.loads(fonction.get("arguments") or "{}")
            except ValueError:
                args = {}
            try:
                resultat, action = executer_outil(nom, args if isinstance(args, dict) else {}, vue)
            except Exception as e:
                resultat, action = {"erreur": str(e)[:150]}, None
            outils_utilises.append(nom)
            if action:
                actions.append(action)
            messages.append({"role": "tool", "tool_call_id": appel.get("id") or nom,
                             "name": nom,
                             "content": json.dumps(resultat, ensure_ascii=False)[:3000]})
    texte = re.sub(r"<think>[\s\S]*?</think>", "", texte, flags=re.I).strip()
    if not texte:
        texte = "C'est fait." if actions else "Je n'ai pas de reponse a donner."
    return {"ok": True, "texte": texte[:2500], "modele": modele,
            "avec_image": bool(b64), "note_image": note_image,
            "actions": actions, "outils": outils_utilises}


PHOTO_JOBS = {}
PHOTO_JOB_LOCK = threading.Lock()


def photo_locate_job(token, payload):
    """Execute la chaine en publiant chaque etape : l'interface affiche GeoCLIP a 4 s
    au lieu d'attendre 40 s que tout soit fini."""
    def publish(partial, etape):
        with PHOTO_JOB_LOCK:
            PHOTO_JOBS[token] = {"status": "running", "etape": etape, "t": time.time(),
                                 "result": json.loads(json.dumps(partial, ensure_ascii=False))}
    try:
        result = photo_locate(payload, publish)
        state = {"status": "done", "result": result, "t": time.time()}
    except Exception as e:
        state = {"status": "error", "error": str(e)[:300], "t": time.time()}
    with PHOTO_JOB_LOCK:
        PHOTO_JOBS[token] = state
        for old in [k for k, v in PHOTO_JOBS.items() if time.time() - v.get("t", 0) > 1800]:
            PHOTO_JOBS.pop(old, None)


def photo_locate(payload, publish=None):
    """Chaine complete : EXIF -> GeoCLIP -> modele vision -> accord entre les deux."""
    raw = str(payload.get("image") or "")
    if "," in raw[:64]:
        raw = raw.split(",", 1)[1]
    b64 = re.sub(r"\s+", "", raw)
    if not b64:
        raise ValueError("aucune image recue")
    blob = base64.b64decode(b64, validate=False)
    if len(blob) > 24 * 1024 * 1024:
        raise ValueError("image trop lourde (24 Mo maximum)")
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".photo_locate_tmp")
    with open(tmp, "wb") as f:
        f.write(blob)
    try:
        result = {"ok": True, "exif": photo_exif_gps(tmp), "candidates": [],
                  "vlm": None, "engine": {"geoclip": None, "vlm": VLM_MODEL}}
        if photo_osint is not None:
            try:
                result["metadata"] = photo_osint.metadata_full(tmp)
            except Exception as e:
                result["metadata"] = {"erreur": str(e)[:200]}
            try:
                result["forensics"] = photo_osint.jpeg_forensics(tmp)
            except Exception as e:
                result["forensics"] = {"erreur": str(e)[:200]}
            # OCR de scene : lecture des panneaux, plus fiable et 6x plus rapide que
            # de laisser le modele vision dechiffrer une image redimensionnee.
            try:
                result["ocr"] = photo_osint.ocr_read(tmp)
            except Exception as e:
                result["ocr"] = {"erreur": str(e)[:200], "textes": []}
            if publish:
                publish(result, "fichier analyse")
            if payload.get("streetclip", True):
                try:
                    result["streetclip"] = photo_osint.streetclip_country(tmp)
                except Exception as e:
                    result["streetclip"] = {"erreur": str(e)[:200]}
        try:
            result["candidates"] = photo_geoclip(tmp, int(payload.get("top_k") or 5))
            result["engine"]["geoclip"] = GEOCLIP["device"] if GEOCLIP["net"] else None
        except Exception as e:
            result["geoclip_error"] = str(e)[:300]
        if GEOCLIP["error"]:
            result["geoclip_error"] = GEOCLIP["error"]
        if publish:
            publish(result, "zones candidates")
        for c in result["candidates"][:3]:
            c["place"] = reverse_place(c["lat"], c["lng"])
        if result["exif"]:
            result["exif"]["place"] = reverse_place(result["exif"]["lat"], result["exif"]["lng"])
        if publish:
            publish(result, "lieux nommes")
        if payload.get("vlm", True):
            try:
                result["vlm"] = photo_vlm(b64, result["candidates"])
            except Exception as e:
                result["vlm_error"] = str(e)[:300]
        vlm = result.get("vlm") or {}
        query = ", ".join([x for x in (vlm.get("lieu"), vlm.get("ville"), vlm.get("region"), vlm.get("pays")) if x])
        if query:
            pos = geocode(query) or geocode(", ".join([x for x in (vlm.get("ville"), vlm.get("pays")) if x]))
            if pos:
                vlm["lat"], vlm["lng"] = round(pos[0], 5), round(pos[1], 5)
                vlm["query"] = query
                for c in result["candidates"]:
                    d = haversine_km(pos[0], pos[1], c["lat"], c["lng"])
                    c["vlm_km"] = round(d, 1)
                    if d <= 150:
                        c["agree"] = True
        # Pistes toponymiques : textes de l'OCR (fiables, scores eleves) puis ceux du
        # modele vision, geocodes et recoupes entre eux.
        textes_all = [t["texte"] for t in ((result.get("ocr") or {}).get("textes") or [])
                      if t.get("score", 0) >= 0.85]
        for t in (vlm.get("textes") or []):
            if t not in textes_all:
                textes_all.append(t)
        pays_hint = vlm.get("pays") or ""
        if not pays_hint:
            sc = ((result.get("streetclip") or {}).get("pays") or [])
            if sc and sc[0].get("score", 0) >= 0.5:
                pays_hint = sc[0]["nom"]
        try:
            result["leads"] = toponym_leads(textes_all, pays_hint)
        except Exception as e:
            result["leads_error"] = str(e)[:200]
        if publish:
            publish(result, "pistes toponymiques")
        if payload.get("arbiter", True) and result["candidates"]:
            try:
                verdict = photo_arbitrate(vlm, result["candidates"], result.get("leads"),
                                          result.get("ocr"), result.get("streetclip"))
                if verdict and not verdict["rejette"]:
                    result["arbiter"] = verdict
                    result["candidates"][verdict["rang"] - 1]["chosen"] = True
                    # le lieu retenu par l'arbitre est resolu meme s'il etait hors du top 3
                    winner = result["candidates"][verdict["rang"] - 1]
                    if not winner.get("place"):
                        winner["place"] = reverse_place(winner["lat"], winner["lng"])
                elif verdict:
                    # aucune zone GeoCLIP ne tient : la lecture visuelle devient la reponse
                    result["arbiter"] = verdict
            except Exception as e:
                result["arbiter_error"] = str(e)[:300]
        result["best"] = photo_best_answer(result)
        if publish:
            publish(result, "verdict")
        if payload.get("verify", True):
            try:
                result["checks"] = photo_verifications(result, tmp)
            except Exception as e:
                result["checks"] = {"erreur": str(e)[:200]}
        return result
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ---------------- serveur ----------------
# skyvdn.com = CDN video des cameras NYSDOT (autorise pour le suivi)
ALLOWED_DETECT = ("whatsupcams.com", "tfl.gov.uk", "digitraffic.fi", "amazonaws.com", "skylinewebcams.com", "skyvdn.com")

def detect_args_from_source(source):
    """Traduit une URL resolue (YouTube / Skyline / HLS / MP4) en arguments pour
    detect_stream.py, ou None si le flux n'est pas analysable (lecteur tiers opaque)."""
    if not source:
        return None
    m = re.search(r"(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/|[?&]v=)([\w-]{6,})", source)
    if m:
        return ["youtube", m.group(1)]
    if source.startswith(SKY_BASE + "en/webcam/") and source.endswith(".html"):
        return ["skyline", source]
    low = source.split("?", 1)[0].lower()
    if source.startswith("https://") and (low.endswith(".m3u8") or low.endswith(".mp4")):
        return ["video", source]
    return None

# ---------------- mode site : ecoute reseau, jeton d'acces, routes bridees ----------------
# Par defaut rien ne change : ecoute sur 127.0.0.1, aucun jeton, toutes les routes ouvertes.
# Des que l'ecoute sort de la machine, l'authentification devient obligatoire et les routes
# qui touchent au disque ou lancent des processus sont coupees.
BIND = os.environ.get("CARTE_BIND") or KEYS.get("bind") or "127.0.0.1"
SITE_TOKEN = os.environ.get("CARTE_TOKEN") or KEYS.get("site_token") or ""
MODE_PUBLIC = BIND not in ("127.0.0.1", "localhost")
ROUTES_LOCALES = ("/detect", "/detect-stop", "/api/photo-batch")
# Trois roles possibles :
#   complet  tout sur la machine (defaut, comportement historique)
#   site     heberge sur un VPS : delegue les traitements GPU au poste de l'utilisateur
#   worker   poste de l'utilisateur : ne sert que les traitements GPU appeles par le site
ROLE = (os.environ.get("CARTE_ROLE") or KEYS.get("role") or "complet").lower()
IA_URL = (os.environ.get("CARTE_IA_URL") or KEYS.get("ia_url") or "").rstrip("/")
IA_TOKEN = os.environ.get("CARTE_IA_TOKEN") or KEYS.get("ia_token") or SITE_TOKEN
ROUTES_GPU = ("/api/geolocate", "/api/photo-anonymize")   # les seules qui exigent le GPU
# Origines autorisees quand le front est heberge ailleurs que le back (Vercel, CDN).
ORIGINES = [o.strip().rstrip("/") for o in
            (os.environ.get("CARTE_ORIGINES") or KEYS.get("origines") or "").split(",") if o.strip()]


def relais_ia(route, payload, timeout=300):
    """Le site delegue un traitement lourd au poste equipe du GPU."""
    if not IA_URL:
        raise RuntimeError("aucun poste de calcul configure (CARTE_IA_URL)")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(IA_URL + route, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "Authorization": "Bearer " + IA_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


PAGE_LOGIN = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<title>Carte Cameras Live</title><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
background:#080a0c;color:#c1c7cd;font-family:system-ui,sans-serif}
form{border:1px solid #242a31;border-radius:12px;padding:28px;background:#0a0d10;width:300px}
h1{margin:0 0 6px;font-size:13px;letter-spacing:2.5px;text-transform:uppercase;color:#e7eaed}
p{margin:0 0 18px;color:#5a626b;font-size:11px}
input{width:100%;box-sizing:border-box;padding:10px 12px;background:#080a0c;border:1px solid #242a31;
border-radius:8px;color:#c1c7cd;outline:none;font-size:13px}
input:focus{border-color:#d9a648}
button{width:100%;margin-top:12px;padding:10px;background:#d9a648;border:0;border-radius:8px;
color:#0b0d10;font-weight:600;cursor:pointer}
</style></head><body><form method="GET" action="/login">
<h1>Acces protege</h1><p>Cette instance est exposee sur le reseau.</p>
<input type="password" name="t" placeholder="Jeton d'acces" autofocus>
<button type="submit">Entrer</button></form></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _jeton_fourni(self):
        entete = self.headers.get("Authorization") or ""
        if entete.startswith("Bearer "):
            return entete[7:].strip()
        for morceau in (self.headers.get("Cookie") or "").split(";"):
            if morceau.strip().startswith("carte_token="):
                return urllib.parse.unquote(morceau.split("=", 1)[1].strip())
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("t", [""])[0]

    def _autorise(self):
        """True si la requete peut continuer. Ne bride rien en usage local."""
        if not MODE_PUBLIC:
            return True
        chemin = urllib.parse.urlparse(self.path).path
        if chemin.startswith(ROUTES_LOCALES):
            self._send_json(403, {"ok": False,
                                  "error": "route desactivee quand l'application est exposee"})
            return False
        if not SITE_TOKEN:
            self._send(503, "Aucun jeton configure : definis CARTE_TOKEN avant d'exposer l'app.",
                       "text/plain; charset=utf-8")
            return False
        if self._jeton_fourni() == SITE_TOKEN:
            return True
        if chemin == "/login":
            self._send(200, PAGE_LOGIN, "text/html; charset=utf-8")
            return False
        self.send_response(302)
        self.send_header("Location", "/login")
        self.end_headers()
        return False

    def _cors(self):
        origine = (self.headers.get("Origin") or "").rstrip("/")
        if origine and origine in ORIGINES:
            self.send_header("Access-Control-Allow-Origin", origine)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def _send(self, code, body, ctype):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_bytes(self, code, body, ctype):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, value):
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self._send(code, body, "application/json; charset=utf-8")

    def _send_state(self, state):
        # Ne pas conserver le verrou pendant la serialisation et l'envoi des
        # gros catalogues : les collecteurs restent ainsi reactifs.
        with LOCK:
            snapshot = dict(state)
            for key in ("cams", "list"):
                if key in snapshot:
                    snapshot[key] = list(snapshot[key])
        self._send_json(200, snapshot)

    def do_GET(self):
        if not self._autorise():
            return
        chemin = urllib.parse.urlparse(self.path).path
        if chemin == "/login" and self._jeton_fourni() == SITE_TOKEN and SITE_TOKEN:
            self.send_response(302)
            self.send_header("Set-Cookie",
                             "carte_token=%s; Path=/; Max-Age=2592000; SameSite=Lax; HttpOnly"
                             % urllib.parse.quote(SITE_TOKEN))
            self.send_header("Location", "/")
            self.end_headers()
            return
        if urllib.parse.urlparse(self.path).path == "/assets/plane.png":
            try:
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons8-plane-50.png")
                with open(icon_path, "rb") as icon_file:
                    self._send_bytes(200, icon_file.read(), "image/png")
            except OSError:
                self._send(404, "plane icon not found", "text/plain; charset=utf-8")
        elif self.path.startswith("/api/status"):
            with LOCK:
                sources = {
                    "youtube": {"count": len(EARTH["cams"]), "updated": EARTH["updated"]},
                    "skyline": {"count": len(SKY["cams"]), "updated": SKY["updated"]},
                    "taxi": {"count": len(TAXI["cams"]), "updated": TAXI["updated"]},
                    "hopper": {"count": len(HOPPER["cams"]), "updated": HOPPER["updated"]},
                    "nydot": {"count": len(NYDOT["cams"]), "updated": NYDOT["updated"]},
                    "hls": {"count": len(WUC["cams"]), "updated": WUC["updated"]},
                    "video": {"count": len(TFL["cams"]), "updated": TFL["updated"]},
                    "img": {"count": len(FIN["cams"]), "updated": FIN["updated"]},
                }
            self._send_json(200, {"sources": sources})
        elif self.path.startswith("/api/whatsupcams"):
            self._send_state(WUC)
        elif self.path.startswith("/api/tfl"):
            self._send_state(TFL)
        elif self.path.startswith("/api/finland"):
            self._send_state(FIN)
        elif self.path.startswith("/api/earthcam"):
            self._send_state(EARTH)
        elif self.path.startswith("/api/skyline-stream"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                page_url = p.get("url", [""])[0]
                stream = skyline_stream(page_url)
                proxy = ("/api/skyline-proxy?url=" + urllib.parse.quote(stream, safe="")) if stream else None
                self._send(200 if proxy else 404, json.dumps({"ok": bool(proxy), "url": proxy}),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "err": str(e)}), "application/json; charset=utf-8")
        elif self.path.startswith("/api/skyline-proxy"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                remote = p.get("url", [""])[0]
                if not skyline_proxy_allowed(remote):
                    self._send(403, "forbidden", "text/plain; charset=utf-8")
                    return
                req = urllib.request.Request(remote, headers={
                    "User-Agent": UA, "Accept": "*/*", "Referer": SKY_BASE})
                with urllib.request.urlopen(req, timeout=25) as response:
                    body = response.read()
                    ctype = response.headers.get("Content-Type", "application/octet-stream")
                if body.startswith(b"#EXTM3U"):
                    lines = []
                    for line in body.decode("utf-8", "replace").splitlines():
                        if line and not line.startswith("#"):
                            asset = urllib.parse.urljoin(remote, line)
                            if skyline_proxy_allowed(asset):
                                line = "/api/skyline-proxy?url=" + urllib.parse.quote(asset, safe="")
                        lines.append(line)
                    body = ("\n".join(lines) + "\n").encode("utf-8")
                    ctype = "application/vnd.apple.mpegurl"
                self._send_bytes(200, body, ctype)
            except Exception as e:
                self._send(502, str(e), "text/plain; charset=utf-8")
        elif self.path.startswith("/api/skyline"):
            self._send_state(SKY)
        elif self.path.startswith("/api/webcamtaxi-stream"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                page_url = p.get("url", [""])[0]
                embed = webcam_taxi_embed(page_url)
                self._send(200 if embed else 404, json.dumps({"ok": bool(embed), "url": embed}),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "err": str(e)}), "application/json; charset=utf-8")
        elif self.path.startswith("/api/webcamtaxi"):
            self._send_state(TAXI)
        elif self.path.startswith("/api/webcamhopper-stream"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                page_url = p.get("url", [""])[0]
                cam_id = p.get("id", [""])[0]
                stream = webcam_hopper_stream(page_url, cam_id)
                body = {"ok": bool(stream)}
                if stream:
                    body.update(stream)
                self._send(200 if stream else 404, json.dumps(body),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "err": str(e)}),
                           "application/json; charset=utf-8")
        elif self.path.startswith("/api/webcamhopper"):
            self._send_state(HOPPER)
        elif self.path.startswith("/api/nydot"):
            self._send_state(NYDOT)
        elif self.path.startswith("/api/planes"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                lat = max(-85.0, min(85.0, float(p.get("lat", [PLANES_VIEW["lat"]])[0])))
                lng = max(-180.0, min(180.0, float(p.get("lng", [PLANES_VIEW["lng"]])[0])))
                radius = max(20.0, min(250.0, float(p.get("radius", [PLANES_VIEW["radius"]])[0])))
                with LOCK:
                    moved = (abs(lat - PLANES_VIEW["lat"]) > 0.15 or
                             abs(lng - PLANES_VIEW["lng"]) > 0.15 or
                             abs(radius - PLANES_VIEW["radius"]) > 15)
                    PLANES_VIEW.update({"lat": lat, "lng": lng, "radius": radius,
                                        "active_until": time.time() + 15})
                    if moved:
                        PLANES_VIEW["version"] = int(PLANES_VIEW.get("version", 0)) + 1
            except Exception:
                pass
            self._send_state(PLANES)
        elif self.path.startswith("/api/ais"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                lat = float(p.get("lat", ["50"])[0]); lng = float(p.get("lng", ["8"])[0])
                rad = max(1.0, min(80.0, float(p.get("radius", ["25"])[0])))
                now = time.time(); out = []
                with LOCK:
                    upd = AIS["updated"]
                    for mmsi, v in AIS_DB.items():
                        if now - v[6] > 600:
                            continue
                        if abs(v[0] - lat) <= rad and abs(((v[1] - lng + 180) % 360) - 180) <= rad:
                            out.append([mmsi, v[0], v[1], v[2], v[3], v[4], v[5]])
                out.sort(key=lambda s: (s[1] - lat) ** 2 + (s[2] - lng) ** 2)
                self._send_json(200, {"list": out[:900], "updated": upd})
            except Exception as e:
                self._send_json(500, {"list": [], "err": str(e)})
        elif self.path.startswith("/api/airports"):
            self._send_state(AIRPORTS)
        elif self.path.startswith("/api/photo-progress"):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            with PHOTO_JOB_LOCK:
                job = dict(PHOTO_JOBS.get(p.get("token", [""])[0]) or {"status": "inconnu"})
            job.pop("t", None)
            self._send_json(200, job)
        elif self.path.startswith("/api/photo-cases"):
            self._send_json(200, {"cases": case_list()})
        elif self.path.startswith("/api/photo-batch"):
            with LOCK:
                self._send_json(200, dict(BATCH, results=list(BATCH["results"])))
        elif self.path.startswith("/api/photo-report"):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            case_id = os.path.basename(p.get("id", [""])[0])
            path = os.path.join(CASE_DIR, case_id, "rapport.html")
            if case_id and os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(404, "rapport introuvable", "text/plain; charset=utf-8")
        elif self.path.startswith("/api/photo-verify"):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            with VERIFY_LOCK:
                job = dict(VERIFY_JOBS.get(p.get("token", [""])[0]) or {"status": "inconnu"})
            job.pop("t", None)
            self._send_json(200, job)
        elif self.path.startswith("/api/geo-status"):
            try:
                import importlib.util
                has_geoclip = importlib.util.find_spec("geoclip") is not None
            except Exception:
                has_geoclip = False
            info = {"geoclip": has_geoclip, "loaded": GEOCLIP["net"] is not None,
                    "device": GEOCLIP["device"], "error": GEOCLIP["error"],
                    "provider": VLM_PROVIDER, "vlm_model": VLM_MODEL}
            if VLM_PROVIDER == "ollama":
                status = local_llm_status()
                models = status.get("models") or []
                info["ollama"] = status.get("online", False)
                info["vlm_ready"] = any(m == VLM_MODEL or m.split(":")[0] == VLM_MODEL.split(":")[0]
                                        for m in models)
            else:
                info["ollama"] = True
                info["vlm_ready"] = bool(VLM_KEY and VLM_BASE)
            self._send_json(200, info)
        elif self.path.startswith("/api/llm-status"):
            self._send_json(200, local_llm_status())
        elif self.path.startswith("/api/flight-route"):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._send_json(200, flight_route_lookup(p.get("callsign", [""])[0]))
        elif self.path.startswith("/api/events"):
            self._send_state(EVENTS)
        elif self.path.startswith("/api/cables"):
            with LOCK:
                gj = CABLES["geojson"]
            self._send(200, gj or '{"type":"FeatureCollection","features":[]}', "application/json; charset=utf-8")
        elif self.path.startswith("/translate"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                text = (p.get("q", [""])[0] or "")[:1800]
                tl = p.get("tl", ["fr"])[0]
                if not text.strip():
                    self._send(400, json.dumps({"ok": False}), "application/json; charset=utf-8")
                    return
                u = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="
                     + urllib.parse.quote(tl) + "&dt=t&q=" + urllib.parse.quote(text))
                arr = json.loads(http_get(u, timeout=15))
                tr = "".join(x[0] for x in arr[0] if x and x[0])
                self._send(200, json.dumps({"ok": True, "text": tr}), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "err": str(e)}), "application/json; charset=utf-8")
        elif self.path.startswith("/detect-stop"):
            p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            token = p.get("token", [""])[0]
            stopped = False
            with LOCK:
                if token and token == DETECT_TOKEN[0]:
                    try:
                        if DETECT[0] is not None and DETECT[0].poll() is None:
                            DETECT[0].terminate(); DETECT[0].wait(timeout=2)
                    except Exception:
                        pass
                    DETECT[0] = None; DETECT_TOKEN[0] = None; stopped = True
            self._send(200, json.dumps({"ok": True, "stopped": stopped}), "application/json; charset=utf-8")
        elif self.path.startswith("/detect"):
            try:
                p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                src = p.get("src", ["hls"])[0]
                cid = p.get("id", [""])[0]
                url = p.get("url", [""])[0]
                title = p.get("title", [cid or "cam"])[0][:70]
                args = None
                if src in ("hls", "youtube") and re.match(r"^[\w-]+$", cid or ""):
                    args = [src, cid, title]
                elif src == "skyline" and url.startswith(SKY_BASE + "en/webcam/") and url.endswith(".html"):
                    args = [src, url, title]
                elif src in ("video", "img") and url.startswith("https://") and any(d in url for d in ALLOWED_DETECT):
                    args = [src, url, title]
                elif src == "nydot" and url.startswith("https://") and any(d in url for d in ALLOWED_DETECT):
                    args = ["video", url, title]
                elif src == "taxi" and url.startswith(TAXI_BASE + "en/") and url.endswith(".html"):
                    r = detect_args_from_source(webcam_taxi_embed(url))
                    if r:
                        args = r + [title]
                elif src == "hopper":
                    st = webcam_hopper_stream(url, cid)
                    r = None
                    if isinstance(st, dict):
                        u = st.get("url", "")
                        if u.startswith("/api/skyline-proxy") and "url=" in u:
                            r = ["video", urllib.parse.unquote(u.split("url=", 1)[1])]
                        else:
                            r = detect_args_from_source(u)
                    if r:
                        args = r + [title]
                ok = False
                if args:
                    here = os.path.dirname(os.path.abspath(__file__))
                    script = os.path.join(here, "detect_stream.py")
                    with LOCK:
                        try:
                            if DETECT[0] is not None and DETECT[0].poll() is None:
                                DETECT[0].terminate(); DETECT[0].wait(timeout=2)
                        except Exception:
                            pass
                        popen_options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
                        DETECT[0] = subprocess.Popen([sys.executable, script] + args, **popen_options)
                        DETECT_TOKEN[0] = "%x" % time.time_ns()
                    ok = True
                self._send(200 if ok else 400, json.dumps({"ok": ok, "token": DETECT_TOKEN[0] if ok else None,
                    "frame_url": "http://127.0.0.1:8772/frame.jpg" if ok else None,
                    "stream_url": "http://127.0.0.1:8772/stream.mjpg" if ok else None,
                    "meta_url": "http://127.0.0.1:8772/meta.json" if ok else None}), "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "err": str(e)}), "application/json; charset=utf-8")
        else:
            chemin = urllib.parse.urlparse(self.path).path
            contenu, ctype = fichier_web("index.html" if chemin in ("/", "") else chemin)
            if contenu is None:
                self._send(404, "introuvable", "text/plain; charset=utf-8")
            else:
                self._send_bytes(200, contenu, ctype)

    def do_POST(self):
        if not self._autorise():
            return
        route = urllib.parse.urlparse(self.path).path
        big = ("/api/geolocate", "/api/photo-save", "/api/photo-anonymize", "/api/chat")
        if route not in ("/api/llm-analyze",) + big + ("/api/photo-batch",):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        cap = 33 * 1024 * 1024 if route in big else 65536
        try:
            length = min(cap, max(0, int(self.headers.get("Content-Length") or 0)))
            payload = json.loads(self.rfile.read(length).decode("utf-8", "replace") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("payload invalide")
            if ROLE == "site" and route in ROUTES_GPU:
                # le VPS n'a pas de GPU : on delegue, puis on complete avec nos catalogues
                resultat = relais_ia(route, dict(payload, progressif=False, verify=True))
                if route == "/api/geolocate":
                    meilleur = resultat.get("best") or {}
                    if meilleur.get("lat") is not None:
                        resultat.setdefault("checks", {})["cameras"] = cameras_near(
                            meilleur["lat"], meilleur["lng"])
                self._send_json(200, resultat)
            elif route == "/api/geolocate":
                if payload.get("progressif"):
                    token = "%x" % time.time_ns()
                    with PHOTO_JOB_LOCK:
                        PHOTO_JOBS[token] = {"status": "running", "etape": "demarrage",
                                             "t": time.time(), "result": {}}
                    threading.Thread(target=photo_locate_job, args=(token, payload),
                                     daemon=True).start()
                    self._send_json(200, {"ok": True, "token": token})
                else:
                    self._send_json(200, photo_locate(payload))
            elif route == "/api/chat":
                self._send_json(200, photo_chat(payload))
            elif route == "/api/photo-save":
                self._send_json(200, case_save(payload))
            elif route == "/api/photo-anonymize":
                if photo_osint is None:
                    raise RuntimeError("module photo_osint absent")
                raw = str(payload.get("image") or "")
                if "," in raw[:64]:
                    raw = raw.split(",", 1)[1]
                os.makedirs(CASE_DIR, exist_ok=True)
                src = os.path.join(CASE_DIR, "_anon_src.jpg")
                dst = os.path.join(CASE_DIR, "anonyme-%s.jpg" % time.strftime("%Y%m%d-%H%M%S"))
                with open(src, "wb") as f:
                    f.write(base64.b64decode(re.sub(r"\s+", "", raw), validate=False))
                out = photo_osint.anonymize(src, dst)
                try:
                    if out.get("ok"):
                        with open(dst, "rb") as f:
                            out["apercu"] = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
                    os.remove(src)
                except OSError:
                    pass
                self._send_json(200, out)
            elif route == "/api/photo-batch":
                with LOCK:
                    busy = BATCH["status"] == "running"
                if busy:
                    self._send_json(200, {"ok": False, "error": "un lot est deja en cours"})
                else:
                    threading.Thread(target=batch_run,
                                     args=(str(payload.get("folder") or ""), payload),
                                     daemon=True).start()
                    self._send_json(200, {"ok": True})
            else:
                self._send_json(200, local_llm_analyze(payload))
        except Exception as e:
            model = VLM_MODEL if route == "/api/geolocate" else LLM_MODEL
            self._send_json(503, {"ok": False, "model": model, "error": str(e)[:300]})


WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
WEB_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
             ".js": "application/javascript; charset=utf-8", ".png": "image/png",
             ".svg": "image/svg+xml", ".ico": "image/x-icon", ".json": "application/json"}


def fichier_web(nom):
    """Sert un fichier du dossier web/. Le front vit dans de vrais fichiers : coloration
    syntaxique, devtools avec noms de fichiers, et rechargement sans redemarrer Python."""
    chemin = os.path.normpath(os.path.join(WEB_DIR, nom.lstrip("/")))
    if not chemin.startswith(WEB_DIR) or not os.path.isfile(chemin):
        return None, None
    with open(chemin, "rb") as f:
        return f.read(), WEB_TYPES.get(os.path.splitext(chemin)[1].lower(),
                                       "application/octet-stream")


def main():
    with LOCK:
        WUC["cams"] = _load(WUC_CACHE_FILE, [])
        SKY["cams"] = _load(SKY_CACHE_FILE, [])
        TAXI["cams"] = _load(TAXI_CACHE_FILE, [])
        HOPPER["cams"] = _load(HOPPER_CACHE_FILE, [])
        NYDOT["cams"] = _load(NYDOT_CACHE_FILE, [])
    if ROLE == "worker":
        print("MODE POSTE DE CALCUL : traitements GPU uniquement, aucun collecteur")
        if photo_osint is not None:
            threading.Thread(target=geoclip_model, daemon=True).start()
        srv = ThreadingHTTPServer((BIND, PORT), Handler)
        print("en ecoute sur %s:%d" % (BIND, PORT))
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nArret.")
        return
    threading.Thread(target=wuc_loop, daemon=True).start()
    threading.Thread(target=tfl_loop, daemon=True).start()
    threading.Thread(target=fin_loop, daemon=True).start()
    threading.Thread(target=earth_loop, daemon=True).start()
    threading.Thread(target=skyline_loop, daemon=True).start()
    threading.Thread(target=webcam_taxi_loop, daemon=True).start()
    threading.Thread(target=webcam_hopper_loop, daemon=True).start()
    threading.Thread(target=nydot_loop, daemon=True).start()
    estore_boot()  # recharge les evenements des dernieres 24h (survit au redemarrage)
    threading.Thread(target=events_loop, daemon=True).start()
    threading.Thread(target=gdacs_loop, daemon=True).start()
    threading.Thread(target=quake_loop, daemon=True).start()
    threading.Thread(target=firms_loop, daemon=True).start()
    threading.Thread(target=acled_loop, daemon=True).start()
    threading.Thread(target=refine_positions_loop, daemon=True).start()
    threading.Thread(target=cables_load, daemon=True).start()
    # Prechargement : GeoCLIP met ~20 s a charger ses poids. Le faire au demarrage
    # evite de payer cette attente sur la premiere photo analysee.
    if photo_osint is not None and ROLE != "site":
        threading.Thread(target=geoclip_model, daemon=True).start()
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://localhost:%d" % PORT
    print("Live Public Cam Map ->", url)
    print("role : %s%s" % (ROLE, (" -> calcul delegue a " + IA_URL) if ROLE == "site" and IA_URL else ""))
    if MODE_PUBLIC:
        print("MODE SITE : ecoute sur %s:%d" % (BIND, PORT))
        print("  jeton d'acces : %s" % ("defini" if SITE_TOKEN else "MANQUANT (definis CARTE_TOKEN)"))
        print("  routes locales desactivees : %s" % ", ".join(ROUTES_LOCALES))
    if ROLE == "site" or MODE_PUBLIC:
        print("Mode serveur : aucune fenetre native, Ctrl+C pour arreter.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nArret.")
        return
    try:
        import webview
        webview.create_window("Carte Cameras Live", url, width=1400, height=860)
        webview.start()
    except Exception as e:
        print("Fenetre native indisponible (%s) -> mode application (Chrome)." % e)
        launched = False
        for appexe in ("chrome", "msedge"):
            try:
                subprocess.Popen('start "" %s --app=%s --window-size=1400,880' % (appexe, url), shell=True)
                launched = True
                break
            except Exception:
                pass
        if not launched:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nArret.")


if __name__ == "__main__":
    main()
