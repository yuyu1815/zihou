# Zihou – Hourly Chime Discord Bot

Zihou is a minimal Discord bot that joins your current voice channel and plays an hourly chime using local MP3 files. It does not auto-move between voice channels. Commands are provided as hybrid commands (slash and prefix).

- Commands: `/start`, `/stop`
- Audio files: `audio/1.mp3` to `audio/24.mp3` (0:00 uses `24.mp3`)
- Requires FFmpeg available on the system PATH

Looking for Japanese docs? See `README_JP.md`.

## Features
- Join the caller’s current VC with `/start` and stay there until `/stop`.
- Play the matching hourly chime at every top of the hour.
  - Skips if the bot is not connected or is already playing audio.
- Never auto-moves to another VC (explicit by design).

## Requirements
- Python 3.11+ (tested with 3.12)
- FFmpeg installed and accessible from the command line (`ffmpeg -version`)
- Discord Bot token

Python dependencies are listed in `requirements.txt` (notably `discord.py==2.6.3`).

## Setup
1) Create the `audio` folder at the project root and put these files inside:
   - `1.mp3` … `24.mp3` where `24.mp3` will be used for 0:00.
2) Create a Discord Application and Bot, then invite it to your server with permissions:
   - Connect, Speak (and optionally Move Members, though the bot does not auto-move)
3) Provide environment variables (via a `.env` file or system envs):
   - `TOKEN`: your bot token
   - `PREFIX` (optional): prefix for message commands, e.g. `!`
   - `INVITE_LINK` (optional): used for embeds or messages

Install dependencies:

```
python -m pip install -r requirements.txt
```

Start the bot:

```
python bot.py
```

## Usage
- Join your target VC, then run `/start` (or `start` if you enabled message commands). The bot will join and begin playing the chime at the next hour.
- To make it leave, run `/stop`.
- If the bot is already connected to another VC in the same guild, it will not move. Use `/stop` first, then run `/start` in the desired VC.

## Docker
A `docker-compose.yml` is provided. After installing Docker, you can run:

```
docker compose up -d --build
```

Notes:
- Mount your `audio` folder into the container if you keep MP3s outside the image.
- Provide environment variables via an `.env` file or Compose `env_file`/`environment`.
- Ensure FFmpeg is available inside the image if you customize the Dockerfile.

## Troubleshooting
- “FFmpeg initialization failed”: Ensure FFmpeg is installed and on PATH. Verify with `ffmpeg -version`.
- “Audio file not found”: Check that `audio/1.mp3 … 24.mp3` exist and the bot’s working directory is the project root.
- “Bot doesn’t join”: Verify the bot has Connect and Speak permissions in that VC.
- “No hourly sound”: The bot only plays at the top of each hour and skips while already playing.

## Acknowledgements
This project started from the excellent `kkrypt0nn/Python-Discord-Bot-Template` and was adapted for a simple hourly-chime use case.

## License
Apache License 2.0 — see [`LICENSE.md`](LICENSE.md).
