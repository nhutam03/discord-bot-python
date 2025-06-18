import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='help', description='Hiển thị danh sách các lệnh có sẵn')
    async def help(self, ctx):
        """Show all available commands."""
        embed = discord.Embed(
            title='🎵 Music Bot Commands',
            description='Dưới đây là các lệnh bạn có thể sử dụng:\n\n**Cách sử dụng:**\n• Slash commands: `/help`\n• Prefix commands: `thelp`',
            color=discord.Color.blue()
        )
        
        # Music commands
        music_commands = [
            ('play <query>', 'Phát một bài hát hoặc thêm vào queue'),
            ('skip', 'Bỏ qua bài hát hiện tại'),
            ('stop', 'Dừng phát nhạc và xóa queue'),
            ('pause', 'Tạm dừng bài hát'),
            ('resume', 'Tiếp tục phát bài hát'),
            ('queue', 'Hiển thị queue hiện tại'),
            ('nowplaying', 'Hiển thị bài hát đang phát'),
            ('leave', 'Rời voice channel')
        ]
        
        embed.add_field(
            name='🎵 Music Commands',
            value='\n'.join(f'`{cmd}` - {desc}' for cmd, desc in music_commands),
            inline=False
        )
        
        # Other commands
        other_commands = [
            ('help', 'Hiển thị danh sách lệnh'),
            ('ping', 'Kiểm tra độ trễ của bot')
        ]
        
        embed.add_field(
            name='📝 Other Commands',
            value='\n'.join(f'`{cmd}` - {desc}' for cmd, desc in other_commands),
            inline=False
        )
        
        # Add footer with supported platforms
        embed.set_footer(text='Hỗ trợ: YouTube, Spotify, SoundCloud')
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot)) 