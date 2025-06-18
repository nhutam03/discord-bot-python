import discord
from discord.ext import commands
import wavelink
import asyncio
import logging
from typing import Optional, Dict, List
import yt_dlp

logger = logging.getLogger(__name__)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: Dict[int, List[wavelink.Track]] = {}
        self.now_playing: Dict[int, wavelink.Track] = {}
        
        # Configure yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        self.ydl = yt_dlp.YoutubeDL(ydl_opts)
        
        # Start node connection
        self.bot.loop.create_task(self.connect_nodes())
    
    async def connect_nodes(self):
        """Connect to Lavalink nodes."""
        await self.bot.wait_until_ready()
        
        node = wavelink.Node(
            uri='http://localhost:2333',  # Lavalink server address
            password='youshallnotpass'    # Lavalink server password
        )
        
        try:
            await wavelink.NodePool.connect(client=self.bot, nodes=[node])
            logger.info('✅ Connected to Lavalink node')
        except Exception as e:
            logger.error(f'❌ Failed to connect to Lavalink node: {e}')
    
    def get_queue(self, guild_id: int) -> List[wavelink.Track]:
        """Get the queue for a guild."""
        return self.queues.get(guild_id, [])
    
    def add_to_queue(self, guild_id: int, track: wavelink.Track):
        """Add a track to the queue."""
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        self.queues[guild_id].append(track)
    
    async def play_next(self, guild_id: int):
        """Play the next track in the queue."""
        queue = self.get_queue(guild_id)
        if not queue:
            return
        
        track = queue.pop(0)
        self.now_playing[guild_id] = track
        
        # Get the voice client
        voice_client = wavelink.NodePool.get_node().get_player(guild_id)
        if not voice_client:
            return
        
        await voice_client.play(track)
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Play a song or add it to the queue."""
        if not ctx.author.voice:
            return await ctx.send('❌ Bạn cần vào voice channel trước!')
        
        # Connect to voice channel if not already connected
        if not ctx.voice_client:
            await ctx.author.voice.channel.connect(cls=wavelink.Player)
        
        # Search for the track
        try:
            tracks = await wavelink.NodePool.get_node().get_tracks(query)
            if not tracks:
                return await ctx.send('❌ Không tìm thấy bài hát!')
            
            track = tracks[0]
            
            # Add to queue
            self.add_to_queue(ctx.guild.id, track)
            
            # If nothing is playing, start playing
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx.guild.id)
                await ctx.send(f'🎵 Đang phát: **{track.title}**')
            else:
                await ctx.send(f'✅ Đã thêm vào queue: **{track.title}**')
                
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
        
        await ctx.voice_client.stop()
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
        await ctx.voice_client.stop()
        await ctx.send('⏹️ Đã dừng phát nhạc và xóa queue!')
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pause the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_playing():
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        await ctx.voice_client.pause()
        await ctx.send('⏸️ Đã tạm dừng bài hát!')
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resume the current song."""
        if not ctx.voice_client:
            return await ctx.send('❌ Bot không đang phát nhạc!')
        
        if not ctx.voice_client.is_paused():
            return await ctx.send('❌ Bài hát không đang tạm dừng!')
        
        await ctx.voice_client.resume()
        await ctx.send('▶️ Đã tiếp tục phát bài hát!')
    
    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Show the current queue."""
        queue = self.get_queue(ctx.guild.id)
        if not queue:
            return await ctx.send('📋 Queue trống!')
        
        # Create queue message
        message = ['📋 **Queue hiện tại:**']
        for i, track in enumerate(queue, 1):
            message.append(f'{i}. {track.title}')
        
        await ctx.send('\n'.join(message))
    
    @commands.command(name='nowplaying', aliases=['np'])
    async def now_playing(self, ctx):
        """Show the currently playing song."""
        track = self.now_playing.get(ctx.guild.id)
        if not track:
            return await ctx.send('❌ Không có bài hát nào đang phát!')
        
        await ctx.send(f'🎵 Đang phát: **{track.title}**')
    
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