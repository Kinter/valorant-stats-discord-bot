import discord
from discord import app_commands
from discord.ext import commands
from core.config import GUILD_ID

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="명령동기화", description="모든 서버의 슬래시 명령을 다시 동기화합니다 (관리자 전용).")
    async def resync(self, inter: discord.Interaction):
        app = await self.bot.application_info()
        if inter.user.id != app.owner.id:
            await inter.response.send_message("권한이 없습니다.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            global_synced = await self.bot.tree.sync()

            target_guild_ids = {guild.id for guild in self.bot.guilds}
            if GUILD_ID:
                target_guild_ids.add(GUILD_ID)

            responses = [f"Global: {len(global_synced)} commands"]
            for gid in sorted(target_guild_ids):
                guild_obj = discord.Object(id=gid)
                self.bot.tree.copy_global_to(guild=guild_obj)
                guild_synced = await self.bot.tree.sync(guild=guild_obj)
                responses.append(f"Guild {gid}: {len(guild_synced)} commands")

            await inter.followup.send("\n".join(responses), ephemeral=True)
        except Exception as e:
            await inter.followup.send(f"Resync error: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
