import os
import time
import threading
import tkinter as tk

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

POLL_INTERVAL_SEC = 2.0   # hvor ofte vi faktisk spør Spotify (for å unngå rate-limiting)
TICK_INTERVAL_MS = 100    # hvor ofte GUI oppdaterer linjen (jo lavere, jo raskere/jevnere)
BG_COLOR = "#0b0b0f"
FG_ACTIVE = "#ffffff"
FG_DIM = "#666672"
ACCENT = "#1db954"  # Spotify-grønn

# Referansestørrelse vinduet er designet for - skriftstørrelser skaleres opp/ned herfra
BASE_WIDTH = 900
BASE_HEIGHT = 500
BASE_TITLE_SIZE = 26
BASE_SIDE_SIZE = 28
BASE_MAIN_SIZE = 48
MIN_SCALE = 0.5
MAX_SCALE = 3.0


class LyricsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Lyrics")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("900x500")
        self.is_fullscreen = False

        self.root.bind("<f>", self.toggle_fullscreen)
        self.root.bind("<F>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.bind("<q>", lambda e: self.root.destroy())

        # Container som fyller hele vinduet - brukes til å plassere innholdet midt i,
        # uansett vindusstørrelse (også i fullskjerm).
        self.main_frame = tk.Frame(root, bg=BG_COLOR)
        self.main_frame.pack(fill="both", expand=True)

        # Selve innholdet legges i en indre frame som sentreres med place()
        self.content_frame = tk.Frame(self.main_frame, bg=BG_COLOR)
        self.content_frame.place(relx=0.5, rely=0.5, anchor="center")

        # UI-elementer: låt-info øverst, tre lyrics-linjer i midten
        self.track_label = tk.Label(
            self.content_frame, text="Kobler til Spotify …", fg=ACCENT, bg=BG_COLOR,
            font=("Helvetica", BASE_TITLE_SIZE, "bold")
        )
        self.track_label.pack(pady=(0, 20))

        self.prev_label = tk.Label(
            self.content_frame, text="", fg=FG_DIM, bg=BG_COLOR,
            font=("Helvetica", BASE_SIDE_SIZE)
        )
        self.prev_label.pack(pady=8)

        self.current_label = tk.Label(
            self.content_frame, text="", fg=FG_ACTIVE, bg=BG_COLOR,
            font=("Helvetica", BASE_MAIN_SIZE, "bold"), wraplength=1200, justify="center"
        )
        self.current_label.pack(pady=20)

        self.next_label = tk.Label(
            self.content_frame, text="", fg=FG_DIM, bg=BG_COLOR,
            font=("Helvetica", BASE_SIDE_SIZE)
        )
        self.next_label.pack(pady=8)

        self.hint_label = tk.Label(
            root, text="F = fullskjerm   Esc = avslutt fullskjerm   Q = avslutt",
            fg="#333340", bg=BG_COLOR, font=("Helvetica", 10)
        )
        self.hint_label.pack(side="bottom", pady=10)

        # Responsiv skalering: regn ut ny skriftstørrelse når vinduet endrer størrelse
        self.root.bind("<Configure>", self.on_resize)
        self._last_scale = 1.0

        # Spotify-klient
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
            scope="user-read-playback-state",
            cache_path=".cache"
        ))

        self.current_track_id = None
        self.lrc_lines = []  # liste av (ms, tekst)
        self.stop_flag = False

        # For lokal interpolering av avspillingsposisjon mellom Spotify-spørringer
        self.last_known_progress_ms = 0
        self.last_progress_timestamp = time.time()
        self.is_playing = False
        self.progress_lock = threading.Lock()

        # Poll Spotify i egen tråd så GUI ikke fryser
        self.worker = threading.Thread(target=self.poll_loop, daemon=True)
        self.worker.start()

        # Rask GUI-tikker som interpolerer posisjon og oppdaterer linjen jevnt
        self.root.after(TICK_INTERVAL_MS, self.tick)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def tick(self):
        if self.stop_flag:
            return
        with self.progress_lock:
            if self.is_playing and self.lrc_lines:
                elapsed = (time.time() - self.last_progress_timestamp) * 1000
                estimated_progress_ms = self.last_known_progress_ms + elapsed
                self.update_current_line(estimated_progress_ms)
        self.root.after(TICK_INTERVAL_MS, self.tick)

    def on_resize(self, event):
        # Vi bryr oss bare om resize på selve vinduet, ikke på hver indre widget
        # som også sender Configure-eventer.
        if event.widget is not self.root:
            return

        scale = min(event.width / BASE_WIDTH, event.height / BASE_HEIGHT)
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))

        # Unngå å oppdatere fonten på hver eneste pixel - bare når skalaen faktisk
        # har endret seg nok til å utgjøre en forskjell.
        if abs(scale - self._last_scale) < 0.02:
            return
        self._last_scale = scale

        title_size = max(10, int(BASE_TITLE_SIZE * scale))
        side_size = max(8, int(BASE_SIDE_SIZE * scale))
        main_size = max(14, int(BASE_MAIN_SIZE * scale))

        self.track_label.config(font=("Helvetica", title_size, "bold"))
        self.prev_label.config(font=("Helvetica", side_size))
        self.next_label.config(font=("Helvetica", side_size))
        self.current_label.config(
            font=("Helvetica", main_size, "bold"),
            wraplength=max(300, int(event.width * 0.85)),
        )

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)

    def on_close(self):
        self.stop_flag = True
        self.root.destroy()

    # ---------- Lyrics-henting ----------

    def fetch_synced_lyrics(self, title, artist, duration_sec):
        try:
            resp = requests.get(
                "https://lrclib.net/api/get",
                params={
                    "track_name": title,
                    "artist_name": artist,
                    "duration": duration_sec,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("syncedLyrics")
        except requests.RequestException:
            pass
        return None

    def parse_lrc(self, lrc_text):
        lines = []
        for raw_line in lrc_text.split("\n"):
            if raw_line.startswith("["):
                timestamp, _, text = raw_line.partition("]")
                try:
                    minutes, seconds = timestamp[1:].split(":")
                    total_ms = int((float(minutes) * 60 + float(seconds)) * 1000)
                    if text.strip():
                        lines.append((total_ms, text.strip()))
                except ValueError:
                    continue
        return lines

    # ---------- Bakgrunnstråd: poller Spotify ----------

    def poll_loop(self):
        while not self.stop_flag:
            try:
                playback = self.sp.current_playback()
            except Exception as e:
                self.update_track_label(f"Feil: {e}")
                time.sleep(POLL_INTERVAL_SEC)
                continue

            if playback and playback.get("is_playing") and playback.get("item"):
                track = playback["item"]
                progress_ms = playback["progress_ms"]

                if track["id"] != self.current_track_id:
                    self.current_track_id = track["id"]
                    title = track["name"]
                    artist = track["artists"][0]["name"]
                    duration_sec = track["duration_ms"] // 1000

                    self.update_track_label(f"{title} — {artist}")
                    lrc_text = self.fetch_synced_lyrics(title, artist, duration_sec)
                    self.lrc_lines = self.parse_lrc(lrc_text) if lrc_text else []

                    if not self.lrc_lines:
                        self.update_lyrics("", "Ingen synkroniserte lyrics funnet", "")

                # Sett referansepunkt for interpolering - tick() tar seg av
                # å oppdatere linjen jevnt mellom hver spørring herfra.
                with self.progress_lock:
                    self.last_known_progress_ms = progress_ms
                    self.last_progress_timestamp = time.time()
                    self.is_playing = True
            else:
                self.update_track_label("Ingenting spilles av akkurat nå")
                self.update_lyrics("", "", "")
                self.current_track_id = None
                with self.progress_lock:
                    self.is_playing = False

            time.sleep(POLL_INTERVAL_SEC)

    # ---------- Finn riktig linje ----------

    def update_current_line(self, progress_ms):
        # Kalles fra tick() på GUI-tråden - trygt å oppdatere direkte.
        if not self.lrc_lines:
            return
        idx = -1
        for i, (ts, _) in enumerate(self.lrc_lines):
            if ts <= progress_ms:
                idx = i
            else:
                break
        prev_text = self.lrc_lines[idx - 1][1] if idx > 0 else ""
        current_text = self.lrc_lines[idx][1] if idx >= 0 else ""
        next_text = self.lrc_lines[idx + 1][1] if 0 <= idx + 1 < len(self.lrc_lines) else ""
        self.update_lyrics(prev_text, current_text, next_text)

    # ---------- Trådsikre GUI-oppdateringer ----------

    def update_track_label(self, text):
        self.root.after(0, lambda: self.track_label.config(text=text))

    def update_lyrics(self, prev_text, current_text, next_text):
        def apply():
            self.prev_label.config(text=prev_text)
            self.current_label.config(text=current_text)
            self.next_label.config(text=next_text)
        self.root.after(0, apply)


if __name__ == "__main__":
    root = tk.Tk()
    app = LyricsApp(root)
    root.mainloop()