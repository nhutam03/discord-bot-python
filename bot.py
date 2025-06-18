import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import logging
import asyncio
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix='t',
            intents=intents,
            help_command=None
        )
        
        self.queues = {}  # Store queues for each guild
        
    async def setup_hook(self):
        # Load all cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f'✅ Loaded extension: {filename}')
                except Exception as e:
                    logger.error(f'❌ Failed to load extension {filename}: {e}')
    
    async def on_ready(self):
        logger.info(f'🚀 Bot is ready! Logged in as {self.user.name}')
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name='Đang phục vụ server!'
            )
        )
    
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        
        error_message = 'Có lỗi xảy ra khi thực hiện lệnh này!'
        logger.error(f'❌ Error executing command: {error}')
        
        try:
            await ctx.send(error_message)
        except discord.HTTPException as e:
            logger.error(f'❌ Error sending error message: {e}')

async def main():
    bot = MusicBot()
    
    try:
        await bot.start(os.getenv('YOUR_BOT_TOKEN'))
    except Exception as e:
        logger.error(f'❌ Error starting bot: {e}')

if __name__ == '__main__':
    asyncio.run(main()) 