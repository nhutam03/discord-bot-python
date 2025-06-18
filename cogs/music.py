import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional, Dict, List
import yt_dlp
import os
import json

logger = logging.getLogger(__name__)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: Dict[int, List[dict]] = {}
        self.now_playing: Dict[int, dict] = {}
        
        # Configure yt-dlp
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'cookiesfrombrowser': ('chrome',),  # Use Chrome cookies
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        self.ydl = yt_dlp.YoutubeDL(self.ydl_opts)
    
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
            # Download and play the song
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(song['url'], download=False)
                url = info['url']
                
            voice_client.play(
                discord.FFmpegPCMAudio(url, **{
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn'
                }),
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.play_next(ctx), self.bot.loop
                )
            )
            
            await ctx.send(f'🎵 Đang phát: **{song["title"]}**')
            
        except Exception as e:
            logger.error(f'❌ Error playing song: {e}')
            await ctx.send('❌ Có lỗi xảy ra khi phát bài hát!')
            await self.play_next(ctx)
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue."""
        if not ctx.author.voice:
            return await ctx.send('❌ Bạn cần vào voice channel trước!')
        
        # Connect to voice channel if not already connected
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect()
        
        try:
            # Search for the song
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
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