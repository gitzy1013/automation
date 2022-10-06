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
import contextvars
import inspect
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union, cast

from greenlet import greenlet
from pyee import AsyncIOEventEmitter, EventEmitter

import playwright
from playwright._impl._helper import ParsedMessagePayload, parse_error
from playwright._impl._transport import Transport

if TYPE_CHECKING:
    from playwright._impl._local_utils import LocalUtils
    from playwright._impl._playwright import Playwright


class Channel(AsyncIOEventEmitter):
    def __init__(self, connection: "Connection", guid: str) -> None:
        super().__init__()
        self._connection: Connection = connection
        self._guid = guid
        self._object: Optional[ChannelOwner] = None

    async def send(self, method: str, params: Dict = None) -> Any:
        return await self._connection.wrap_api_call(
            lambda: self.inner_send(method, params, False)
        )

    async def send_return_as_dict(self, method: str, params: Dict = None) -> Any:
        return await self._connection.wrap_api_call(
            lambda: self.inner_send(method, params, True)
        )

    def send_no_reply(self, method: str, params: Dict = None) -> None:
        self._connection.wrap_api_call_sync(
            lambda: self._connection._send_message_to_server(
                self._guid, method, {} if params is None else params
            )
        )

    async def inner_send(
        self, method: str, params: Optional[Dict], return_as_dict: bool
    ) -> Any:
        if params is None:
            params = {}
        callback = self._connection._send_message_to_server(self._guid, method, params)
        if self._connection._error:
            error = self._connection._error
            self._connection._error = None
            raise error
        done, _ = await asyncio.wait(
            {
                self._connection._transport.on_error_future,
                callback.future,
            },
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not callback.future.done():
            callback.future.cancel()
        result = next(iter(done)).result()
        # Protocol now has named return values, assume result is one level deeper unless
        # there is explicit ambiguity.
        if not result:
            return None
        assert isinstance(result, dict)
        if return_as_dict:
            return result
        if len(result) == 0:
            return None
        assert len(result) == 1
        key = next(iter(result))
        return result[key]


class ChannelOwner(AsyncIOEventEmitter):
    def __init__(
        self,
        parent: Union["ChannelOwner", "Connection"],
        type: str,
        guid: str,
        initializer: Dict,
    ) -> None:
        super().__init__(loop=parent._loop)
        self._loop: asyncio.AbstractEventLoop = parent._loop
        self._dispatcher_fiber: Any = parent._dispatcher_fiber
        self._type = type
        self._guid = guid
        self._connection: Connection = (
            parent._connection if isinstance(parent, ChannelOwner) else parent
        )
        self._parent: Optional[ChannelOwner] = (
            parent if isinstance(parent, ChannelOwner) else None
        )
        self._objects: Dict[str, "ChannelOwner"] = {}
        self._channel: Channel = Channel(self._connection, guid)
        self._channel._object = self
        self._initializer = initializer

        self._connection._objects[guid] = self
        if self._parent:
            self._parent._objects[guid] = self

    def _dispose(self) -> None:
        # Clean up from parent and connection.
        if self._parent:
            del self._parent._objects[self._guid]
        del self._connection._objects[self._guid]

        # Dispose all children.
        for object in list(self._objects.values()):
            object._dispose()
        self._objects.clear()

    def _adopt(self, child: "ChannelOwner") -> None:
        del cast("ChannelOwner", child._parent)._objects[child._guid]
        self._objects[child._guid] = child
        child._parent = self


class ProtocolCallback:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.stack_trace: traceback.StackSummary
        self.future = loop.create_future()
        # The outer task can get cancelled by the user, this forwards the cancellation to the inner task.
        current_task = asyncio.current_task()

        def cb(task: asyncio.Task) -> None:
            if current_task:
                current_task.remove_done_callback(cb)
            if task.cancelled():
                self.future.cancel()

        if current_task:
            current_task.add_done_callback(cb)
            self.future.add_done_callback(
                lambda _: current_task.remove_done_callback(cb)
                if current_task
                else None
            )


class RootChannelOwner(ChannelOwner):
    def __init__(self, connection: "Connection") -> None:
        super().__init__(connection, "Root", "", {})

    async def initialize(self) -> "Playwright":
        return from_channel(
            await self._channel.send(
                "initialize",
                {
                    "sdkLanguage": "python",
                },
            )
        )


class Connection(EventEmitter):
    def __init__(
        self,
        dispatcher_fiber: Any,
        object_factory: Callable[[ChannelOwner, str, str, Dict], ChannelOwner],
        transport: Transport,
        loop: asyncio.AbstractEventLoop,
        local_utils: Optional["LocalUtils"] = None,
    ) -> None:
        super().__init__()
        self._dispatcher_fiber = dispatcher_fiber
        self._transport = transport
        self._transport.on_message = lambda msg: self.dispatch(msg)
        self._waiting_for_object: Dict[str, Callable[[ChannelOwner], None]] = {}
        self._last_id = 0
        self._objects: Dict[str, ChannelOwner] = {}
        self._callbacks: Dict[int, ProtocolCallback] = {}
        self._object_factory = object_factory
        self._is_sync = False
        self._child_ws_connections: List["Connection"] = []
        self._loop = loop
        self.playwright_future: asyncio.Future["Playwright"] = loop.create_future()
        self._error: Optional[BaseException] = None
        self.is_remote = False
        self._init_task: Optional[asyncio.Task] = None
        self._api_zone: contextvars.ContextVar[Optional[Dict]] = contextvars.ContextVar(
            "ApiZone", default=None
        )
        self._local_utils: Optional["LocalUtils"] = local_utils

    @property
    def local_utils(self) -> "LocalUtils":
        assert self._local_utils
        return self._local_utils

    def mark_as_remote(self) -> None:
        self.is_remote = True

    async def run_as_sync(self) -> None:
        self._is_sync = True
        await self.run()

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._root_object = RootChannelOwner(self)

        async def init() -> None:
            self.playwright_future.set_result(await self._root_object.initialize())

        await self._transport.connect()
        self._init_task = self._loop.create_task(init())
        await self._transport.run()

    def stop_sync(self) -> None:
        self._transport.request_stop()
        self._dispatcher_fiber.switch()
        self._loop.run_until_complete(self._transport.wait_until_stopped())
        self.cleanup()

    async def stop_async(self) -> None:
        self._transport.request_stop()
        await self._transport.wait_until_stopped()
        self.cleanup()

    def cleanup(self) -> None:
        if self._init_task and not self._init_task.done():
            self._init_task.cancel()
        for ws_connection in self._child_ws_connections:
            ws_connection._transport.dispose()
        self.emit("close")

    def call_on_object_with_known_name(
        self, guid: str, callback: Callable[[ChannelOwner], None]
    ) -> None:
        self._waiting_for_object[guid] = callback

    def _send_message_to_server(
        self, guid: str, method: str, params: Dict
    ) -> ProtocolCallback:
        self._last_id += 1
        id = self._last_id
        callback = ProtocolCallback(self._loop)
        task = asyncio.current_task(self._loop)
        callback.stack_trace = cast(
            traceback.StackSummary,
            getattr(task, "__pw_stack_trace__", traceback.extract_stack()),
        )
        self._callbacks[id] = callback
        message = {
            "id": id,
            "guid": guid,
            "method": method,
            "params": self._replace_channels_with_guids(params),
            "metadata": self._api_zone.get(),
        }
        self._transport.send(message)
        self._callbacks[id] = callback
        return callback

    def dispatch(self, msg: ParsedMessagePayload) -> None:
        id = msg.get("id")
        if id:
            callback = self._callbacks.pop(id)
            if callback.future.cancelled():
                return
            error = msg.get("error")
            if error:
                parsed_error = parse_error(error["error"])  # type: ignore
                parsed_error.stack = "".join(
                    traceback.format_list(callback.stack_trace)[-10:]
                )
                callback.future.set_exception(parsed_error)
            else:
                result = self._replace_guids_with_channels(msg.get("result"))
                callback.future.set_result(result)
            return

        guid = msg["guid"]
        method = msg.get("method")
        params = msg.get("params")
        if method == "__create__":
            assert params
            parent = self._objects[guid]
            self._create_remote_object(
                parent, params["type"], params["guid"], params["initializer"]
            )
            return

        object = self._objects.get(guid)
        if not object:
            raise Exception(f'Cannot find object to "{method}": {guid}')

        if method == "__adopt__":
            child_guid = cast(Dict[str, str], params)["guid"]
            child = self._objects.get(child_guid)
            if not child:
                raise Exception(f"Unknown new child: {child_guid}")
            object._adopt(child)
            return

        if method == "__dispose__":
            self._objects[guid]._dispose()
            return
        object = self._objects[guid]
        should_replace_guids_with_channels = "jsonPipe@" not in guid
        try:
            if self._is_sync:
                for listener in object._channel.listeners(method):
                    # Each event handler is a potentilly blocking context, create a fiber for each
                    # and switch to them in order, until they block inside and pass control to each
                    # other and then eventually back to dispatcher as listener functions return.
                    g = greenlet(listener)
                    if should_replace_guids_with_channels:
                        g.switch(self._replace_guids_with_channels(params))
                    else:
                        g.switch(params)
            else:
                if should_replace_guids_with_channels:
                    object._channel.emit(
                        method, self._replace_guids_with_channels(params)
                    )
                else:
                    object._channel.emit(method, params)
        except BaseException as exc:
            print("Error occurred in event listener", file=sys.stderr)
            traceback.print_exc()
            self._error = exc

    def _create_remote_object(
        self, parent: ChannelOwner, type: str, guid: str, initializer: Dict
    ) -> ChannelOwner:
        initializer = self._replace_guids_with_channels(initializer)
        result = self._object_factory(parent, type, guid, initializer)
        if guid in self._waiting_for_object:
            self._waiting_for_object.pop(guid)(result)
        return result

    def _replace_channels_with_guids(
        self,
        payload: Any,
    ) -> Any:
        if payload is None:
            return payload
        if isinstance(payload, Path):
            return str(payload)
        if isinstance(payload, list):
            return list(map(self._replace_channels_with_guids, payload))
        if isinstance(payload, Channel):
            return dict(guid=payload._guid)
        if isinstance(payload, dict):
            result = {}
            for key, value in payload.items():
                result[key] = self._replace_channels_with_guids(value)
            return result
        return payload

    def _replace_guids_with_channels(self, payload: Any) -> Any:
        if payload is None:
            return payload
        if isinstance(payload, list):
            return list(map(self._replace_guids_with_channels, payload))
        if isinstance(payload, dict):
            if payload.get("guid") in self._objects:
                return self._objects[payload["guid"]]._channel
            result = {}
            for key, value in payload.items():
                result[key] = self._replace_guids_with_channels(value)
            return result
        return payload

    async def wrap_api_call(
        self, cb: Callable[[], Any], is_internal: bool = False
    ) -> Any:
        if self._api_zone.get():
            return await cb()
        task = asyncio.current_task(self._loop)
        st: List[inspect.FrameInfo] = getattr(task, "__pw_stack__", inspect.stack())
        metadata = _extract_metadata_from_stack(st, is_internal)
        if metadata:
            self._api_zone.set(metadata)
        try:
            return await cb()
        finally:
            self._api_zone.set(None)

    def wrap_api_call_sync(
        self, cb: Callable[[], Any], is_internal: bool = False
    ) -> Any:
        if self._api_zone.get():
            return cb()
        task = asyncio.current_task(self._loop)
        st: List[inspect.FrameInfo] = getattr(task, "__pw_stack__", inspect.stack())
        metadata = _extract_metadata_from_stack(st, is_internal)
        if metadata:
            self._api_zone.set(metadata)
        try:
            return cb()
        finally:
            self._api_zone.set(None)


def from_channel(channel: Channel) -> Any:
    return channel._object


def from_nullable_channel(channel: Optional[Channel]) -> Optional[Any]:
    return channel._object if channel else None


def _extract_metadata_from_stack(
    st: List[inspect.FrameInfo], is_internal: bool
) -> Optional[Dict]:
    if is_internal:
        return {
            "apiName": "",
            "stack": [],
            "internal": True,
        }
    playwright_module_path = str(Path(playwright.__file__).parents[0])
    last_internal_api_name = ""
    api_name = ""
    stack: List[Dict] = []
    for frame in st:
        is_playwright_internal = frame.filename.startswith(playwright_module_path)

        method_name = ""
        if "self" in frame[0].f_locals:
            method_name = frame[0].f_locals["self"].__class__.__name__ + "."
        method_name += frame[0].f_code.co_name

        if not is_playwright_internal:
            stack.append(
                {
                    "file": frame.filename,
                    "line": frame.lineno,
                    "function": method_name,
                }
            )
        if is_playwright_internal:
            last_internal_api_name = method_name
        elif last_internal_api_name:
            api_name = last_internal_api_name
            last_internal_api_name = ""
    if not api_name:
        api_name = last_internal_api_name
    if api_name:
        return {
            "apiName": api_name,
            "stack": stack,
        }
    return None
