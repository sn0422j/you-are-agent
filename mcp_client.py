import asyncio
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult


class MCPClient:
    """MCPサーバーとの非同期通信を行うクライアント"""

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.server_type: Optional[str] = None
        self.server_command_or_server_url: Optional[str] = None
        self.stdio_server_key: Optional[str] = None
        self.exit_stack = AsyncExitStack()

    async def connect_to_server(
        self,
        server_type: str,
        server_command_or_server_url: str,
        stdio_args: Optional[list[str]] = None,
        stdio_env: Optional[dict[str, str]] = None,
        stdio_cwd: Optional[str] = None,
        stdio_server_key: Optional[str] = None,
    ):
        match server_type:
            case "stdio":
                server_params = StdioServerParameters(
                    command=server_command_or_server_url, args=stdio_args or [], env=stdio_env, cwd=stdio_cwd
                )
                # streams = await self.exit_stack.enter_async_context(stdio_client(server_params))
                # self.session = await self.exit_stack.enter_async_context(ClientSession(*streams))
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                stdio, write = stdio_transport
                self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
                await self.session.initialize()
                self.server_type = server_type
                self.server_command_or_server_url = server_command_or_server_url
                self.stdio_server_key = stdio_server_key
            case "sse":
                streams = await self.exit_stack.enter_async_context(sse_client(url=server_command_or_server_url))
                self.session = await self.exit_stack.enter_async_context(ClientSession(*streams))
                await self.session.initialize()
                self.server_type = server_type
                self.server_command_or_server_url = server_command_or_server_url

    async def get_tools(self) -> list[Tool]:
        """MCPサーバーから利用可能なツールのリストを取得する"""
        if self.session is None:
            raise ValueError("MCPサーバーに接続されていません。")
        response = await self.session.list_tools()
        tools = response.tools
        if not isinstance(tools, list):
            raise ValueError("ツールリストのレスポンス形式が不正です (リストではありません)。")
        return tools

    async def run_tool(self, tool_name: str, tool_args: dict[str, Any]) -> CallToolResult:
        """指定されたツールをMCPサーバー上で実行する"""
        if self.session is None:
            raise ValueError("MCPサーバーに接続されていません。")
        result = await self.session.call_tool(tool_name, tool_args)
        if not isinstance(result, CallToolResult):
            raise ValueError("ツール実行結果のレスポンス形式が不正です (辞書ではありません)。")
        return result

    async def aclose(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def test():
    client = MCPClient()
    try:
        await client.connect_to_server(server_type="sse", server_command_or_server_url="http://localhost:8080/sse")
        tools = await client.get_tools()
        print(f"{tools=}")
    finally:
        await client.aclose()

    # client = MCPClient()
    # try:
    #     await client.connect_to_server(server_type="stdio", server_command_or_server_url="", stdio_args=[])
    #     tools = await client.get_tools()
    #     print(f"{tools=}")
    # finally:
    #     await client.aclose()


if __name__ == "__main__":
    asyncio.run(test())
