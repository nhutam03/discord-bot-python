A Discord music bot built with Python using discord.py and wavelink.

## Features

- 🎵 Play music from YouTube
- 📋 Queue management
- ⏯️ Playback controls (play, pause, resume, skip, stop)
- 🎧 Voice channel management
- 📝 Command help system

## Requirements

- Python 3.8 or higher
- Lavalink server
- FFmpeg

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd discord-music-bot
```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Set up Lavalink server:
   - Download the latest Lavalink.jar from [GitHub](https://github.com/freyacodes/Lavalink/releases)
   - Create an `application.yml` file with the following content:
   ```yaml
   server:
     port: 2333
     address: 127.0.0.1
   lavalink:
     server:
       password: "youshallnotpass"
       sources:
         youtube: true
         bandcamp: true
         soundcloud: true
         twitch: true
         vimeo: true
         http: true
       bufferDurationMs: 400
       youtubePlaylistLoadLimit: 6
       playerUpdateInterval: 5
       youtubeSearchEnabled: true
       soundcloudSearchEnabled: true
   ```

4. Create a `.env` file:
```env
YOUR_BOT_TOKEN=your_discord_bot_token_here
```

5. Start the Lavalink server:
```bash
java -jar Lavalink.jar
```

6. Run the bot:
```bash
python bot.py
```

## Commands

- `tplay <query>` - Play a song or add to queue
- `tskip` - Skip the current song
- `tstop` - Stop playing and clear queue
- `tpause` - Pause the current song
- `tresume` - Resume the current song
- `tqueue` - Show the current queue
- `tnowplaying` - Show the currently playing song
- `tleave` - Leave the voice channel
- `thelp` - Show all available commands
- `tping` - Check bot latency

## Contributing

Feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details.