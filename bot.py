import os, sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN=os.getenv('DISCORD_TOKEN')
GUILD_ID=int(os.getenv('GUILD_ID','0'))
ADMIN_ROLE_ID=int(os.getenv('ADMIN_ROLE_ID','0'))
DB='demonlist.db'


def connect():
    c=sqlite3.connect(DB)
    c.row_factory=sqlite3.Row
    return c


def init_db():
    c=connect()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS levels(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      gd_id TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      creator TEXT DEFAULT '',
      position INTEGER UNIQUE,
      points INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS players(
      user_id INTEGER PRIMARY KEY,
      name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS records(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      level_id INTEGER NOT NULL,
      percent INTEGER NOT NULL,
      verified INTEGER NOT NULL DEFAULT 0,
      awarded INTEGER NOT NULL DEFAULT 0,
      UNIQUE(user_id, level_id)
    );
    ''')
    c.commit(); c.close()


def is_admin(interaction):
    if ADMIN_ROLE_ID == 0:
        return interaction.user.guild_permissions.manage_guild
    return any(r.id == ADMIN_ROLE_ID for r in getattr(interaction.user,'roles',[]))


def get_level(query):
    c=connect()
    row=c.execute('''SELECT * FROM levels
                    WHERE gd_id NOT LIKE '__slot_%'
                    AND (name LIKE ? OR gd_id=?)
                    ORDER BY position LIMIT 1''',(f'%{query}%',query)).fetchone()
    c.close(); return row


def points_for_position(position):
    return max(1,151-position)


class DemonBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())
    async def setup_hook(self):
        init_db()
        if GUILD_ID:
            guild=discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

bot=DemonBot()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} | Custom Demonlist Top 150')

@bot.tree.command(name='top', description='Show the custom Top 150 Demonlist')
async def top(interaction: discord.Interaction):
    c=connect()
    rows=c.execute("SELECT * FROM levels WHERE gd_id NOT LIKE '__slot_%' ORDER BY position").fetchall()
    c.close()
    if not rows:
        return await interaction.response.send_message('The list is empty.')
    lines=[f"**#{r['position']}** {r['name']} — `{r['points']} points`" for r in rows]
    await interaction.response.send_message('\n'.join(lines[:50]))
    for i in range(50,len(lines),50):
        await interaction.followup.send('\n'.join(lines[i:i+50]))

@bot.tree.command(name='leaderboard', description='Player leaderboard by points')
async def leaderboard(interaction: discord.Interaction):
    c=connect()
    rows=c.execute('''SELECT p.user_id,p.name,COALESCE(SUM(l.points),0) AS pts,
                             COUNT(r.id) AS demons
                      FROM players p
                      LEFT JOIN records r ON r.user_id=p.user_id AND r.verified=1
                      LEFT JOIN levels l ON l.id=r.level_id
                      GROUP BY p.user_id
                      ORDER BY pts DESC, demons DESC, p.name
                      LIMIT 100''').fetchall()
    c.close()
    if not rows:
        return await interaction.response.send_message('The leaderboard is empty.')
    lines=[f"**#{i}** {r['name']} — **{r['pts']} points** • {r['demons']} verified" for i,r in enumerate(rows,1)]
    await interaction.response.send_message('\n'.join(lines[:50]))
    if len(lines)>50:
        await interaction.followup.send('\n'.join(lines[50:]))

@bot.tree.command(name='level', description='Show level information')
@app_commands.describe(name='Geometry Dash level name or ID')
async def level(interaction: discord.Interaction, name: str):
    l=get_level(name)
    if not l:
        return await interaction.response.send_message('Level not found.')
    c=connect()
    records=c.execute('''SELECT p.name,r.percent FROM records r
                         JOIN players p ON p.user_id=r.user_id
                         WHERE r.level_id=? AND r.verified=1
                         ORDER BY r.percent DESC''',(l['id'],)).fetchall()
    c.close()
    msg=(f"**{l['name']}**\nGD ID: `{l['gd_id']}`\nCreator: `{l['creator'] or '—'}`\n"
         f"Position: **#{l['position']}**\nPoints: **{l['points']}**")
    if records:
        msg+='\n\n**Records:**\n'+'\n'.join(f"{r['name']} — {r['percent']}%" for r in records[:20])
    await interaction.response.send_message(msg)

@bot.tree.command(name='player', description='Show player profile')
@app_commands.describe(user='Discord player')
async def player(interaction: discord.Interaction, user: discord.User):
    c=connect()
    rows=c.execute('''SELECT l.name,l.position,l.points,r.percent FROM records r
                     JOIN levels l ON l.id=r.level_id
                     WHERE r.user_id=? AND r.verified=1 ORDER BY l.position''',(user.id,)).fetchall()
    c.close()
    pts=sum(r['points'] for r in rows)
    msg=f"**{user.display_name}**\nPoints: **{pts}**\nVerified demons: **{len(rows)}**"
    if rows:
        msg+='\n\n'+'\n'.join(f"#{r['position']} {r['name']} — {r['percent']}% (+{r['points']} points)" for r in rows[:25])
    await interaction.response.send_message(msg)

admin=app_commands.Group(name='admin', description='Manage the custom Demonlist')

@admin.command(name='addlevel', description='Add a level to a specific position 1-150')
@app_commands.describe(position='Position 1-150', name='Level name', gd_id='Geometry Dash ID', creator='Creator', points='Points; 0 = position-based')
async def addlevel(interaction: discord.Interaction, position: int, name: str, gd_id: str, creator: str='', points: int=0):
    if not is_admin(interaction): return await interaction.response.send_message('You don't have permission.', ephemeral=True)
    if not 1<=position<=150: return await interaction.response.send_message('Position must be 1-150.', ephemeral=True)
    c=connect()
    exists=c.execute('SELECT id FROM levels WHERE gd_id=?',(gd_id,)).fetchone()
    if exists:
        c.close(); return await interaction.response.send_message('This GD ID already exists.', ephemeral=True)
    # Shift existing levels at or below the target down. #150 is dropped if occupied.
    c.execute('DELETE FROM levels WHERE position=150')
    c.execute("UPDATE levels SET position=position+1 WHERE position>=? AND position<150",(position,))
    pts=points if points>0 else points_for_position(position)
    c.execute('INSERT INTO levels(gd_id,name,creator,position,points) VALUES(?,?,?,?,?)',(gd_id,name,creator,position,pts))
    c.commit(); c.close()
    await interaction.response.send_message(f'✅ Added **{name}** at **#{position}** for **{pts} points**.')

@admin.command(name='removelevel', description='Remove a level from the list')
@app_commands.describe(name='Level name or ID')
async def removelevel(interaction: discord.Interaction, name: str):
    if not is_admin(interaction): return await interaction.response.send_message('You don't have permission.', ephemeral=True)
    l=get_level(name)
    if not l: return await interaction.response.send_message('Level not found.', ephemeral=True)
    c=connect(); p=l['position']
    c.execute('DELETE FROM records WHERE level_id=?',(l['id'],))
    c.execute('DELETE FROM levels WHERE id=?',(l['id'],))
    c.execute('UPDATE levels SET position=position-1 WHERE position>?',(p,))
    c.commit(); c.close()
    await interaction.response.send_message(f'🗑️ Removed **{l["name"]}**.')

@admin.command(name='record', description='Add or update a player record')
@app_commands.describe(user='Player', level='Level name/ID', percent='Percentage 1-100')
async def record(interaction: discord.Interaction, user: discord.User, level: str, percent: int):
    if not is_admin(interaction): return await interaction.response.send_message('You don't have permission.', ephemeral=True)
    if not 1<=percent<=100: return await interaction.response.send_message('Percentage must be 1-100.', ephemeral=True)
    l=get_level(level)
    if not l: return await interaction.response.send_message('Level not found.', ephemeral=True)
    c=connect()
    c.execute('INSERT OR IGNORE INTO players(user_id,name) VALUES(?,?)',(user.id,user.display_name))
    c.execute('''INSERT INTO records(user_id,level_id,percent,verified,awarded) VALUES(?,?,?,?,?)
                 ON CONFLICT(user_id,level_id) DO UPDATE SET percent=excluded.percent,verified=0,awarded=0''',(user.id,l['id'],percent,0,0))
    c.commit(); c.close()
    await interaction.response.send_message(f'📝 Record **{user.display_name} — {l["name"]} {percent}%** is awaiting verification.')

@admin.command(name='verify', description='Verify a record and automatically award points')
@app_commands.describe(user='Player', level='Level name/ID')
async def verify(interaction: discord.Interaction, user: discord.User, level: str):
    if not is_admin(interaction): return await interaction.response.send_message('You don't have permission.', ephemeral=True)
    l=get_level(level)
    if not l: return await interaction.response.send_message('Level not found.', ephemeral=True)
    c=connect()
    r=c.execute('SELECT * FROM records WHERE user_id=? AND level_id=?',(user.id,l['id'])).fetchone()
    if not r: c.close(); return await interaction.response.send_message('No record to verify.', ephemeral=True)
    if r['verified'] and r['awarded']:
        c.close(); return await interaction.response.send_message('This record is already verified and awarded.', ephemeral=True)
    c.execute('UPDATE records SET verified=1,awarded=1 WHERE id=?',(r['id'],))
    c.commit(); c.close()
    await interaction.response.send_message(f'✅ **{user.display_name}**: {l["name"]} **{r["percent"]}%** — awarded **{l["points"]} points**.')

bot.tree.add_command(admin)

if not TOKEN:
    raise SystemExit('Missing DISCORD_TOKEN in .env')
bot.run(TOKEN)
