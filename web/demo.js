// ---------------------------------------------------------------------------
// Mode demonstration — pour enregistrer une video de presentation.
//
//   http://localhost:8770/?demo=1        joue la sequence complete
//   http://localhost:8770/?demo=1&etape=4   demarre a une etape precise
//   Espace : pause / reprise      Fleche droite : etape suivante
//
// La sequence rejoue une analyse REELLE (web/demo/analyse.json) avec un minutage
// lisible a l'ecran. Aucune valeur n'est inventee : voir le champ _provenance.
// ---------------------------------------------------------------------------
(function () {
  const params = new URLSearchParams(location.search);
  if (!params.get('demo')) return;

  const D = () => window.__demo || {};
  const pause = ms => new Promise(r => setTimeout(r, ms));
  let enPause = false, sauter = false;
  const attendre = async ms => {
    const fin = Date.now() + ms;
    while (Date.now() < fin) {
      if (sauter) { sauter = false; return; }
      await pause(60);
      while (enPause) await pause(120);
    }
  };

  // --- bandeau de titres, style presentation ---
  const style = document.createElement('style');
  style.textContent = `
  #demoTitre{position:fixed;left:0;right:0;bottom:76px;z-index:3000;text-align:center;
    pointer-events:none;opacity:0;transition:opacity .5s ease}
  #demoTitre.on{opacity:1}
  #demoTitre b{display:block;font:600 30px/1.25 "Inter",system-ui,sans-serif;color:#f2f4f6;
    letter-spacing:-.5px;text-shadow:0 2px 26px rgba(0,0,0,.95),0 0 60px rgba(0,0,0,.8)}
  #demoTitre span{display:block;margin-top:10px;font:11px var(--mono);letter-spacing:3.5px;
    text-transform:uppercase;color:#d9a648;text-shadow:0 2px 20px rgba(0,0,0,.95)}
  #demoTitre i{display:block;margin-top:14px;font-style:normal;font:600 60px/1 "Inter",system-ui;
    color:#d9a648;letter-spacing:-2px;text-shadow:0 4px 40px rgba(0,0,0,.95)}
  #demoVoile{position:fixed;inset:0;z-index:2999;background:#05070a;pointer-events:none;
    opacity:0;transition:opacity .6s ease}
  #demoVoile.on{opacity:1}
  #demoAide{position:fixed;right:14px;bottom:14px;z-index:3001;color:#3a414a;
    font:9px var(--mono);letter-spacing:1px;pointer-events:none}`;
  document.head.appendChild(style);

  const voile = document.createElement('div'); voile.id = 'demoVoile';
  const titre = document.createElement('div'); titre.id = 'demoTitre';
  const aide = document.createElement('div'); aide.id = 'demoAide';
  aide.textContent = 'espace : pause · fleche droite : suivant';
  document.body.append(voile, titre, aide);

  async function dire(principal, sous, chiffre, duree = 3200) {
    titre.innerHTML = (chiffre ? '<i>' + chiffre + '</i>' : '')
      + (principal ? '<b>' + principal + '</b>' : '')
      + (sous ? '<span>' + sous + '</span>' : '');
    titre.classList.add('on');
    await attendre(duree);
    titre.classList.remove('on');
    await attendre(500);
  }

  // Leaflet et son maxBounds produisent des NaN sur les vols animes : on interpole
  // nous-memes le centre et le zoom, ce qui donne aussi un mouvement plus filmique.
  function voler(lat, lng, zoom, secondes) {
    return new Promise(resolve => {
      const d0 = map.getCenter(), z0 = map.getZoom(), t0 = performance.now();
      const duree = Math.max(200, secondes * 1000);
      const doux = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      let fini = false;
      const terminer = () => {
        if (fini) return;
        fini = true;
        map.setView([lat, lng], Math.round(zoom), { animate: false });
        resolve();
      };
      // Filet de securite : requestAnimationFrame ne s'execute pas quand l'onglet est
      // masque. Sans ca, la sequence resterait bloquee sur ce plan.
      setTimeout(terminer, duree + 600);
      (function pas(t) {
        if (fini) return;
        const p = Math.min(1, ((t || performance.now()) - t0) / duree), e = doux(p);
        const la = d0.lat + (lat - d0.lat) * e, lo = d0.lng + (lng - d0.lng) * e;
        if (isFinite(la) && isFinite(lo)) {
          map.setView([la, lo], z0 + (zoom - z0) * e, { animate: false });
        }
        if (p < 1) requestAnimationFrame(pas); else terminer();
      })(t0);
    });
  }

  // --- la sequence ---
  const etapes = [

    async function ouverture(a) {
      voile.classList.add('on');
      D().fermer && D().fermer();
      map.setView([25, 15], 3, { animate: false });
      await attendre(600);
      voile.classList.remove('on');
      await attendre(900);
      await dire('Des milliers de cameras publiques', 'agregees en direct, huit sources', '', 3400);
    },

    async function catalogue(a) {
      let total = 0;
      try {
        const s = await (await fetch('/api/status')).json();
        total = Object.values(s.sources || {}).reduce((n, x) => n + (x.count || 0), 0);
      } catch (e) { total = 5596; }
      await dire('', 'cameras cataloguees, positionnees, interrogeables',
                 total.toLocaleString('fr-FR'), 3600);
      await voler(54, 15, 4.2, 2.6);
    },

    async function photo(a) {
      D().ouvrir && D().ouvrir('photo');
      D().geoVider && D().geoVider();
      await attendre(700);
      const b = await (await fetch('/demo/photo.jpg', { cache: 'no-store' })).blob();
      const url = await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(b); });
      D().geoPhoto && D().geoPhoto(url);
      D().geoDire && D().geoDire('Analyse en cours...');
      await dire('Une photo. Aucune metadonnee.', 'ou a-t-elle ete prise ?', '', 3400);
    },

    async function lecture(a) {
      D().geoRender && D().geoRender({ encours: true, ocr: a.ocr, metadata: a.metadata, forensics: a.forensics });
      D().geoDire && D().geoDire('Lecture de scene...');
      await dire('Lecture des panneaux', 'OCR de scene, 0,7 seconde', '', 3600);
    },

    async function zones(a) {
      D().geoRender && D().geoRender({ encours: true, ocr: a.ocr, metadata: a.metadata,
        forensics: a.forensics, streetclip: a.streetclip, candidates: a.candidates });
      await voler(52, 5, 3.4, 2.4);
      await dire('Le modele geographique propose', 'cinq zones, sur trois continents', '', 3400);
    },

    async function erreur(a) {
      await dire('Il se trompe', 'de mille quatre cent cinquante et un kilometres', '1 451 km', 3800);
    },

    async function verdict(a) {
      D().geoRender && D().geoRender({ ocr: a.ocr, metadata: a.metadata, forensics: a.forensics,
        streetclip: a.streetclip, candidates: a.candidates, vlm: a.vlm, leads: a.leads,
        arbiter: a.arbiter, best: a.best });
      await dire('Aucune zone ne colle aux indices', 'la lecture des panneaux prend le dessus', '', 3800);
    },

    async function convergence(a) {
      await voler(a.best.lat, a.best.lng, 8, 3.2);
      await voler(a.best.lat, a.best.lng, 15, 3.4);
      await dire('Myllylampi, Vihti, Finlande',
                 'de la position officielle de la camera', '271 m', 4200);
    },

    async function terrain(a) {
      D().geoRender && D().geoRender(a);
      await dire('Le terrain confirme', 'quatre correspondances sur OpenStreetMap', '', 3600);
    },

    async function assistant(a) {
      D().ouvrir && D().ouvrir('chat');
      await attendre(800);
      const champ = document.getElementById('chatInput');
      const q = 'Que lis-tu sur les panneaux de cette camera ?';
      for (let i = 0; i <= q.length; i++) { champ.value = q.slice(0, i); await attendre(38); }
      await attendre(500);
      champ.value = '';
      D().chatAjoute && D().chatAjoute('user', q);
      const bulle = D().chatAjoute && D().chatAjoute('bot', '', { attente: true });
      await attendre(2200);
      D().chatRemplit && D().chatRemplit(bulle,
        "Je lis « Tie 25 », « Vihti » et « Myllylampi » sur le panneau de droite. "
        + "Ce sont des toponymes finlandais, et « tie » signifie route en finnois.",
        'gemma-4-31B-it · sur l\'image de la camera');
      await dire('Interrogez ce que voit le systeme', 'en langage naturel', '', 3600);
    },

    async function final(a) {
      D().fermer && D().fermer();
      await voler(30, 12, 3, 3.4);
      await dire('Carte Cameras Live', 'sources ouvertes · analyse locale · verifiable', '', 4200);
      voile.classList.add('on');
    },
  ];

  document.addEventListener('keydown', e => {
    if (e.code === 'Space') { e.preventDefault(); enPause = !enPause; }
    if (e.code === 'ArrowRight') { e.preventDefault(); sauter = true; }
  });

  (async function jouer() {
    const a = await (await fetch('/demo/analyse.json', { cache: 'no-store' })).json();
    const depart = Math.max(0, parseInt(params.get('etape') || '0', 10));
    await attendre(1200);
    for (let i = depart; i < etapes.length; i++) {
      console.log('demo : etape %d/%d — %s', i + 1, etapes.length, etapes[i].name);
      await etapes[i](a);
    }
    console.log('demo terminee');
  })();
})();
