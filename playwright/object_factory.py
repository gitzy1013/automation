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

from typing import Any, Dict, cast

from playwright.browser import Browser
from playwright.browser_context import BrowserContext
from playwright.browser_server import BrowserServer
from playwright.browser_type import BrowserType
from playwright.cdp_session import CDPSession
from playwright.chromium_browser_context import ChromiumBrowserContext
from playwright.connection import ChannelOwner
from playwright.console_message import ConsoleMessage
from playwright.dialog import Dialog
from playwright.download import Download
from playwright.element_handle import ElementHandle
from playwright.frame import Frame
from playwright.js_handle import JSHandle
from playwright.network import Request, Response, Route
from playwright.page import BindingCall, Page, Worker
from playwright.playwright import Playwright
from playwright.selectors import Selectors
from playwright.stream import Stream


class DummyObject(ChannelOwner):
    def __init__(
        self, parent: ChannelOwner, type: str, guid: str, initializer: Dict
    ) -> None:
        super().__init__(parent, type, guid, initializer)


def create_remote_object(
    parent: ChannelOwner, type: str, guid: str, initializer: Dict
) -> Any:
    if type == "BindingCall":
        return BindingCall(parent, type, guid, initializer)
    if type == "Browser":
        return Browser(cast(BrowserType, parent), type, guid, initializer)
    if type == "BrowserServer":
        return BrowserServer(parent, type, guid, initializer)
    if type == "BrowserType":
        return BrowserType(parent, type, guid, initializer)
    if type == "BrowserContext":
        browser_name: str = ""
        if isinstance(parent, Browser):
            browser_name = parent._browser_type.name
        if isinstance(parent, BrowserType):
            browser_name = parent.name
        if browser_name == "chromium":
            return ChromiumBrowserContext(parent, type, guid, initializer)
        return BrowserContext(parent, type, guid, initializer)
    if type == "CDPSession":
        return CDPSession(parent, type, guid, initializer)
    if type == "ConsoleMessage":
        return ConsoleMessage(parent, type, guid, initializer)
    if type == "Dialog":
        return Dialog(parent, type, guid, initializer)
    if type == "Download":
        return Download(parent, type, guid, initializer)
    if type == "ElementHandle":
        return ElementHandle(parent, type, guid, initializer)
    if type == "Frame":
        return Frame(parent, type, guid, initializer)
    if type == "JSHandle":
        return JSHandle(parent, type, guid, initializer)
    if type == "Page":
        return Page(parent, type, guid, initializer)
    if type == "Playwright":
        return Playwright(parent, type, guid, initializer)
    if type == "Request":
        return Request(parent, type, guid, initializer)
    if type == "Response":
        return Response(parent, type, guid, initializer)
    if type == "Route":
        return Route(parent, type, guid, initializer)
    if type == "Worker":
        return Worker(parent, type, guid, initializer)
    if type == "Selectors":
        return Selectors(parent, type, guid, initializer)
    if type == "Stream":
        return Stream(parent, type, guid, initializer)
    return DummyObject(parent, type, guid, initializer)
