# Copyright (c) Microsoft Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import pathlib
from pathlib import Path
from typing import Dict, List, Optional, Union, cast

from playwright._impl._api_structures import (
    Geolocation,
    HttpCredentials,
    ProxySettings,
    ViewportSize,
)
from playwright._impl._browser import Browser, normalize_context_params
from playwright._impl._browser_context import BrowserContext
from playwright._impl._connection import (
    ChannelOwner,
    from_channel,
    from_nullable_channel,
)
from playwright._impl._helper import (
    ColorScheme,
    Env,
    ForcedColors,
    ReducedMotion,
    locals_to_params,
)
from playwright._impl.jsonpipe import JsonPipe

from ._connection import Connection


class BrowserType(ChannelOwner):
    def __init__(
        self, parent: ChannelOwner, type: str, guid: str, initializer: Dict
    ) -> None:
        super().__init__(parent, type, guid, initializer)

    def __repr__(self) -> str:
        return f"<BrowserType name={self.name} executable_path={self.executable_path}>"

    @property
    def name(self) -> str:
        return self._initializer["name"]

    @property
    def executable_path(self) -> str:
        return self._initializer["executablePath"]

    async def launch(
        self,
        executablePath: Union[str, Path] = None,
        channel: str = None,
        args: List[str] = None,
        ignoreDefaultArgs: Union[bool, List[str]] = None,
        handleSIGINT: bool = None,
        handleSIGTERM: bool = None,
        handleSIGHUP: bool = None,
        timeout: float = None,
        env: Env = None,
        headless: bool = None,
        devtools: bool = None,
        proxy: ProxySettings = None,
        downloadsPath: Union[str, Path] = None,
        slowMo: float = None,
        tracesDir: Union[pathlib.Path, str] = None,
        chromiumSandbox: bool = None,
        firefoxUserPrefs: Dict[str, Union[str, float, bool]] = None,
    ) -> Browser:
        params = locals_to_params(locals())
        normalize_launch_params(params)
        return from_channel(await self._channel.send("launch", params))

    async def launch_persistent_context(
        self,
        userDataDir: Union[str, Path],
        channel: str = None,
        executablePath: Union[str, Path] = None,
        args: List[str] = None,
        ignoreDefaultArgs: Union[bool, List[str]] = None,
        handleSIGINT: bool = None,
        handleSIGTERM: bool = None,
        handleSIGHUP: bool = None,
        timeout: float = None,
        env: Env = None,
        headless: bool = None,
        devtools: bool = None,
        proxy: ProxySettings = None,
        downloadsPath: Union[str, Path] = None,
        slowMo: float = None,
        viewport: ViewportSize = None,
        screen: ViewportSize = None,
        noViewport: bool = None,
        ignoreHTTPSErrors: bool = None,
        javaScriptEnabled: bool = None,
        bypassCSP: bool = None,
        userAgent: str = None,
        locale: str = None,
        timezoneId: str = None,
        geolocation: Geolocation = None,
        permissions: List[str] = None,
        extraHTTPHeaders: Dict[str, str] = None,
        offline: bool = None,
        httpCredentials: HttpCredentials = None,
        deviceScaleFactor: float = None,
        isMobile: bool = None,
        hasTouch: bool = None,
        colorScheme: ColorScheme = None,
        reducedMotion: ReducedMotion = None,
        forcedColors: ForcedColors = None,
        acceptDownloads: bool = None,
        tracesDir: Union[pathlib.Path, str] = None,
        chromiumSandbox: bool = None,
        recordHarPath: Union[Path, str] = None,
        recordHarOmitContent: bool = None,
        recordVideoDir: Union[Path, str] = None,
        recordVideoSize: ViewportSize = None,
        baseURL: str = None,
        strictSelectors: bool = None,
    ) -> BrowserContext:
        userDataDir = str(Path(userDataDir))
        params = locals_to_params(locals())
        await normalize_context_params(self._connection._is_sync, params)
        normalize_launch_params(params)
        context = from_channel(
            await self._channel.send("launchPersistentContext", params)
        )
        context._options = params
        return context

    async def connect_over_cdp(
        self,
        endpointURL: str,
        timeout: float = None,
        slow_mo: float = None,
        headers: Dict[str, str] = None,
    ) -> Browser:
        params = locals_to_params(locals())
        params["sdkLanguage"] = (
            "python" if self._connection._is_sync else "python-async"
        )
        response = await self._channel.send_return_as_dict("connectOverCDP", params)
        browser = cast(Browser, from_channel(response["browser"]))

        default_context = cast(
            Optional[BrowserContext],
            from_nullable_channel(response.get("defaultContext")),
        )
        if default_context:
            browser._contexts.append(default_context)
            default_context._browser = browser
        return browser

    async def connect(
        self,
        wsEndpoint: str,
        timeout: float = None,
        slowMo: float = None,
        headers: Dict[str, str] = None,
    ) -> Browser:
        pipe: JsonPipe = from_channel(
            await self._channel.send("connect", locals_to_params(locals()))
        )
        connection = Connection(
            self._connection._dispatcher_fiber, asyncio.get_running_loop(), pipe.close
        )
        connection.mark_as_remote()
        connection._is_sync = self._connection._is_sync

        def pipe_closed() -> None:
            for context in browser.contexts:
                for page in context.pages:
                    page._on_close()
                context._on_close()
            browser._on_close()

        pipe.on("closed", pipe_closed)

        async def on_message(message: Dict) -> None:
            try:
                await pipe.send(message)
            except Exception:
                if not browser.is_connected:
                    pipe_closed()
                raise

        connection.on_message = on_message
        pipe.on("message", connection.dispatch)
        await connection.run()
        playwright = await connection.playwright_future
        browser: Browser = from_channel(playwright._initializer["preLaunchedBrowser"])
        browser._is_remote = True
        browser._is_connected_over_websocket = True
        return browser


def normalize_launch_params(params: Dict) -> None:
    if "env" in params:
        params["env"] = [
            {"name": name, "value": str(value)}
            for [name, value] in params["env"].items()
        ]
    if "ignoreDefaultArgs" in params:
        if params["ignoreDefaultArgs"] is True:
            params["ignoreAllDefaultArgs"] = True
            del params["ignoreDefaultArgs"]
    if "executablePath" in params:
        params["executablePath"] = str(Path(params["executablePath"]))
    if "downloadsPath" in params:
        params["downloadsPath"] = str(Path(params["downloadsPath"]))
