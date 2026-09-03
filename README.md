# STAVA Player

Player audio pentru desktop, scris în Python cu PyQt6 și motorul audio BASS.

**Gratuit și fără scop comercial.** Nu se percep bani pentru acest proiect, nici
acum, nici mai târziu. Vezi [LICENSE](LICENSE).

---

## Ce face

- **Redare** MP3, FLAC, WAV, OGG, M4A, prin motorul nativ BASS
- **Egalizator** cu 10 benzi, preamp, control de bas și înalte
- **Efecte** — spațializare, reverb, tempo, limitator, plus suport pentru
  plugin-uri VST
- **Bibliotecă** cu scanare pe foldere, albume, artiști, piese cele mai ascultate
  și coadă de redare, toate ținute într-o bază SQLite locală
- **Waveform** pre-randat și vizualizator FFT
- **Player în două moduri** — mare, cu artwork și waveform, sau compact lângă
  bibliotecă
- **Discord Rich Presence**, opțional
- **Teme** și zoom reglabil pentru întreaga interfață

## Cerințe

- Python 3.10 sau mai nou
- Windows (motorul BASS e inclus pentru Windows; există și binare macOS în
  `libs/`, dar aplicația e testată pe Windows)

## Instalare

```bash
git clone https://github.com/<utilizator>/stava-player.git
cd stava-player

python -m venv .venv
.venv\Scripts\activate        # pe Windows
pip install -r requirements.txt

python main.py
```

La prima pornire aplicația își creează singură fișierul `settings.ini` cu valori
implicite. Din **Setări → Playlist** alegi folderul cu muzică, iar de acolo
scanarea pornește automat.

## Structura proiectului

| Director | Rol |
|---|---|
| `audio/` | motorul de redare, legătura cu BASS și lanțul de efecte |
| `core/` | orchestrare: sesiune, redare, navigare, evenimente, Discord |
| `playlist/` | bibliotecă, scanare, bază de date, interfața de playlist |
| `tabs/` | ecranele principale — Player, EQ, Playlist, Setări |
| `player/` | widget-urile player-ului și cele două layout-uri |
| `Eq/`, `ui/`, `animations/`, `background/` | componente vizuale și tranziții |
| `libs/` | BASS și plugin-urile VST |

## Note

**Discord Rich Presence** vine cu un Client ID implicit, ca funcția să meargă
fără nicio configurare. Nu e un secret: orice aplicație care folosește Rich
Presence îl trimite către Discord de la fiecare utilizator. Îl poți înlocui cu
ID-ul propriei aplicații Discord din **Setări → Discord**.

**`settings.ini` nu este inclus în repo.** Conține preferințe și căi locale,
diferite de la o instalare la alta, și se generează singur.

## Licență

Cod: [MIT](LICENSE). Bibliotecile din `libs/` aparțin autorilor lor și au
licențele proprii — BASS este gratuit pentru utilizare necomercială.
