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

import re
from typing import List, Tuple, cast

from playwright._impl._api_types import Error
from playwright._impl._element_handle import ElementHandle
from playwright._impl._frame import Frame
from playwright._impl._page import Page
from playwright._impl._selectors import Selectors


class Utils:
    async def attach_frame(self, page: Page, frame_id: str, url: str):
        handle = await page.evaluate_handle(
            """async ({ frame_id, url }) => {
                const frame = document.createElement('iframe');
                frame.src = url;
                frame.id = frame_id;
                document.body.appendChild(frame);
                await new Promise(x => frame.onload = x);
                return frame;
            }""",
            {"frame_id": frame_id, "url": url},
        )
        return await cast(ElementHandle, handle.as_element()).content_frame()

    async def detach_frame(self, page: Page, frame_id: str):
        await page.evaluate(
            "frame_id => document.getElementById(frame_id).remove()", frame_id
        )

    def dump_frames(self, frame: Frame, indentation: str = "") -> List[str]:
        indentation = indentation or ""
        description = re.sub(r":\d+/", ":<PORT>/", frame.url)
        if frame.name:
            description += " (" + frame.name + ")"
        result = [indentation + description]
        sorted_frames = sorted(
            frame.child_frames, key=lambda frame: frame.url + frame.name
        )
        for child in sorted_frames:
            result = result + utils.dump_frames(child, "    " + indentation)
        return result

    async def verify_viewport(self, page: Page, width: int, height: int):
        assert cast(Tuple[int, int], page.viewport_size())[0] == width
        assert cast(Tuple[int, int], page.viewport_size())[1] == height
        assert await page.evaluate("window.innerWidth") == width
        assert await page.evaluate("window.innerHeight") == height

    async def register_selector_engine(
        self, selectors: Selectors, *args, **kwargs
    ) -> None:
        try:
            await selectors.register(*args, **kwargs)
        except Error as exc:
            if "has been already registered" not in exc.message:
                raise exc


utils = Utils()
