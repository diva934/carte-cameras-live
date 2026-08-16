#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_stream.py <mode> <id_or_url> <title>
  mode = "hls"   -> id WhatsUpCams (resolution CDN)
         "video" -> URL directe (MP4/HLS, ex: TfL JamCams)
         "img"   -> URL image JPEG rafraichie (ex: Finlande)
         "skyline" -> page SkylineWebcams (resolution HLS officielle)

YOLO26 + suivi anonyme des personnes avec ByteTrack (IDs temporaires).
La fenetre compacte affiche un recadrage agrandi de la personne suivie.
Touche : [q] pour quitter.
"""
import os, sys, time, threading, urllib.request, json, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = os.path.join(BASE_DIR, "yolo26n.pt")
DEVICE = "cpu"
IMGSZ = 960   # 640 -> 960 : bien meilleure detection des sujets petits/lointains (webcams)
CONF = 0.22   # legerement plus bas pour rattraper les petites detections faibles


def pick_model_and_device():
    """Choix auto : modele affine (entrainement) > gros modele sur GPU > nano (repli sur)."""
    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = 0
    except Exception:
        pass
    forced = os.environ.get("CARTE_YOLO")                 # pour imposer un modele precis
    if forced and os.path.exists(os.path.join(BASE_DIR, forced)):
        return os.path.join(BASE_DIR, forced), device
    finetuned = os.path.join(BASE_DIR, "yolo_camera.pt")  # produit par train_overnight.py
    if os.path.exists(finetuned):
        return finetuned, device
    if device != "cpu":
        # Mesure : yolo11l met plus de 100 s a se charger quand la carte est deja
        # occupee par GeoCLIP (6 Go au total). Sous 3,5 Go libres on prend le modele
        # nano, qui se charge en quelques secondes et suffit au suivi.
        libre = 0.0
        try:
            import torch as _t
            libre = _t.cuda.mem_get_info()[0] / (1024 ** 3)
        except Exception:
            pass
        gros = os.path.join(BASE_DIR, "yolo11l.pt")
        if libre >= 3.5 and os.path.exists(gros):
            return gros, device
        print("VRAM libre %.1f Go -> modele leger pour un demarrage rapide" % libre, flush=True)
        return DEFAULT_MODEL, device
    return DEFAULT_MODEL, device
TRACKER = os.path.join(BASE_DIR, "bytetrack_live.yaml")
CONFIRM_HITS = 2
LOST_TTL = 1.2
# Personne + vehicules + animaux (COCO). Tout ce qui bouge est suivi.
CLASSES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
# Libelles FR + priorite de saillance (plus haut = choisi en priorite a taille egale)
CLASS_FR = {
    "person": "PERSONNE", "bicycle": "VELO", "car": "VOITURE", "motorcycle": "MOTO",
    "airplane": "AVION", "bus": "BUS", "train": "TRAIN", "truck": "CAMION", "boat": "BATEAU",
    "bird": "OISEAU", "cat": "CHAT", "dog": "CHIEN", "horse": "CHEVAL", "sheep": "MOUTON",
    "cow": "VACHE", "elephant": "ELEPHANT", "bear": "OURS", "zebra": "ZEBRE", "giraffe": "GIRAFE",
}
CLASS_PRIORITY = {"person": 2.0, "car": 1.3, "truck": 1.3, "bus": 1.3, "motorcycle": 1.2,
                  "bicycle": 1.1, "dog": 1.4, "cat": 1.4, "bird": 1.2}
VEHICLES = {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}

_frame = [None]
_frame_seq = [0]
_boxes = [[]]
_boxes_seq = [0]
_stop = [False]
_postit_jpeg = [None]
_postit_time = [0.0]
_postit_meta = [{"detected": False, "seq": 0}]
POSTIT_PORT = 8772

# ---- Super-resolution IA (Real-ESRGAN compact, GPU) avec repli sur l'upscale classique ----
_SR = {"net": None, "ok": None}
SR_WEIGHTS = os.path.join(BASE_DIR, "realesr-general-x4v3.pth")
SR_URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
          "v0.2.5.0/realesr-general-x4v3.pth")

def _sr_init():
    """Charge le reseau SRVGGNetCompact une seule fois. False si indispo (=> repli).
    Desactive par defaut : la super-resolution est cosmetique et prend de la VRAM
    dont le detecteur a besoin. CARTE_SR=1 pour la reactiver."""
    if os.environ.get("CARTE_SR") != "1":
        _SR["ok"] = False
        return False
    if _SR["ok"] is not None:
        return _SR["ok"]
    try:
        import torch
        import torch.nn as nn
        if not torch.cuda.is_available():
            _SR["ok"] = False
            print("SR IA : pas de GPU -> upscale classique.")
            return False

        class SRVGGCompact(nn.Module):
            def __init__(self, num_feat=64, num_conv=32, upscale=4):
                super().__init__()
                self.upscale = upscale
                self.body = nn.ModuleList()
                self.body.append(nn.Conv2d(3, num_feat, 3, 1, 1))
                self.body.append(nn.PReLU(num_parameters=num_feat))
                for _ in range(num_conv):
                    self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
                    self.body.append(nn.PReLU(num_parameters=num_feat))
                self.body.append(nn.Conv2d(num_feat, 3 * upscale * upscale, 3, 1, 1))
                self.upsampler = nn.PixelShuffle(upscale)

            def forward(self, x):
                out = x
                for layer in self.body:
                    out = layer(out)
                out = self.upsampler(out)
                out = out + nn.functional.interpolate(x, scale_factor=self.upscale, mode="nearest")
                return out

        if not os.path.exists(SR_WEIGHTS):
            print("Telechargement du modele de super-resolution...")
            urllib.request.urlretrieve(SR_URL, SR_WEIGHTS)
        net = SRVGGCompact(num_conv=32, upscale=4)
        sd = torch.load(SR_WEIGHTS, map_location="cpu")
        sd = sd.get("params", sd.get("params_ema", sd)) if isinstance(sd, dict) else sd
        net.load_state_dict(sd, strict=True)
        net.eval().cuda()
        _SR["net"] = net
        _SR["ok"] = True
        print("Super-resolution IA activee (Real-ESRGAN compact, GPU).")
    except Exception as e:
        _SR["ok"] = False
        print("SR IA indisponible -> upscale classique:", e)
    return _SR["ok"]

def sr_upscale(bgr):
    """Super-resolution x4 d'un petit crop BGR. Retourne l'image ou None (repli)."""
    if not _sr_init():
        return None
    try:
        import torch
        h, w = bgr.shape[:2]
        if h * w > 160000 or h < 8 or w < 8:   # limite pour rester temps reel
            return None
        rgb = np.ascontiguousarray(bgr[:, :, ::-1]).astype(np.float32) / 255.0
        t = torch.from_numpy(rgb).permute(2, 0, 1).unsqueeze(0).cuda()
        with torch.no_grad():
            out = _SR["net"](t).clamp_(0, 1)
        out = out.squeeze(0).permute(1, 2, 0).cpu().numpy()
        return (out[:, :, ::-1] * 255.0 + 0.5).astype(np.uint8)   # RGB->BGR
    except Exception:
        return None


class PostitHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/meta.json":
            data = json.dumps(_postit_meta[0], separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                self.wfile.write(data)
            except Exception:
                pass
            return
        if path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            last_seq = -1
            try:
                while True:
                    meta = _postit_meta[0]
                    seq = int(meta.get("seq", 0))
                    data = _postit_jpeg[0]
                    if data and seq != last_seq and time.monotonic() - _postit_time[0] <= 2.0:
                        head = ("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(data)).encode("ascii")
                        self.wfile.write(head + data + b"\r\n")
                        self.wfile.flush()
                        last_seq = seq
                    else:
                        time.sleep(0.015)
            except Exception:
                pass
            return
        if path != "/frame.jpg":
            self.send_response(404); self.end_headers(); return
        data = _postit_jpeg[0]
        # 1,5 s etait trop strict : une camera de type image ne se rafraichit qu'au mieux
        # toutes les 1,5 s, donc le post-it etait presque toujours juge perime et le
        # navigateur ne recevait que des 404. On sert la derniere image connue ;
        # meta.json porte deja l'information de fraicheur.
        if not data or time.monotonic() - _postit_time[0] > 30.0:
            self.send_response(404)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass


def postit_server():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", POSTIT_PORT), PostitHandler)
        server.serve_forever()
    except Exception as e:
        print("Post-it HTTP:", e)


def color_for(tid):
    import colorsys
    h = (int(tid) * 0.61803398875) % 1.0 if tid is not None else 0.33
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 1.0)
    return (int(b * 255), int(g * 255), int(r * 255))


def resolve_hls(cid):
    for i in range(1, 13):
        url = "https://cdn-%03d.whatsupcams.com/hls/%s.m3u8" % (i, cid)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status == 200 and b"#EXTM3U" in r.read(300):
                    return url
        except Exception:
            pass
    return None


def resolve_youtube(vid):
    try:
        import yt_dlp
    except Exception:
        return None
    opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True,
            "format": "best[height<=720]/best"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=%s" % vid, download=False)
        if info.get("url"):
            return info["url"]
        for f in reversed(info.get("formats", []) or []):
            if f.get("url"):
                return f["url"]
    except Exception as e:
        print("yt-dlp:", e)
    return None


def resolve_skyline(page_url):
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
        page = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        import re
        match = re.search(r"source\s*:\s*['\"]([^'\"]+)", page)
        if match:
            return "https://hd-auth.skylinewebcams.com/" + match.group(1).replace("livee.", "live.")
    except Exception as e:
        print("SkylineWebcams:", e)
    return None


def video_reader(stream):
    # OpenCV 5 choisit parfois le lecteur CAP_IMAGES pour une URL de flux et croit lire
    # une sequence d'images numerotees ('expected 0?[1-9][du] pattern'). On impose FFMPEG.
    cap = cv2.VideoCapture(stream, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    while not _stop[0]:
        ok, f = cap.read()
        if not ok:
            cap.release()
            time.sleep(0.3)
            cap = cv2.VideoCapture(stream, cv2.CAP_FFMPEG)   # reboucle (clips MP4 courts)
            continue
        _frame[0] = f
        _frame_seq[0] += 1
    cap.release()


def img_reader(url):
    while not _stop[0]:
        try:
            u = url + ("&" if "?" in url else "?") + "_t=" + str(int(time.time() * 1000))
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=8).read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                _frame[0] = img
                _frame_seq[0] += 1
        except Exception:
            pass
        time.sleep(1.5)


def detector(model):
    use_track = True
    track_errors = 0
    last_frame_seq = -1
    tracks = {}
    while not _stop[0]:
        frame_seq = _frame_seq[0]
        f = _frame[0]
        if f is None or frame_seq == last_frame_seq:
            time.sleep(0.005)
            continue
        last_frame_seq = frame_seq
        try:
            if use_track:
                res = model.track(f, persist=True, tracker=TRACKER, device=DEVICE,
                                  classes=CLASSES, imgsz=IMGSZ, conf=CONF, verbose=False)
            else:
                res = model.predict(f, imgsz=IMGSZ, conf=CONF, device=DEVICE, classes=CLASSES, verbose=False)
            track_errors = 0
        except Exception as e:
            track_errors += 1
            print("track KO (%d/3):" % track_errors, e)
            if track_errors >= 3:
                use_track = False
                print("Repli sur la detection sans suivi.")
            try:
                res = model.predict(f, imgsz=IMGSZ, conf=CONF, device=DEVICE,
                                    classes=CLASSES, verbose=False)
            except Exception as predict_error:
                print("predict KO:", predict_error)
                continue
        now = time.monotonic()
        detected = set()
        immediate = []
        for r in res:
            for b in r.boxes:
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
                cls = model.names[int(b.cls[0])]
                conf = float(b.conf[0])
                tid = int(b.id[0]) if getattr(b, "id", None) is not None else None
                box = (x1, y1, x2, y2, cls, conf, tid)
                if tid is None:
                    immediate.append(box)
                    continue
                detected.add(tid)
                state = tracks.get(tid)
                if state is None:
                    tracks[tid] = {"hits": 1, "last": now, "box": box}
                else:
                    state["hits"] += 1
                    state["last"] = now
                    state["box"] = box
        out = list(immediate)
        for tid, state in list(tracks.items()):
            age = now - state["last"]
            if age > LOST_TTL:
                del tracks[tid]
                continue
            if state["hits"] >= CONFIRM_HITS:
                out.append(state["box"])
        _boxes[0] = out
        _boxes_seq[0] += 1


def main():
    if len(sys.argv) < 3:
        print("usage: detect_stream.py <hls|video|img|skyline> <id_or_url> [title]")
        return
    mode, arg = sys.argv[1], sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else mode

    if mode == "hls":
        print("Resolution du flux HLS...")
        stream = resolve_hls(arg)
        if not stream:
            print("Flux hors ligne.")
            time.sleep(4); return
        threading.Thread(target=video_reader, args=(stream,), daemon=True).start()
    elif mode == "video":
        threading.Thread(target=video_reader, args=(arg,), daemon=True).start()
    elif mode == "youtube":
        print("Resolution YouTube (yt-dlp)...")
        stream = resolve_youtube(arg)
        if not stream:
            print("Flux YouTube introuvable.")
            time.sleep(4); return
        threading.Thread(target=video_reader, args=(stream,), daemon=True).start()
    elif mode == "skyline":
        print("Resolution SkylineWebcams...")
        stream = resolve_skyline(arg)
        if not stream:
            print("Flux SkylineWebcams introuvable.")
            time.sleep(4); return
        threading.Thread(target=video_reader, args=(stream,), daemon=True).start()
    elif mode == "img":
        threading.Thread(target=img_reader, args=(arg,), daemon=True).start()
    else:
        print("mode inconnu"); return

    global DEVICE
    model_path, DEVICE = pick_model_and_device()
    print("Chargement du modele %s sur %s..." % (os.path.basename(model_path), "GPU" if DEVICE != "cpu" else "CPU"))
    from ultralytics import YOLO
    model = YOLO(model_path)

    _postit_meta[0] = {"detected": False, "seq": 0, "statut": "connexion au flux video",
                       "boxes": [], "subjects": []}
    t0 = time.time()
    while _frame[0] is None and time.time() - t0 < 20:
        time.sleep(0.1)
    if _frame[0] is None:
        print("Pas d'image recue.")
        return
    threading.Thread(target=detector, args=(model,), daemon=True).start()
    threading.Thread(target=postit_server, daemon=True).start()

    # Carte haute resolution : l'upscale Lanczos est renforce par contraste local
    # et nettete, sans pretendre recreer les details absents de la source.
    out_w, out_h, header_h = 480, 600, 56
    clahe = cv2.createCLAHE(clipLimit=1.7, tileGridSize=(8, 8))
    focus_id = None
    focus_box = None
    focus_last = 0.0
    last_encode = 0.0
    postit_seq = 0

    def placeholder(message):
        card = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        card[:] = (9, 14, 18)
        cv2.rectangle(card, (0, 0), (out_w, header_h), (18, 43, 50), -1)
        cv2.putText(card, "SUIVI ANONYME", (16, 36), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (120, 244, 255), 1, cv2.LINE_AA)
        cv2.putText(card, message, (18, out_h // 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.48, (150, 165, 174), 1, cv2.LINE_AA)
        return card

    def person_card(frame, box, count):
        nonlocal focus_box
        x1, y1, x2, y2, _cls, conf, tid = box
        fresh = np.array([x1, y1, x2, y2], dtype=np.float32)
        if focus_box is None:
            focus_box = fresh
        else:
            # Lissage du cadre : assez reactif pour suivre, sans tremblement.
            focus_box = focus_box * 0.70 + fresh * 0.30
        x1, y1, x2, y2 = focus_box
        fh, fw = frame.shape[:2]
        bw, bh = max(24.0, x2 - x1), max(40.0, y2 - y1)
        cx, cy = (x1 + x2) * 0.5, (y1 + y2) * 0.5
        target_h = bh * 1.28
        target_w = max(bw * 1.7, target_h * (out_w / float(out_h - header_h)))
        xa, xb = int(max(0, cx - target_w / 2)), int(min(fw, cx + target_w / 2))
        ya, yb = int(max(0, cy - target_h / 2)), int(min(fh, cy + target_h / 2))
        if xb - xa < 8 or yb - ya < 8:
            return placeholder("Recadrage indisponible")
        crop0 = frame[ya:yb, xa:xb]
        sr = sr_upscale(crop0)   # vraie super-resolution IA (GPU) si dispo
        if sr is not None:
            crop = cv2.resize(sr, (out_w, out_h - header_h), interpolation=cv2.INTER_AREA)
            tier = "IA x4"
        else:
            interpolation = cv2.INTER_LANCZOS4 if crop0.shape[1] < out_w else cv2.INTER_AREA
            crop = cv2.resize(crop0, (out_w, out_h - header_h), interpolation=interpolation)
            # Repli : upscale perceptuel (contraste local + nettete douce).
            lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            crop = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            soft = cv2.GaussianBlur(crop, (0, 0), 0.72)
            crop = cv2.addWeighted(crop, 1.24, soft, -0.24, 0)
            tier = "NET" if bh >= 120 else "SOURCE LIMITEE"
        card = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        card[header_h:] = crop
        cv2.rectangle(card, (0, 0), (out_w, header_h), (14, 55, 43), -1)
        kind = CLASS_FR.get(str(_cls).lower(), str(_cls).upper())
        label = "%s #%s  %s" % (kind, tid if tid is not None else "?", tier)
        cv2.putText(card, label, (14, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.56, (110, 255, 174), 1, cv2.LINE_AA)
        cv2.putText(card, "suivi %.0f%%  |  %d detectee(s)" % (conf * 100, count),
                    (14, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 236, 222), 1, cv2.LINE_AA)
        return card

    focus_cls = "person"
    last_thumbs = 0.0
    subjects_cache = []

    def salience(b):
        cls = str(b[4]).lower()
        return max(1, b[2] - b[0]) * max(1, b[3] - b[1]) * b[5] * CLASS_PRIORITY.get(cls, 1.0)

    def build_subjects(frame, group, fw0, fh0):
        subs = []
        gsort = sorted(group, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)[:5]
        for b in gsort:
            x1, y1, x2, y2 = int(b[0]), int(b[1]), int(b[2]), int(b[3])
            pw = int((x2 - x1) * 0.16) + 2
            ph = int((y2 - y1) * 0.12) + 2
            xa, xb = max(0, x1 - pw), min(fw0, x2 + pw)
            ya, yb = max(0, y1 - ph), min(fh0, y2 + ph)
            crop = frame[ya:yb, xa:xb]
            if crop.shape[0] < 4 or crop.shape[1] < 4:
                continue
            sr = sr_upscale(crop) if (y2 - y1) < 160 else None
            src = sr if sr is not None else crop
            interp = cv2.INTER_LANCZOS4 if src.shape[1] < 100 else cv2.INTER_AREA
            thumb = cv2.resize(src, (100, 132), interpolation=interp)
            ok, enc = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                subs.append({"id": int(b[6]), "cls": str(b[4]).lower(), "box": [x1, y1, x2, y2],
                             "thumb": "data:image/jpeg;base64," + base64.b64encode(enc.tobytes()).decode("ascii")})
        return subs

    while True:
        f = _frame[0]
        if f is not None:
            objs = [b for b in _boxes[0] if b[6] is not None]   # objets suivis (ID stable)
            now = time.monotonic()
            # Priorite : humains ; sinon animaux ; sinon vehicules. On encadre TOUT le groupe.
            group = [b for b in objs if str(b[4]).lower() == "person"]
            if not group:
                group = [b for b in objs if str(b[4]).lower() in ANIMALS]
            if not group:
                group = [b for b in objs if str(b[4]).lower() in VEHICLES]
            boxes_meta = [[int(b[0]), int(b[1]), int(b[2]), int(b[3]), str(b[4]).lower(),
                           (b[6] if b[6] is not None else -1)] for b in group]
            fh0, fw0 = f.shape[:2]
            if now - last_thumbs >= 0.18:
                subjects_cache = build_subjects(f, group, fw0, fh0)
                last_thumbs = now
            chosen = next((b for b in group if focus_id is not None and b[6] == focus_id), None)
            if chosen is None and (focus_id is None or now - focus_last > LOST_TTL):
                chosen = max(group, key=salience, default=None)
                focus_id = chosen[6] if chosen is not None else None
                focus_box = None
            if chosen is not None:
                focus_last = now
                focus_cls = chosen[4]
                card = person_card(f, chosen, len(group))
                if now - last_encode >= 0.05:
                    ok, encoded = cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 94])
                    if ok:
                        postit_seq += 1; last_encode = now
                        _postit_jpeg[0] = encoded.tobytes(); _postit_time[0] = now
                fh, fw = f.shape[:2]
                _postit_meta[0] = {"detected": True, "seq": postit_seq, "track_id": focus_id,
                    "frame_w": fw, "frame_h": fh, "box": [round(float(v), 1) for v in focus_box],
                    "boxes": boxes_meta, "subjects": subjects_cache}
            elif focus_box is not None and now - focus_last <= LOST_TTL:
                stale = tuple(int(v) for v in focus_box) + (focus_cls, 0.0, focus_id)
                card = person_card(f, stale, 0)
                if now - last_encode >= 0.05:
                    ok, encoded = cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 94])
                    if ok:
                        postit_seq += 1; last_encode = now
                        _postit_jpeg[0] = encoded.tobytes(); _postit_time[0] = now
                fh, fw = f.shape[:2]
                _postit_meta[0] = {"detected": True, "seq": postit_seq, "track_id": focus_id,
                    "frame_w": fw, "frame_h": fh, "box": [round(float(v), 1) for v in focus_box],
                    "boxes": boxes_meta, "subjects": subjects_cache}
            else:
                focus_id, focus_box = None, None
                fh, fw = f.shape[:2]
                # Sans explication, une scene vide est indiscernable d'une panne : on
                # publie la raison pour que l'interface puisse la montrer.
                clarte = float(f.mean())
                if clarte < 25:
                    statut = "image trop sombre pour detecter (nuit)"
                elif objs:
                    statut = "objets detectes, suivi en cours de stabilisation"
                else:
                    statut = "aucun objet detecte dans la scene"
                _postit_meta[0] = {"detected": False, "seq": postit_seq, "statut": statut,
                    "clarte": round(clarte, 1),
                    "frame_w": fw, "frame_h": fh, "boxes": boxes_meta, "subjects": subjects_cache}
                if now - focus_last > 2.2:
                    _postit_jpeg[0] = None
        time.sleep(0.025)

    _stop[0] = True


if __name__ == "__main__":
    main()
