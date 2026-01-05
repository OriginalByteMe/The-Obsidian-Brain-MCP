from mcp_use.server import MCPServer

server = MCPServer(
    name="My Server",
    version="1.0.0",
    instructions="A simple example server"
)

@server.tool()
def echo(message: str) -> str:
    """Echo back the provided message."""
    return f"Echo: {message}"

@server.tool()
def calculate(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@server.tool()
def get_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().isoformat()

if __name__ == "__main__":
    server.run(transport="streamable-http", run_debug=True, reload=True)