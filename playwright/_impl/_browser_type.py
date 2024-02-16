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
from typing import TYPE_CHECKING, Dict, Optional, Pattern, Sequence, Union, cast

from playwright._impl._api_structures import (
    Geolocation,
    HttpCredentials,
    ProxySettings,
    ViewportSize,
)
from playwright._impl._browser import Browser, prepare_browser_context_params
from playwright._impl._browser_context import BrowserContext
from playwright._impl._connection import (
    ChannelOwner,
    Connection,
    from_channel,
    from_nullable_channel,
)
from playwright._impl._errors import Error
from playwright._impl._helper import (
    ColorScheme,
    Env,
    ForcedColors,
    HarContentPolicy,
    HarMode,
    ReducedMotion,
    ServiceWorkersPolicy,
    locals_to_params,
)
from playwright._impl._json_pipe import JsonPipeTransport
from playwright._impl._network import serialize_headers
from playwright._impl._waiter import throw_on_timeout

if TYPE_CHECKING:
    from playwright._impl._playwright import Playwright


class BrowserType(ChannelOwner):
    def __init__(
        self, parent: ChannelOwner, type: str, guid: str, initializer: Dict
    ) -> None:
        super().__init__(parent, type, guid, initializer)
        self._playwright: "Playwright"

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
        channel: Optional[str] = None,
        args: Sequence[str] = None,
        ignoreDefaultArgs: Union[bool, Sequence[str]] = None,
        handleSIGINT: Optional[bool] = None,
        handleSIGTERM: Optional[bool] = None,
        handleSIGHUP: Optional[bool] = None,
        timeout: Optional[float] = None,
        env: Optional[Env] = None,
        headless: Optional[bool] = None,
        devtools: Optional[bool] = None,
        proxy: Optional[ProxySettings] = None,
        downloadsPath: Union[str, Path] = None,
        slowMo: Optional[float] = None,
        tracesDir: Union[pathlib.Path, str] = None,
        chromiumSandbox: Optional[bool] = None,
        firefoxUserPrefs: Optional[Dict[str, Union[str, float, bool]]] = None,
    ) -> Browser:
        params = locals_to_params(locals())
        normalize_launch_params(params)
        browser = cast(
            Browser, from_channel(await self._channel.send("launch", params))
        )
        self._did_launch_browser(browser)
        return browser

    async def launch_persistent_context(
        self,
        userDataDir: Union[str, Path],
        channel: Optional[str] = None,
        executablePath: Union[str, Path] = None,
        args: Sequence[str] = None,
        ignoreDefaultArgs: Union[bool, Sequence[str]] = None,
        handleSIGINT: Optional[bool] = None,
        handleSIGTERM: Optional[bool] = None,
        handleSIGHUP: Optional[bool] = None,
        timeout: Optional[float] = None,
        env: Optional[Env] = None,
        headless: Optional[bool] = None,
        devtools: Optional[bool] = None,
        proxy: Optional[ProxySettings] = None,
        downloadsPath: Union[str, Path] = None,
        slowMo: Optional[float] = None,
        viewport: Optional[ViewportSize] = None,
        screen: Optional[ViewportSize] = None,
        noViewport: Optional[bool] = None,
        ignoreHTTPSErrors: Optional[bool] = None,
        javaScriptEnabled: Optional[bool] = None,
        bypassCSP: Optional[bool] = None,
        userAgent: Optional[str] = None,
        locale: Optional[str] = None,
        timezoneId: Optional[str] = None,
        geolocation: Optional[Geolocation] = None,
        permissions: Sequence[str] = None,
        extraHTTPHeaders: Optional[Dict[str, str]] = None,
        offline: Optional[bool] = None,
        httpCredentials: Optional[HttpCredentials] = None,
        deviceScaleFactor: Optional[float] = None,
        isMobile: Optional[bool] = None,
        hasTouch: Optional[bool] = None,
        colorScheme: Optional[ColorScheme] = None,
        reducedMotion: Optional[ReducedMotion] = None,
        forcedColors: Optional[ForcedColors] = None,
        acceptDownloads: Optional[bool] = None,
        tracesDir: Union[pathlib.Path, str] = None,
        chromiumSandbox: Optional[bool] = None,
        firefoxUserPrefs: Optional[Dict[str, Union[str, float, bool]]] = None,
        recordHarPath: Union[Path, str] = None,
        recordHarOmitContent: Optional[bool] = None,
        recordVideoDir: Union[Path, str] = None,
        recordVideoSize: Optional[ViewportSize] = None,
        baseURL: Optional[str] = None,
        strictSelectors: Optional[bool] = None,
        serviceWorkers: Optional[ServiceWorkersPolicy] = None,
        recordHarUrlFilter: Union[Pattern[str], str] = None,
        recordHarMode: Optional[HarMode] = None,
        recordHarContent: Optional[HarContentPolicy] = None,
    ) -> BrowserContext:
        userDataDir = str(Path(userDataDir)) if userDataDir else ""
        params = locals_to_params(locals())
        await prepare_browser_context_params(params)
        normalize_launch_params(params)
        context = cast(
            BrowserContext,
            from_channel(await self._channel.send("launchPersistentContext", params)),
        )
        self._did_create_context(context, params, params)
        return context

    async def connect_over_cdp(
        self,
        endpointURL: str,
        timeout: Optional[float] = None,
        slowMo: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Browser:
        params = locals_to_params(locals())
        if params.get("headers"):
            params["headers"] = serialize_headers(params["headers"])
        response = await self._channel.send_return_as_dict("connectOverCDP", params)
        browser = cast(Browser, from_channel(response["browser"]))
        self._did_launch_browser(browser)

        default_context = cast(
            Optional[BrowserContext],
            from_nullable_channel(response.get("defaultContext")),
        )
        if default_context:
            self._did_create_context(default_context, {}, {})
        return browser

    async def connect(
        self,
        wsEndpoint: str,
        timeout: Optional[float] = None,
        slowMo: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
        exposeNetwork: Optional[str] = None,
    ) -> Browser:
        if timeout is None:
            timeout = 30000
        if slowMo is None:
            slowMo = 0

        headers = {**(headers if headers else {}), "x-playwright-browser": self.name}
        local_utils = self._connection.local_utils
        pipe_channel = (
            await local_utils._channel.send_return_as_dict(
                "connect",
                {
                    "wsEndpoint": wsEndpoint,
                    "headers": headers,
                    "slowMo": slowMo,
                    "timeout": timeout,
                    "exposeNetwork": exposeNetwork,
                },
            )
        )["pipe"]
        transport = JsonPipeTransport(self._connection._loop, pipe_channel)

        connection = Connection(
            self._connection._dispatcher_fiber,
            self._connection._object_factory,
            transport,
            self._connection._loop,
            local_utils=self._connection.local_utils,
        )
        connection.mark_as_remote()
        connection._is_sync = self._connection._is_sync
        connection._loop.create_task(connection.run())
        playwright_future = connection.playwright_future

        timeout_future = throw_on_timeout(timeout, Error("Connection timed out"))
        done, pending = await asyncio.wait(
            {transport.on_error_future, playwright_future, timeout_future},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not playwright_future.done():
            playwright_future.cancel()
        if not timeout_future.done():
            timeout_future.cancel()
        playwright: "Playwright" = next(iter(done)).result()
        playwright._set_selectors(self._playwright.selectors)
        self._connection._child_ws_connections.append(connection)
        pre_launched_browser = playwright._initializer.get("preLaunchedBrowser")
        assert pre_launched_browser
        browser = cast(Browser, from_channel(pre_launched_browser))
        self._did_launch_browser(browser)
        browser._should_close_connection_on_close = True

        def handle_transport_close() -> None:
            for context in browser.contexts:
                for page in context.pages:
                    page._on_close()
                context._on_close()
            browser._on_close()
            connection.cleanup()

        transport.once("close", handle_transport_close)

        return browser

    def _did_create_context(
        self, context: BrowserContext, context_options: Dict, browser_options: Dict
    ) -> None:
        context._set_options(context_options, browser_options)

    def _did_launch_browser(self, browser: Browser) -> None:
        browser._browser_type = self


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
    if "tracesDir" in params:
        params["tracesDir"] = str(Path(params["tracesDir"]))
