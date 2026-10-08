# Reps — montage automatique de séances de sport

Tu filmes ta séance sur trépied, Reps fait le montage :

1. **Détecte tes séries** grâce au mouvement : caméra fixe, donc tout ce qui bouge, c'est toi. Le repos est coupé.
2. **Associe chaque série à un exercice** d'après la liste que tu donnes (nombre de séries, ou les pauses les plus longues).
3. **Choisit les meilleurs passages** : la dernière série (les reps les plus dures) et les plus intenses.
4. **Monte en 9:16** (1080×1920, 30 i/s) : hook de 2 s, recadrage automatique sur toi, zooms, étalonnage, textes animés (exercice, séries×reps, charge), texte de fin.
5. **Exporte** un MP4 prêt pour TikTok et Reels, plus une image de couverture.

Tout tourne en local. Aucune vidéo n'est envoyée en ligne.

## Installation (une fois)

1. **Python 3.10+** : https://www.python.org/downloads/ (sous Windows, coche « Add Python to PATH »).
2. **FFmpeg** :
   - Windows : `winget install Gyan.FFmpeg`
   - macOS : `brew install ffmpeg`
   - Linux : `sudo apt install ffmpeg`
3. Dans un terminal, dans le dossier du projet :
   ```bash
   python -m venv .venv
   # Windows : .venv\Scripts\activate    macOS/Linux : source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Utilisation

### Interface web (recommandé)

```bash
python -m reps
```

Le navigateur s'ouvre sur http://127.0.0.1:8000. Ensuite :

1. Glisse tes rushes.
2. Vérifie les séries détectées et clique sur une série pour l'exclure.
3. Liste tes exercices dans l'ordre (nom, séries, reps, charge) et choisis l'accroche et le style.
4. Clique sur **Monter la vidéo**.

Les vidéos sont enregistrées dans `~/Reps/projets/`. Pour changer ce dossier, définis la variable d'environnement `REPS_HOME`.

### Ligne de commande

```bash
python -m reps.cli seance/*.mp4 \
  -e "Développé couché | 4x8 | 80kg" \
  -e "Dips lestés | 3x10 | +20kg" \
  --hook "Séance pecs" --cta "Enregistre pour ta prochaine séance" \
  --style energique --duree 30 -o pecs.mp4
```

`--analyse-seule` liste les séries détectées avec leur identifiant. Pour en ignorer une, passe cet identifiant à `--exclure s0-2`.

## Bien filmer (ça conditionne le résultat)

- **Trépied fixe, aucun mouvement de caméra.** La détection repose dessus.
- **Téléphone en vertical**, en 1080p ou 4K. Un rush horizontal est recadré, donc moins net.
- **Corps entier dans le cadre**, sans personne qui passe derrière toi pendant les séries.
- Un fichier par exercice, ou un seul long fichier : les deux fonctionnent. Garde l'ordre chronologique : les noms de fichiers du téléphone (IMG_0412, IMG_0413…) le donnent.
- **Musique** : laisse vide et ajoute un son tendance dans TikTok ou Instagram au moment de publier. Si tu en importes une, elle doit être libre de droits. Ses coupes sont alors calées sur le tempo.

## Styles

| Style | Rythme | Caméra | Étalonnage |
|---|---|---|---|
| Énergique | plans accélérés ×1,1 | zoom « punch » en fin de plan, flash après le hook | contrasté, saturé, accent citron vert |
| Cinématique | vitesse réelle | zoom lent continu | désaturé, tons froids, accent orange |
| Clean | vitesse réelle | fixe | naturel |

Les styles sont définis dans `reps/styles.py`. Tu peux en ajouter un en quelques lignes.

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

Les tests génèrent une vidéo de synthèse (un « athlète » qui fait des séries, puis se repose). Ils vérifient la détection des séries, des répétitions et de la position du sujet, le regroupement par exercice, le rendu 1080×1920 et l'estimation du tempo.

## Architecture

```
reps/
  media.py     ffprobe/ffmpeg : métadonnées, décodage basse résolution
  motion.py    signal de mouvement, détection des séries, cadence des reps, meilleure fenêtre
  plan.py      séries + exercices -> plan de montage (plans, textes, durées)
  captions.py  textes animés (ASS / libass)
  render.py    rendu ffmpeg en une passe
  music.py     estimation du BPM
  pipeline.py  orchestration
  cli.py       ligne de commande
  server.py    API locale (FastAPI) + interface web (reps/web)
```

## Limites connues

- La détection suppose une caméra fixe. Un trépied qui bouge ou une salle très fréquentée en arrière-plan produisent de fausses séries. Exclus-les dans l'interface.
- Le nombre de répétitions affiché est une estimation (autocorrélation du mouvement). Il ne sert qu'à titre indicatif.
- Pas de publication automatique. Les API TikTok et Instagram exigent un audit de l'app ou un compte Business relié à Facebook.
