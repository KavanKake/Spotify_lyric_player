# Spotify Lyrics App

A small Python desktop app that shows time-synced lyrics for whatever song is currently playing on Spotify — line by line, in real time.

## Features

- Reads what's currently playing on Spotify (requires Spotify Premium and active playback)
- Shows synced lyrics fetched from [lrclib.net](https://lrclib.net) — previous, current, and next line
- Updates smoothly (10 times per second) by estimating playback position locally, without spamming the Spotify API
- Responsive design — text size scales automatically with the window size
- Fullscreen mode for use as a clean "now playing" display

## Screenshot

![alt text](image.png)

## Requirements

- Python 3.9 or newer
- A free [Spotify Developer](https://developer.spotify.com/dashboard) app (Client ID + Client Secret)
- Spotify Premium (required to read playback status via the API)

## Installation

1. Clone the repo:

   ```bash
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a Spotify app on the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard):
   - Click **Create app**
   - Set **Redirect URI** to `http://127.0.0.1:8888/callback`
   - Check **Web API**
   - Copy your **Client ID** and **Client Secret**

4. Create a `.env` file in the project folder (see `.env.example`):

   ```env
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```

## Usage

```bash
python3 lyrics_app.py
```

The first time you run it, a browser window opens for you to log in and authorize access to your Spotify account. After that, the app runs automatically.

### Keyboard shortcuts

| Key   | Action                |
|-------|------------------------|
| `F`   | Toggle fullscreen       |
| `Esc` | Exit fullscreen         |
| `Q`   | Quit the app             |

## How it works

1. The app queries the Spotify Web API every 2 seconds for what's currently playing and how far into the track you are (`progress_ms`).
2. When a new track is detected, the title/artist are looked up against [lrclib.net](https://lrclib.net), which returns lyrics in LRC format (text lines with timestamps).
3. Between each Spotify query, the app estimates the playback position locally, so the text can update far more often than the API calls allow.
4. The correct line is displayed based on the estimated position.

## Known limitations

- Requires Spotify Premium (playback status isn't available for free accounts via the API)
- Not all songs have synced lyrics available on lrclib.net
- This is a Python script with a GUI window, not a packaged `.app`/`.exe` — it's started from the terminal

## License

Free for personal use. Not affiliated with or endorsed by Spotify or lrclib.net.