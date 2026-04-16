from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
from typing import Optional, List
import base64

mcp = FastMCP("Favicon API")

BASE_URL = os.environ.get("FAVICON_API_BASE_URL", "http://localhost:3000")


@mcp.tool()
async def get_favicon(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch and retrieve a favicon for a given domain or URL. Supports PNG, JPG, ICO, WebP, and SVG formats. Optionally resize and convert the image."""
    params = {}
    if size is not None:
        params["size"] = size
    if format is not None:
        params["format"] = format
    params["response"] = "json"

    url = f"{BASE_URL}/{domain}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    return {
                        "success": True,
                        "domain": domain,
                        "status_code": response.status_code,
                        "data": response.json()
                    }
                else:
                    # It returned an image, encode it as base64
                    img_b64 = base64.b64encode(response.content).decode("utf-8")
                    return {
                        "success": True,
                        "domain": domain,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "image_base64": img_b64,
                        "image_size_bytes": len(response.content)
                    }
            else:
                return {
                    "success": False,
                    "domain": domain,
                    "status_code": response.status_code,
                    "error": response.text
                }
        except httpx.RequestError as e:
            return {
                "success": False,
                "domain": domain,
                "error": str(e)
            }


@mcp.tool()
async def check_health() -> dict:
    """Check the health and status of the Favicon API service. Use this to verify the service is running and operational."""
    url = f"{BASE_URL}/health"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url)
            return {
                "success": response.status_code == 200,
                "status_code": response.status_code,
                "data": response.json() if response.status_code == 200 else response.text
            }
        except httpx.RequestError as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Could not connect to the Favicon API service"
            }


@mcp.tool()
async def get_favicon_batch(
    domains: List[str],
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch favicons for multiple domains at once. Returns favicon data for each requested domain."""
    params = {"response": "json"}
    if size is not None:
        params["size"] = size
    if format is not None:
        params["format"] = format

    results = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        for domain in domains:
            url = f"{BASE_URL}/{domain}"
            try:
                response = await client.get(url, params=params)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        results[domain] = {
                            "success": True,
                            "status_code": response.status_code,
                            "data": response.json()
                        }
                    else:
                        img_b64 = base64.b64encode(response.content).decode("utf-8")
                        results[domain] = {
                            "success": True,
                            "status_code": response.status_code,
                            "content_type": content_type,
                            "image_base64": img_b64,
                            "image_size_bytes": len(response.content)
                        }
                else:
                    results[domain] = {
                        "success": False,
                        "status_code": response.status_code,
                        "error": response.text
                    }
            except httpx.RequestError as e:
                results[domain] = {
                    "success": False,
                    "error": str(e)
                }

    return {
        "success": True,
        "total": len(domains),
        "results": results
    }


@mcp.tool()
async def get_favicon_url(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None,
    base_url: Optional[str] = None
) -> dict:
    """Generate a direct favicon API URL for a domain without actually fetching it. Use this when you need to embed a favicon URL in HTML or markdown."""
    effective_base_url = base_url if base_url else BASE_URL

    params_parts = []
    if size is not None:
        params_parts.append(f"size={size}")
    if format is not None:
        params_parts.append(f"format={format}")

    favicon_url = f"{effective_base_url}/{domain}"
    if params_parts:
        favicon_url += "?" + "&".join(params_parts)

    image_tag = f'<img src="{favicon_url}" alt="{domain} favicon"'
    if size:
        image_tag += f' width="{size}" height="{size}"'
    image_tag += " />"

    return {
        "success": True,
        "domain": domain,
        "favicon_url": favicon_url,
        "html_img_tag": image_tag,
        "markdown": f"![{domain} favicon]({favicon_url})"
    }


@mcp.tool()
async def check_favicon_availability(domain: str) -> dict:
    """Check whether a favicon can be found for a given domain without downloading the full image. Validates that a domain has a discoverable favicon."""
    url = f"{BASE_URL}/{domain}"
    params = {"response": "json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                data = {}
                if "application/json" in content_type:
                    data = response.json()
                return {
                    "success": True,
                    "domain": domain,
                    "available": True,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "details": data
                }
            elif response.status_code == 404:
                return {
                    "success": True,
                    "domain": domain,
                    "available": False,
                    "status_code": response.status_code,
                    "message": "No favicon found for this domain"
                }
            else:
                return {
                    "success": False,
                    "domain": domain,
                    "available": False,
                    "status_code": response.status_code,
                    "error": response.text
                }
        except httpx.RequestError as e:
            return {
                "success": False,
                "domain": domain,
                "available": False,
                "error": str(e)
            }


@mcp.tool()
async def get_service_config() -> dict:
    """Retrieve the current configuration and capabilities of the Favicon API service, including supported formats, size limits, and cache settings."""
    # The Favicon API does not expose a dedicated /config endpoint,
    # so we return static capability info derived from the README and source code.
    return {
        "success": True,
        "service": "Favicon API",
        "base_url": BASE_URL,
        "capabilities": {
            "supported_formats": ["png", "jpg", "ico", "webp", "svg"],
            "response_types": ["image", "json"],
            "size_range": {
                "min_pixels": 16,
                "max_pixels": 512
            },
            "query_parameters": {
                "domain": "Path parameter - the domain or URL (e.g., /github.com)",
                "size": "Optional integer - resize favicon to this square pixel dimension (16-512)",
                "format": "Optional string - output format: png, jpg, ico, webp, svg",
                "response": "Optional string - response type: image (default) or json",
                "default": "Optional string - fallback image URL if no favicon is found"
            },
            "fallback_behavior": "Falls back to Google favicon API by default, then to configured DEFAULT_IMAGE_URL",
            "caching": {
                "description": "Sets HTTP Cache-Control headers for CDN/proxy integration",
                "default_success_ttl_seconds": 604800,
                "default_error_ttl_seconds": 604800
            },
            "security": {
                "ssrf_protection": "Blocks requests to private IP ranges (configurable)",
                "max_redirects": 5,
                "request_timeout_ms": 5000,
                "max_image_size_bytes": 5242880
            },
            "cors": "Configurable, default allows all origins (*)"
        },
        "endpoints": {
            "health": "GET /health",
            "favicon": "GET /<domain>[?size=<n>&format=<fmt>&response=<image|json>&default=<url>]"
        }
    }




_SERVER_SLUG = "vemetric-favicon-api"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app(transport="streamable-http", stateless_http=True)

class _FixAcceptHeader:
    """Ensure Accept header includes both types FastMCP requires."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                new_headers = [(k, v) for k, v in scope["headers"] if k != b"accept"]
                new_headers.append((b"accept", b"application/json, text/event-stream"))
                scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)

app = _FixAcceptHeader(Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.lifespan,
))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
