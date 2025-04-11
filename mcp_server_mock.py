import asyncio
import random

import uvicorn
from mcp.server import Server
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

# Initialize FastMCP server
mcp = FastMCP("mock_server")


@mcp.tool()
async def echo(message: str):
    """Echoes back the input message. Useful for testing."""
    # 簡単な遅延をシミュレート
    await asyncio.sleep(0.5)
    return message


@mcp.tool()
async def add(number1: int, number2: int) -> int:
    """Adds two numbers together."""
    await asyncio.sleep(random.uniform(0.2, 1.0))  # ランダムな遅延
    return number1 + number2


@mcp.tool()
async def web_search(query: str, num_results: int | None = None) -> list[dict[str, str]]:
    """Performs a mock web search and returns dummy results."""
    await asyncio.sleep(random.uniform(1.0, 3.0))  # 検索は少し時間がかかる想定
    # ダミーの検索結果を生成
    mock_results = []
    num = num_results or 5
    for i in range(num):
        mock_results.append(
            {
                "title": f"Mock Result {i + 1} for '{query}'",
                "url": f"http://example.com/search?q={query}&page={i + 1}",
                "snippet": f"This is a dummy snippet for result {i + 1} about {query}.",
            }
        )
    return mock_results


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can server the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )


if __name__ == "__main__":
    mcp_server = mcp._mcp_server

    import argparse

    parser = argparse.ArgumentParser(description="Run MCP SSE-based server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8002, help="Port to listen on")
    args = parser.parse_args()

    # Bind SSE request handling to MCP server
    starlette_app = create_starlette_app(mcp_server, debug=True)

    uvicorn.run(starlette_app, host=args.host, port=args.port)
