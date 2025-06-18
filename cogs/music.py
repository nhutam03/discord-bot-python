import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional, Dict, List
import yt_dlp
import os
import json
import time
from datetime import datetime, timedelta
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re

logger = logging.getLogger(__name__)

class CookieManager:
    def __init__(self):
        self.cookies_file = 'cookies.txt'
        self.last_update = None
        self.update_interval = timedelta(hours=6)  # Update every 6 hours
        
    def get_cookies_file(self) -> str:
        """Get current cookies file path."""
        if not os.path.exists(self.cookies_file):
            raise FileNotFoundError("cookies.txt file not found. Please create it with valid YouTube cookies.")
            
        if self.should_update():
            self.update_cookies()
        return self.cookies_file
    
    def should_update(self) -> bool:
        """Check if cookies need to be updated."""
        if not self.last_update:
            return True
        return datetime.now() - self.last_update > self.update_interval
    
    def update_cookies(self):
        """Update cookies file using YouTube API."""
        try:
            # Use yt-dlp to get fresh cookies
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'cookiefile': self.cookies_file,
                'cookiesfrombrowser': ('chrome',),  # Try to get cookies from Chrome
                'cookiesfrombrowser': ('firefox',),  # Try to get cookies from Firefox
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Try to access a public video to get cookies
                ydl.extract_info('https://www.youtube.com/watch?v=dQw4w9WgXcQ', download=False)
                self.last_update = datetime.now()
                logger.info("✅ Cookies updated successfully")
        except Exception as e:
            logger.error(f"❌ Error updating cookies: {e}")
            # If update fails, continue using existing cookies file
            if not os.path.exists(self.cookies_file):
                raise FileNotFoundError("cookies.txt file not found and could not be created automatically. Please create it manually with valid YouTube cookies.")

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.now_playing: Dict[int, dict] = {}
        self.cookie_manager = CookieManager()
        
        # Configure yt-dlp with improved audio quality
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': False,  # Enable playlist support
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',  # Maximum quality
            }],
            'postprocessor_args': [
                '-ar', '48000',     # Set sample rate to 48kHz
                '-ac', '2',         # Set to stereo
                '-b:a', '320k',     # Set bitrate to 320kbps
                '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11',  # Normalize audio levels
            ],
        }
        self.ydl = yt_dlp.YoutubeDL(self.ydl_opts)
        
        # Initialize Spotify client
        try:
            self.spotify = spotipy.Spotify(
                client_credentials_manager=SpotifyClientCredentials(
                    client_id=os.getenv('SPOTIFY_CLIENT_ID'),
                    client_secret=os.getenv('SPOTIFY_CLIENT_SECRET')
                )
            )
            logger.info("✅ Spotify client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing Spotify client: {e}")
            self.spotify = None
    
    def get_ydl_opts(self):
        """Get yt-dlp options with current cookies file."""
        opts = self.ydl_opts.copy()
        opts['cookiefile'] = self.cookie_manager.get_cookies_file()
        return opts
    
    def get_queue(self, guild_id: int) -> List[dict]:
        """Get the queue for a guild."""
        return self.queues.get(guild_id, [])
    
    def add_to_queue(self, guild_id: int, song: dict):
        """Add a song to the queue."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        self.queues[guild_id].append(song)
    
    async def play_next(self, ctx):
        """Play the next song in the queue."""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return
        
        song = queue.pop(0)
        self.now_playing[ctx.guild.id] = song
        
        # Get the voice client
        voice_client = ctx.voice_client
        if not voice_client:
            return
        
        try:
            # Download and play the song with current cookies
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                info = ydl.extract_info(song['url'], download=False)
                url = info['url']
                
            # Enhanced audio processing options
            ffmpeg_options = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': (
                    '-vn '  # Disable video
                    '-af "'
                    'volume=2.0,'  # Increase volume
                    'loudnorm=I=-16:TP=-1.5:LRA=11,'  # Normalize audio levels
                    'equalizer=f=1000:width_type=h:width=200:g=3,'  # Boost mid frequencies
                    'equalizer=f=3000:width_type=h:width=200:g=2,'  # Boost high-mid frequencies
                    'equalizer=f=8000:width_type=h:width=200:g=1,'  # Slight boost to high frequencies
                    'aresample=48000,'  # Resample to 48kHz
                    'aformat=sample_fmts=s16:channel_layouts=stereo'  # Ensure stereo output
                    '" '
                    '-ar 48000 '  # Set sample rate
                    '-ac 2 '      # Set to stereo
                    '-b:a 320k'   # Set bitrate
                )
            }
            
            voice_client.play(
                discord.FFmpegPCMAudio(url, **ffmpeg_options),
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.play_next(ctx), self.bot.loop
                )
            )
            
            await ctx.send(f'🎵 Đang phát: **{song["title"]}**')
            
        except Exception as e:
            logger.error(f'❌ Error playing song: {e}')
            await ctx.send('❌ Có lỗi xảy ra khi phát bài hát!')
            await self.play_next(ctx)
    
    def is_youtube_url(self, url: str) -> bool:
        """Check if the URL is a YouTube URL."""
        return bool(re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/', url))
    
    def is_spotify_url(self, url: str) -> bool:
        """Check if the URL is a Spotify URL."""
        return bool(re.match(r'^https?://(?:open\.)?spotify\.com/(?:track|album|playlist|artist)/[a-zA-Z0-9]+', url))
    
    def is_soundcloud_url(self, url: str) -> bool:
        """Check if the URL is a SoundCloud URL."""
        return bool(re.match(r'^https?://(?:www\.)?soundcloud\.com/[\w-]+/[\w-]+', url))
    
    def is_playlist_url(self, url: str) -> bool:
        """Check if the URL is a playlist URL."""
        # Clean up URL by removing query parameters
        clean_url = url.split('?')[0]
        
        # Check for YouTube playlist
        if 'youtube.com/playlist' in clean_url or 'youtu.be/playlist' in clean_url:
            return True
            
        # Check for Spotify playlist/album
        if 'spotify.com/playlist' in clean_url or 'spotify.com/album' in clean_url:
            return True
            
        # Check for SoundCloud playlist (sets)
        if 'soundcloud.com' in clean_url and ('/sets/' in clean_url or '?si=' in url):
            return True
            
        return False

    async def get_youtube_playlist(self, url: str) -> List[dict]:
        """Get all songs from a YouTube playlist or video."""
        try:
            # Clean up the URL by removing query parameters
            clean_url = url.split('?')[0]
            
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                try:
                    # First try to get playlist/video info
                    info = ydl.extract_info(clean_url, download=False)
                    
                    # Check if it's a playlist
                    if 'entries' in info:
                        return [{
                            'title': entry['title'],
                            'url': entry['url'],
                            'duration': entry.get('duration', 0),
                            'thumbnail': entry.get('thumbnail', '')
                        } for entry in info['entries']]
                    
                    # If it's a single video, return it as a single-item playlist
                    return [{
                        'title': info['title'],
                        'url': info['url'],
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', '')
                    }]
                    
                except Exception as e:
                    logger.error(f"❌ Error extracting YouTube info: {e}")
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Error getting YouTube playlist: {e}")
            return []

    async def get_spotify_track_info(self, url: str) -> Optional[dict]:
        """Get track information from Spotify URL."""
        if not self.spotify:
            return None
            
        try:
            # Extract track ID from URL
            track_id = url.split('/')[-1].split('?')[0]
            track = self.spotify.track(track_id)
            
            # Get artist and title
            artist = track['artists'][0]['name']
            title = track['name']
            
            # Search on YouTube
            search_query = f"{artist} - {title} audio"
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                info = ydl.extract_info(f"ytsearch:{search_query}", download=False)['entries'][0]
                
            return {
                'title': f"{artist} - {title}",
                'url': info['url'],
                'duration': track['duration_ms'] // 1000,
                'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else ''
            }
        except Exception as e:
            logger.error(f"❌ Error getting Spotify track info: {e}")
            return None
    
    async def get_spotify_playlist_info(self, url: str) -> List[dict]:
        """Get track information from Spotify playlist/album URL."""
        if not self.spotify:
            return []
            
        try:
            # Clean up the URL by removing query parameters
            clean_url = url.split('?')[0]
            
            # Extract playlist/album ID from URL
            playlist_id = clean_url.split('/')[-1]
            
            # Check if it's a playlist or album
            if 'playlist' in clean_url:
                playlist = self.spotify.playlist(playlist_id)
                tracks = playlist['tracks']['items']
            else:  # album
                album = self.spotify.album(playlist_id)
                tracks = album['tracks']['items']
            
            songs = []
            for item in tracks:
                track = item['track'] if 'track' in item else item
                artist = track['artists'][0]['name']
                title = track['name']
                
                # Search on YouTube
                search_query = f"{artist} - {title} audio"
                with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                    try:
                        info = ydl.extract_info(f"ytsearch:{search_query}", download=False)['entries'][0]
                        songs.append({
                            'title': f"{artist} - {title}",
                            'url': info['url'],
                            'duration': track['duration_ms'] // 1000,
                            'thumbnail': track['album']['images'][0]['url'] if track['album']['images'] else ''
                        })
                    except Exception as e:
                        logger.error(f"❌ Error getting track info for {title}: {e}")
                        continue
                        
            return songs
        except Exception as e:
            logger.error(f"❌ Error getting Spotify playlist info: {e}")
            return []

    async def get_soundcloud_playlist(self, url: str) -> List[dict]:
        """Get all songs from a SoundCloud playlist."""
        try:
            # Clean up the URL by removing query parameters
            clean_url = url.split('?')[0]
            
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                try:
                    # First try to get playlist info
                    playlist = ydl.extract_info(clean_url, download=False)
                    
                    # Check if it's a playlist
                    if 'entries' in playlist:
                        return [{
                            'title': entry['title'],
                            'url': entry['url'],
                            'duration': entry.get('duration', 0),
                            'thumbnail': entry.get('thumbnail', '')
                        } for entry in playlist['entries']]
                    
                    # If it's a single track, return it as a single-item playlist
                    return [{
                        'title': playlist['title'],
                        'url': playlist['url'],
                        'duration': playlist.get('duration', 0),
                        'thumbnail': playlist.get('thumbnail', '')
                    }]
                    
                except Exception as e:
                    logger.error(f"❌ Error extracting SoundCloud info: {e}")
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Error getting SoundCloud playlist: {e}")
            return []
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue."""
        if not ctx.author.voice:
            return await ctx.send('❌ Bạn cần vào voice channel trước!')
        
        # Connect to voice channel if not already connected
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        
        try:
            # Check if it's a playlist URL
            if self.is_playlist_url(query):
                await ctx.send('⏳ Đang tải playlist...')
                songs = []
                
                if self.is_youtube_url(query):
                    songs = await self.get_youtube_playlist(query)
                elif self.is_spotify_url(query):
                    songs = await self.get_spotify_playlist_info(query)
                elif self.is_soundcloud_url(query):
                    songs = await self.get_soundcloud_playlist(query)
                
                if not songs:
                    return await ctx.send('❌ Không thể tải playlist!')
                
                # Add all songs to queue
                for song in songs:
                    self.add_to_queue(ctx.guild.id, song)
                
                # If nothing is playing, start playing
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                else:
                    await ctx.send(f'✅ Đã thêm {len(songs)} bài hát vào queue!')
                return

            # Check if it's a Spotify URL
            if self.is_spotify_url(query):
                song = await self.get_spotify_track_info(query)
                if not song:
                    return await ctx.send('❌ Không thể lấy thông tin bài hát từ Spotify!')
            # Check if it's a SoundCloud URL
            elif self.is_soundcloud_url(query):
                songs = await self.get_soundcloud_playlist(query)
                if not songs:
                    return await ctx.send('❌ Không thể lấy thông tin bài hát từ SoundCloud!')
                song = songs[0]  # Get the first song if it's a single track
            # Check if it's a YouTube URL
            elif self.is_youtube_url(query):
                songs = await self.get_youtube_playlist(query)
                if not songs:
                    return await ctx.send('❌ Không thể lấy thông tin bài hát từ YouTube!')
                song = songs[0]  # Get the first song if it's a single video
            else:
                # Search for the song with current cookies
                with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                    try:
                        # Try to extract info directly if it's a URL
                        info = ydl.extract_info(query, download=False)
                    except:
                        # If not a URL, search for it
                        info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                    
                    song = {
                        'title': info['title'],
                        'url': info['url'],
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', '')
                    }
            
            # Add to queue
            self.add_to_queue(ctx.guild.id, song)
            
            # If nothing is playing, start playing
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx)
            else:
                await ctx.send(f'✅ Đã thêm vào queue: **{song["title"]}**')
                
        except Exception as e:
            logger.error(f'❌ Error in play command: {e}')
            await ctx.send('❌ Có lỗi xảy ra khi tìm kiếm bài hát!')
    
    @commands.command(name='skip', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_playing():
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        ctx.voice_client.stop()
        await ctx.send('⏭️ Đã skip bài hát hiện tại!')
    
    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stop playing and clear the queue."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        # Clear queue
        self.queues[ctx.guild.id] = []
        self.now_playing.pop(ctx.guild.id, None)
        
        # Stop playing
        ctx.voice_client.stop()
        await ctx.send('⏹️ Đã dừng phát nhạc và xóa queue!')
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_playing():
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        ctx.voice_client.pause()
        await ctx.send('⏸️ Đã tạm dừng bài hát!')
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_paused():
            return await ctx.send('❌ Bài hát không đang tạm dừng!')
        
        ctx.voice_client.resume()
        await ctx.send('▶️ Đã tiếp tục phát bài hát!')
    
    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Show the current queue."""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return await ctx.send('📋 Queue trống!')
        
        # Create queue message
        message = ['📋 **Queue hiện tại:**']
        for i, song in enumerate(queue, 1):
            message.append(f'{i}. {song["title"]}')
        
        await ctx.send('\n'.join(message))
    
    @commands.command(name='nowplaying', aliases=['np'])
    async def now_playing(self, ctx):
        """Show the currently playing song."""
        song = self.now_playing.get(ctx.guild.id)
        if not song:
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        await ctx.send(f'🎵 Đang phát: **{song["title"]}**')
    
    @commands.command(name='leave', aliases=['disconnect'])
    async def leave(self, ctx):
        """Leave the voice channel."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang trong voice channel!')
        
        # Clear queue and now playing
        self.queues.pop(ctx.guild.id, None)
        self.now_playing.pop(ctx.guild.id, None)
        
        # Disconnect
        await ctx.voice_client.disconnect()
        await ctx.send('👋 Đã rời voice channel!')

async def setup(bot):
    await bot.add_cog(Music(bot)) 