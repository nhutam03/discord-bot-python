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
        
    def get_cookies_file(self) -> str:
        """Get current cookies file path."""
        if not os.path.exists(self.cookies_file):
            raise FileNotFoundError("cookies.txt file not found. Please create it with valid YouTube cookies.")
        return self.cookies_file

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
                try:
                    info = ydl.extract_info(song['url'], download=False)
                    url = info['url']
                except Exception as e:
                    logger.error(f"❌ Error extracting info: {e}")
                    # If it's a SoundCloud URL, try to get a different format
                    if 'soundcloud.com' in song['url']:
                        try:
                            # Try to get a different format
                            info = ydl.extract_info(song['url'], download=False, format='bestaudio/best')
                            url = info['url']
                        except Exception as e2:
                            logger.error(f"❌ Error getting alternative format: {e2}")
                            await ctx.send("❌ Không thể phát bài hát này. Đang chuyển sang bài tiếp theo...")
                            await self.play_next(ctx)
                            return
                    else:
                        await ctx.send("❌ Không thể phát bài hát này. Đang chuyển sang bài tiếp theo...")
                        await self.play_next(ctx)
                        return
                
            # Enhanced audio processing options with better error handling
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
            
            # Add error handling for the play command
            def after_playing(error):
                if error:
                    logger.error(f"❌ Error in after_playing: {error}")
                    asyncio.run_coroutine_threadsafe(
                        self.handle_play_error(ctx, error), self.bot.loop
                    )
                else:
                    asyncio.run_coroutine_threadsafe(
                        self.play_next(ctx), self.bot.loop
                    )
            
            voice_client.play(
                discord.FFmpegPCMAudio(url, **ffmpeg_options),
                after=after_playing
            )
            
            # Create now playing embed
            embed = discord.Embed(
                title='🎵 Đang phát',
                description=f'**{song["title"]}**',
                color=discord.Color.blue()
            )
            
            if song.get('thumbnail'):
                embed.set_thumbnail(url=song['thumbnail'])
                
            if song.get('duration'):
                duration = str(timedelta(seconds=song['duration']))
                embed.add_field(
                    name='⏱️ Thời lượng',
                    value=duration,
                    inline=True
                )
            
            # Add queue info
            if queue:
                embed.add_field(
                    name='📋 Queue',
                    value=f'Còn {len(queue)} bài hát trong queue',
                    inline=True
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f'❌ Error playing song: {e}')
            await self.handle_play_error(ctx, e)
    
    async def handle_play_error(self, ctx, error):
        """Handle play errors and attempt recovery."""
        try:
            # If the error is related to streaming, try to skip to next song
            if "403" in str(error) or "Forbidden" in str(error):
                await ctx.send("❌ Lỗi khi phát bài hát. Đang chuyển sang bài tiếp theo...")
            else:
                await ctx.send(f"❌ Có lỗi xảy ra khi phát bài hát: {str(error)}")
            
            # Stop current playback
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            
            # Try to play next song
            await self.play_next(ctx)
        except Exception as e:
            logger.error(f"❌ Error in handle_play_error: {e}")
            await ctx.send("❌ Có lỗi xảy ra khi xử lý lỗi phát nhạc!")
    
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
        """Get all songs from a YouTube playlist or video, always fetch full info for each entry."""
        try:
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
                songs = []
                if 'entries' in info:
                    for entry in info['entries']:
                        if not entry:
                            continue
                        # Nếu entry chưa có đủ thông tin, lấy lại bằng id
                        if not entry.get('title') or not entry.get('url'):
                            video_id = entry.get('id')
                            if video_id:
                                try:
                                    video_info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
                                    songs.append({
                                        'title': video_info.get('title', 'Unknown Title'),
                                        'url': video_info.get('url', ''),
                                        'duration': video_info.get('duration', 0),
                                        'thumbnail': video_info.get('thumbnail', '')
                                    })
                                except Exception as e:
                                    logger.error(f"❌ Error fetching video info for {video_id}: {e}")
                                    continue
                        else:
                            songs.append({
                                'title': entry.get('title', 'Unknown Title'),
                                'url': entry.get('url', ''),
                                'duration': entry.get('duration', 0),
                                'thumbnail': entry.get('thumbnail', '')
                            })
                    return songs
                # Nếu là 1 video
                return [{
                    'title': info.get('title', 'Unknown Title'),
                    'url': info.get('url', ''),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', '')
                }]
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
        """Get track information from Spotify playlist/album URL, handle missing album field and always get thumbnail safely."""
        if not self.spotify:
            return []
        try:
            clean_url = url.split('?')[0]
            playlist_id = clean_url.split('/')[-1]
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
                # Lấy thumbnail an toàn
                album_info = track.get('album', {}) if isinstance(track.get('album'), dict) else {}
                images = album_info.get('images', [])
                thumbnail = images[0]['url'] if images else ''
                # Search on YouTube
                search_query = f"{artist} - {title} audio"
                with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                    try:
                        info = ydl.extract_info(f"ytsearch:{search_query}", download=False)['entries'][0]
                        songs.append({
                            'title': f"{artist} - {title}",
                            'url': info['url'],
                            'duration': track.get('duration_ms', 0) // 1000,
                            'thumbnail': thumbnail
                        })
                    except Exception as e:
                        logger.error(f"❌ Error getting track info for {title}: {e}")
                        continue
            return songs
        except Exception as e:
            logger.error(f"❌ Error getting Spotify playlist info: {e}")
            return []

    async def get_soundcloud_playlist(self, url: str) -> List[dict]:
        """Get all songs from a SoundCloud playlist, always fetch full info for each entry if missing."""
        try:
            # Clean up URL by removing query parameters
            clean_url = url.split('?')[0]
            
            with yt_dlp.YoutubeDL(self.get_ydl_opts()) as ydl:
                # First get the playlist info
                playlist = ydl.extract_info(clean_url, download=False)
                songs = []
                
                if 'entries' in playlist:
                    for entry in playlist['entries']:
                        if not entry:
                            continue
                            
                        try:
                            # Get the track URL
                            track_url = entry.get('webpage_url') or entry.get('url')
                            if not track_url:
                                continue
                                
                            # Get full track info
                            track_info = ydl.extract_info(track_url, download=False)
                            
                            songs.append({
                                'title': track_info.get('title', 'Unknown Title'),
                                'url': track_info.get('url', ''),
                                'duration': track_info.get('duration', 0),
                                'thumbnail': track_info.get('thumbnail', '')
                            })
                        except Exception as e:
                            logger.error(f"❌ Error fetching SoundCloud track info: {e}")
                            continue
                            
                    return songs
                    
                # If it's a single track
                return [{
                    'title': playlist.get('title', 'Unknown Title'),
                    'url': playlist.get('url', ''),
                    'duration': playlist.get('duration', 0),
                    'thumbnail': playlist.get('thumbnail', '')
                }]
                
        except Exception as e:
            logger.error(f"❌ Error getting SoundCloud playlist: {e}")
            return []
    
    @commands.hybrid_command(name='play', description='Phát nhạc từ YouTube, Spotify hoặc SoundCloud', aliases=['p'])
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
                    embed = discord.Embed(
                        title='✅ Đã thêm playlist vào queue',
                        description=f'Đã thêm {len(songs)} bài hát vào queue',
                        color=discord.Color.green()
                    )
                    # Add first few songs as preview
                    preview = []
                    for i, song in enumerate(songs[:5], 1):
                        preview.append(f'{i}. {song["title"]}')
                    if len(songs) > 5:
                        preview.append(f'... và {len(songs) - 5} bài hát khác')
                    embed.add_field(
                        name='📝 Preview',
                        value='\n'.join(preview),
                        inline=False
                    )
                    await ctx.send(embed=embed)
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
                embed = discord.Embed(
                    title='✅ Đã thêm vào queue',
                    description=f'**{song["title"]}**',
                    color=discord.Color.green()
                )
                if song.get('thumbnail'):
                    embed.set_thumbnail(url=song['thumbnail'])
                if song.get('duration'):
                    duration = str(timedelta(seconds=song['duration']))
                    embed.add_field(
                        name='⏱️ Thời lượng',
                        value=duration,
                        inline=True
                    )
                # Add queue position
                queue = self.get_queue(ctx.guild.id)
                position = len(queue)
                embed.add_field(
                    name='📋 Vị trí trong queue',
                    value=f'#{position}',
                    inline=True
                )
                await ctx.send(embed=embed)
                
        except Exception as e:
            logger.error(f'❌ Error in play command: {e}')
            await ctx.send('❌ Có lỗi xảy ra khi tìm kiếm bài hát!')
    
    @commands.hybrid_command(name='skip', description='Bỏ qua bài hát hiện tại', aliases=['s'])
    async def skip(self, ctx):
        """Skip the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_playing():
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        ctx.voice_client.stop()
        embed = discord.Embed(
            title='⏭️ Đã skip bài hát',
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='stop', description='Dừng phát nhạc và xóa queue', aliases=['st'])
    async def stop(self, ctx):
        """Stop playing and clear the queue."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        # Clear queue
        self.queues[ctx.guild.id] = []
        self.now_playing.pop(ctx.guild.id, None)
        
        # Stop playing
        ctx.voice_client.stop()
        embed = discord.Embed(
            title='⏹️ Đã dừng phát nhạc',
            description='Queue đã được xóa',
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='pause', description='Tạm dừng bài hát đang phát', aliases=['pa'])
    async def pause(self, ctx):
        """Pause the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_playing():
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        ctx.voice_client.pause()
        embed = discord.Embed(
            title='⏸️ Đã tạm dừng bài hát',
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='resume', description='Tiếp tục phát bài hát', aliases=['r'])
    async def resume(self, ctx):
        """Resume the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_paused():
            return await ctx.send('❌ Bài hát không đang tạm dừng!')
        
        ctx.voice_client.resume()
        embed = discord.Embed(
            title='▶️ Đã tiếp tục phát bài hát',
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='queue', description='Hiển thị queue hiện tại', aliases=['q'])
    async def queue(self, ctx):
        """Show the current queue."""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return await ctx.send('📋 Queue trống!')
        
        # Create queue embed
        embed = discord.Embed(
            title='📋 Queue hiện tại',
            color=discord.Color.blue()
        )
        
        # Add current song if playing
        current_song = self.now_playing.get(ctx.guild.id)
        if current_song:
            embed.add_field(
                name='🎵 Đang phát',
                value=f'**{current_song["title"]}**',
                inline=False
            )
        
        # Add queue songs
        queue_text = []
        for i, song in enumerate(queue[:10], 1):
            duration = str(timedelta(seconds=song.get('duration', 0)))
            queue_text.append(f'{i}. {song["title"]} `[{duration}]`')
        
        if len(queue) > 10:
            queue_text.append(f'\n... và {len(queue) - 10} bài hát khác')
        
        embed.add_field(
            name='📝 Queue',
            value='\n'.join(queue_text),
            inline=False
        )
        
        # Add total duration
        total_duration = sum(song.get('duration', 0) for song in queue)
        if total_duration > 0:
            embed.set_footer(text=f'Tổng thời lượng: {str(timedelta(seconds=total_duration))}')
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='nowplaying', description='Hiển thị bài hát đang phát', aliases=['np'])
    async def now_playing(self, ctx):
        """Show the currently playing song."""
        song = self.now_playing.get(ctx.guild.id)
        if not song:
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        embed = discord.Embed(
            title='🎵 Đang phát',
            description=f'**{song["title"]}**',
            color=discord.Color.blue()
        )
        
        if song.get('thumbnail'):
            embed.set_thumbnail(url=song['thumbnail'])
            
        if song.get('duration'):
            duration = str(timedelta(seconds=song['duration']))
            embed.add_field(
                name='⏱️ Thời lượng',
                value=duration,
                inline=True
            )
        
        # Add queue info
        queue = self.get_queue(ctx.guild.id)
        if queue:
            embed.add_field(
                name='📋 Queue',
                value=f'Còn {len(queue)} bài hát trong queue',
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='leave', description='Rời voice channel', aliases=['disconnect', 'dc'])
    async def leave(self, ctx):
        """Leave the voice channel."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang trong voice channel!')
        
        # Clear queue and now playing
        self.queues.pop(ctx.guild.id, None)
        self.now_playing.pop(ctx.guild.id, None)
        
        # Disconnect
        await ctx.voice_client.disconnect()
        embed = discord.Embed(
            title='👋 Đã rời voice channel',
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot)) 