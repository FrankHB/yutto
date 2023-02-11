from __future__ import annotations

import argparse
import asyncio
import re
from collections.abc import Coroutine
from typing import Any

import aiohttp

from yutto._typing import EpisodeData, FId, MId
from yutto.api.space import get_favourite_avids, get_favourite_info, get_user_name
from yutto.api.ugc_video import UgcVideoListItem, get_ugc_video_list
from yutto.exceptions import NotFoundError
from yutto.extractor._abc import BatchExtractor
from yutto.extractor.common import extract_ugc_video_data
from yutto.utils.console.logger import Badge, Logger
from yutto.utils.fetcher import Fetcher


class FavouritesExtractor(BatchExtractor):
    """用户单一收藏夹"""

    REGEX_FAV = re.compile(r"https?://space\.bilibili\.com/(?P<mid>\d+)/favlist\?fid=(?P<fid>\d+)((&ftype=create)|$)")

    mid: MId
    fid: FId

    def match(self, url: str) -> bool:
        if match_obj := self.REGEX_FAV.match(url):
            self.mid = MId(match_obj.group("mid"))
            self.fid = FId(match_obj.group("fid"))
            return True
        else:
            return False

    async def extract(
        self, session: aiohttp.ClientSession, args: argparse.Namespace
    ) -> list[Coroutine[Any, Any, EpisodeData | None] | None]:
        username, favourite_info = await asyncio.gather(
            get_user_name(session, self.mid),
            get_favourite_info(session, self.fid),
        )
        Logger.custom(favourite_info["title"], Badge("收藏夹", fore="black", back="cyan"))

        ugc_video_info_list: list[tuple[UgcVideoListItem, str, str]] = []

        for avid in await get_favourite_avids(session, self.fid):
            try:
                ugc_video_list = await get_ugc_video_list(session, avid)
                # 在使用 SESSDATA 时，如果不去事先 touch 一下视频链接的话，是无法获取 episode_data 的
                # 至于为什么前面那俩（投稿视频页和番剧页）不需要额外 touch，因为在 get_redirected_url 阶段连接过了呀
                await Fetcher.touch_url(session, avid.to_url())
                for ugc_video_item in ugc_video_list["pages"]:
                    ugc_video_info_list.append(
                        (
                            ugc_video_item,
                            ugc_video_list["title"],
                            ugc_video_list["pubdate"],
                        )
                    )
            except NotFoundError as e:
                Logger.error(e.message)
                continue

        return [
            extract_ugc_video_data(
                session,
                ugc_video_item["avid"],
                ugc_video_item,
                args,
                {
                    "title": title,
                    "username": username,
                    "series_title": favourite_info["title"],
                    "pubdate": pubdate,
                },
                "{username}的收藏夹/{series_title}/{title}/{name}",
            )
            for ugc_video_item, title, pubdate in ugc_video_info_list
        ]
