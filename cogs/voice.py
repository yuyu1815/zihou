"""
Voice channel control commands.
- /start: Join the invoker's current voice channel (does not move if already connected)
- /stop: Leave the current voice channel in this guild
- 時報: audio フォルダー内の 1.mp3～24.mp3 を毎正時に再生（減税は未設置）

Responses are in Japanese to match the request.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import discord
from discord.ext import commands
from discord.ext.commands import Context


AUDIO_DIR = Path(__file__).resolve().parent.parent / "audio"
JIHOU_FILE = AUDIO_DIR / "時報.mp3"


class Voice(commands.Cog, name="voice"):
    def __init__(self, bot) -> None:
        self.bot = bot
        # ギルドごとの時報タスクを管理
        self._hourly_tasks: Dict[int, asyncio.Task] = {}
        # 次の正時に1回だけ再生するワンショットタスク
        self._oneshot_tasks: Dict[int, asyncio.Task] = {}

    def cog_unload(self) -> None:
        # Cog unload 時に全タスクを停止
        for task in self._hourly_tasks.values():
            task.cancel()
        for task in self._oneshot_tasks.values():
            task.cancel()

    async def _play_sequence(self, voice_client: discord.VoiceClient, paths: list[Path]) -> bool:
        """指定された複数の音声ファイルを順番に再生する。
        - 1つ以上再生できた場合 True を返す。
        - すべて存在しない/失敗した場合は False。
        - 例外はログに記録し、次のトラックに進む。
        """
        played_any = False
        for p in paths:
            if not p.exists():
                # ファイルがない場合はスキップ
                self.bot.logger.warning(self._fmt_missing(p))
                continue
            try:
                # もしまだ何か再生中なら待つ
                while voice_client.is_playing() or voice_client.is_paused():
                    await asyncio.sleep(0.2)
                source = discord.FFmpegPCMAudio(str(p))
                voice_client.play(source)
                played_any = True
                # 再生が終わるまで待機
                while voice_client.is_playing():
                    await asyncio.sleep(0.2)
            except Exception as e:
                self.bot.logger.error(f"音声再生に失敗しました ({p.name}): {e}")
                # 失敗したら次のトラックへ
                continue
        return played_any

    @staticmethod
    def _hour_to_filename(hour: int) -> str:
        """0..23 の時刻を 1..24.wav にマッピング
        例: 1時→1.wav, 13時→13.wav,
        """
        return f"{hour}.wav"

    @staticmethod
    def _fmt_missing(file: Path) -> str:
        return f"音声ファイルが見つかりません: {file}"

    async def _hourly_chime_loop(self, guild_id: int) -> None:
        """ギルドごとに動作する時報ループ。
        - 常に次の“ちょうどの時刻”まで待機し、対応する wav を再生
        - ボイス未接続 / 切断時は待機を継続（/start で再接続すればそのまま動作）
        - 再生中で埋まっている場合はその時間の時報はスキップ
        """
        while True:
            # 次の正時まで待機
            now = datetime.now()
            next_top = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            await asyncio.sleep(max(0.0, (next_top - now).total_seconds()))

            # 現在のギルドの VoiceClient を取得
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            voice_client: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore[attr-defined]

            # 接続していなければスキップ（次の時間を待つ）
            if not voice_client or not voice_client.is_connected():
                continue

            # すでに再生中なら今回はスキップ
            if voice_client.is_playing() or voice_client.is_paused():
                continue

            # 再生するファイルを決定
            hour = datetime.now().hour
            filename = self._hour_to_filename(hour)
            path = AUDIO_DIR / filename

            # 時報(共通) + 時間の順で再生
            played = await self._play_sequence(voice_client, [JIHOU_FILE, path])
            if not played:
                # どちらも再生できなかった場合は一度だけ警告
                if not JIHOU_FILE.exists() and not path.exists():
                    self.bot.logger.warning(self._fmt_missing(path))
                continue


    def _ensure_hourly_task(self, guild_id: int) -> None:
        task = self._hourly_tasks.get(guild_id)
        if task is None or task.done() or task.cancelled():
            self._hourly_tasks[guild_id] = asyncio.create_task(self._hourly_chime_loop(guild_id))

    def _cancel_hourly_task(self, guild_id: int) -> None:
        task = self._hourly_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    async def _wait_and_play_once(self, guild_id: int, notify_channel_id: Optional[int]) -> None:
        """次の正時まで待機して、対応する wav を1回だけ再生する。
        再生可否はその時点の接続状態に依存（未接続ならスキップ）。
        実行後は oneshot タスク登録をクリーンアップ。
        """
        try:
            now = datetime.now()
            next_top = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            await asyncio.sleep(max(0.0, (next_top - now).total_seconds()))

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return
            voice_client: Optional[discord.VoiceClient] = guild.voice_client  # type: ignore[attr-defined]

            if not voice_client or not voice_client.is_connected():
                # 接続していないので今回はスキップ
                if notify_channel_id:
                    channel = self.bot.get_channel(notify_channel_id)
                    if isinstance(channel, (discord.TextChannel, discord.Thread)):
                        try:
                            await channel.send("指定時刻になりましたが、ボイスチャンネルに接続していないため再生をスキップしました。/start で接続してください。")
                        except Exception:
                            pass
                return

            # 既に再生中ならスキップ
            if voice_client.is_playing() or voice_client.is_paused():
                return

            hour = datetime.now().hour  # 正時になっている想定
            filename = self._hour_to_filename(hour)
            path = AUDIO_DIR / filename

            # 時報(共通) + 時間の順で再生
            played = await self._play_sequence(voice_client, [JIHOU_FILE, path])
            if notify_channel_id:
                channel = self.bot.get_channel(notify_channel_id)
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        if played:
                            await channel.send(f"{hour}時の時報を再生します。")
                        else:
                            # どちらも再生できなかった場合
                            if not JIHOU_FILE.exists() and not path.exists():
                                await channel.send(self._fmt_missing(path))
                            else:
                                await channel.send("音声再生に失敗しました。FFmpeg の導入やファイルの存在を確認してください。")
                    except Exception:
                        pass
        finally:
            # タスク終了時にクリア
            self._oneshot_tasks.pop(guild_id, None)

    def _schedule_oneshot(self, guild_id: int, notify_channel_id: Optional[int]) -> None:
        # 既存があれば置き換え
        prev = self._oneshot_tasks.pop(guild_id, None)
        if prev:
            prev.cancel()
        self._oneshot_tasks[guild_id] = asyncio.create_task(self._wait_and_play_once(guild_id, notify_channel_id))

    @commands.hybrid_command(name="start", description="あなたがいるボイスチャンネルに参加します（毎正時に時報を流します）")
    @commands.guild_only()
    async def start(self, ctx: Context) -> None:
        """
        Join the voice channel the user is currently in.
        - If already connected in this guild to a different channel, do not move.
        - Requires the bot to have Connect and (ideally) Speak permissions.
        - 参加中は毎正時に `audio/時報.mp3` の後に、対応する `audio/0.wav ～ 23.wav` を再生します。
        """
        author = ctx.author
        if not isinstance(author, (discord.Member,)):
            await ctx.send("このコマンドはサーバー内でのみ使用できます。")
            return

        if not author.voice or not author.voice.channel:
            await ctx.send("まず先にボイスチャンネルに参加してください。")
            return

        destination: discord.VoiceChannel | discord.StageChannel = author.voice.channel
        voice_client: Optional[discord.VoiceClient] = ctx.voice_client

        try:
            if voice_client and voice_client.is_connected():
                await ctx.send(f"すでに {destination.mention} に接続しています。時報タスクを確認します…")
            else:
                await destination.connect()
                await ctx.send(f"{destination.mention} に参加しました。毎正時に時報を流します。")
        except discord.Forbidden:
            await ctx.send("接続する権限がありません。ボットに『接続』と『発言』権限があるか確認してください。")
            return
        except discord.ClientException as e:
            await ctx.send(f"ボイス接続中にエラーが発生しました: {e}")
            return

        # ギルドの時報タスクを起動
        if ctx.guild:
            self._ensure_hourly_task(ctx.guild.id)
            # audio ディレクトリ存在確認を一度案内
            if not AUDIO_DIR.exists():
                await ctx.send(f"注意: 音声フォルダーが見つかりませんでした: `{AUDIO_DIR}`\n`audio/1.mp3` ～ `audio/24.mp3` を配置してください。")

    @commands.hybrid_command(name="stop", description="ボイスチャンネルから切断します（時報も停止）")
    @commands.guild_only()
    async def stop(self, ctx: Context) -> None:
        """
        Disconnect the bot from the guild's current voice channel and stop hourly chime.
        """
        voice_client: Optional[discord.VoiceClient] = ctx.voice_client
        if not voice_client or not voice_client.is_connected():
            await ctx.send("現在どのボイスチャンネルにも接続していません。", ephemeral=True)  # type: ignore
            return
        try:
            await voice_client.disconnect(force=True)
            await ctx.send("切断しました。時報も停止しました。")
        except discord.ClientException as e:
            await ctx.send(f"切断時にエラーが発生しました: {e}")
        finally:
            if ctx.guild:
                self._cancel_hourly_task(ctx.guild.id)

    @commands.hybrid_command(name="test", description="次の時間の音声を今すぐ一度だけ再生します（必要なら接続します）")
    @commands.guild_only()
    async def test(self, ctx: Context) -> None:
        """Play the next hour's chime immediately, once.
        - Connects to your current voice channel if not connected yet in this guild.
        - Does not move if already connected to a different channel.
        - Stops current playback if any, then plays the corresponding wav immediately.
        """
        author = ctx.author
        if not isinstance(author, (discord.Member,)):
            await ctx.send("このコマンドはサーバー内でのみ使用できます。")
            return

        # Ensure connection
        voice_client: Optional[discord.VoiceClient] = ctx.voice_client
        if not voice_client or not voice_client.is_connected():
            if not author.voice or not author.voice.channel:
                await ctx.send("まず先にボイスチャンネルに参加してください。")
                return
            destination: discord.VoiceChannel | discord.StageChannel = author.voice.channel
            try:
                await destination.connect()
                await ctx.send(f"{destination.mention} に参加しました。")
            except discord.Forbidden:
                await ctx.send("接続する権限がありません。ボットに『接続』と『発言』権限があるか確認してください。")
                return
            except discord.ClientException as e:
                await ctx.send(f"ボイス接続中にエラーが発生しました: {e}")
                return
            voice_client = ctx.voice_client

        if not voice_client or not voice_client.is_connected():
            await ctx.send("ボイスチャンネルへの接続に失敗しました。")
            return

        # Determine next hour and audio files (時報 + 時間)
        now = datetime.now()
        next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).hour
        filename = self._hour_to_filename(next_hour)
        path = AUDIO_DIR / filename

        # Stop current playback if any, then play the sequence immediately
        try:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            played = await self._play_sequence(voice_client, [JIHOU_FILE, path])
            if played:
                await ctx.send(f"{next_hour}時の時報を再生します。（順番: 時報 → {filename}）")
            else:
                # どちらも再生不可
                if not JIHOU_FILE.exists() and not path.exists():
                    await ctx.send(self._fmt_missing(path))
                else:
                    await ctx.send("音声再生に失敗しました。FFmpeg の導入やファイルの存在を確認してください。")
        except Exception as e:
            await ctx.send(f"音声再生に失敗しました: {e}")
            self.bot.logger.error(f"test: 音声再生に失敗: {e}")
            return


async def setup(bot):
    await bot.add_cog(Voice(bot))
