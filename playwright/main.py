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
import gzip
import os
import shutil
import stat
import subprocess
import sys
from typing import Any

from greenlet import greenlet

from playwright.async_api import Playwright as AsyncPlaywright
from playwright.connection import Connection
from playwright.helper import Error, not_installed_error
from playwright.object_factory import create_remote_object
from playwright.playwright import Playwright
from playwright.sync_api import Playwright as SyncPlaywright
from playwright.sync_base import dispatcher_fiber, set_dispatcher_fiber


def compute_driver_name() -> str:
    platform = sys.platform
    if platform == "darwin":
        result = "driver-macos"
    elif platform == "linux":
        result = "driver-linux"
    elif platform == "win32":
        result = "driver-win.exe"
    return result


async def run_driver_async() -> Connection:
    package_path = os.path.dirname(os.path.abspath(__file__))
    driver_name = compute_driver_name()
    driver_executable = os.path.join(package_path, driver_name)
    archive_name = os.path.join(package_path, "drivers", driver_name + ".gz")

    if not os.path.exists(driver_executable) or os.path.getmtime(
        driver_executable
    ) < os.path.getmtime(archive_name):
        raise not_installed_error(
            "Playwright requires additional post-installation step to be made."
        )

    proc = await asyncio.create_subprocess_exec(
        driver_executable,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=32768,
    )
    assert proc.stdout
    assert proc.stdin
    connection = Connection(
        proc.stdout, proc.stdin, create_remote_object, asyncio.get_event_loop()
    )
    return connection


def run_driver() -> Connection:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        raise Error(
            "Existing event loop is already running. Most likely that you have nested Playwright initialisations."
        )
    return loop.run_until_complete(run_driver_async())


class SyncPlaywrightContextManager:
    def __init__(self) -> None:
        self._connection = run_driver()
        self._playwright: SyncPlaywright

    def __enter__(self) -> SyncPlaywright:
        g_self = greenlet.getcurrent()

        def callback_wrapper(playwright_impl: Playwright) -> None:
            self._playwright = SyncPlaywright(playwright_impl)
            g_self.switch()

        self._connection.call_on_object_with_known_name("Playwright", callback_wrapper)
        set_dispatcher_fiber(greenlet(lambda: self._connection.run_sync()))
        dispatcher_fiber().switch()
        return self._playwright

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._connection.stop_sync()


class AsyncPlaywrightContextManager:
    def __init__(self) -> None:
        self._connection: Connection

    async def __aenter__(self) -> AsyncPlaywright:
        self._connection = await run_driver_async()
        self._connection.run_async()
        return AsyncPlaywright(
            await self._connection.wait_for_object_with_known_name("Playwright")
        )

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._connection.stop_async()


if sys.platform == "win32":
    # Use ProactorEventLoop in 3.7, which is default in 3.8
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)


def main() -> None:
    if "install" not in sys.argv:
        print('Run "python -m playwright install" to complete installation')
        return
    package_path = os.path.dirname(os.path.abspath(__file__))
    driver_name = compute_driver_name()
    driver_executable = os.path.join(package_path, driver_name)
    archive_name = os.path.join(package_path, "drivers", driver_name + ".gz")

    if not os.path.exists(driver_executable) or os.path.getmtime(
        driver_executable
    ) < os.path.getmtime(archive_name):
        print(f"Extracting {archive_name} into {driver_executable}...")
        with gzip.open(archive_name, "rb") as f_in, open(
            driver_executable, "wb"
        ) as f_out:
            shutil.copyfileobj(f_in, f_out)

        st = os.stat(driver_executable)
        if st.st_mode & stat.S_IEXEC == 0:
            print(f"Making {driver_executable} executable...")
            os.chmod(driver_executable, st.st_mode | stat.S_IEXEC)

    print("Installing the browsers...")
    subprocess.run(f"{driver_executable} install", shell=True)

    print("Playwright is now ready for use")
