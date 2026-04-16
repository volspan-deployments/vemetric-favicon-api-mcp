from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import asyncio
from typing import Optional, List

mcp = FastMCP("Favicon API")

BASE_URL = os.environ.get("FAVICON_API_BASE_URL", "http://localhost:3000")


@mcp.tool()
async def get_favicon(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch a favicon for a given domain or URL. This is the primary tool for retrieving website favicons.
    Use this when you need to get the icon/logo for any website.
    Supports format conversion, resizing, and intelligent fallback behavior."""
    params = {"response": "json"}
    if size is not None:
        params["size"] = str(size)
    if format is not None:
        params["format"] = format

    url = f"{BASE_URL}/{domain}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            if response.headers.get("content-type", "").startswith("application/json"):
                return {
                    "success": True,
                    "domain": domain,
                    "status_code": response.status_code,
                    "data": response.json()
                }
            else:
                content_type = response.headers.get("content-type", "unknown")
                content_length = len(response.content)
                return {
                    "success": response.status_code == 200,
                    "domain": domain,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "content_length": content_length,
                    "message": f"Favicon fetched successfully as {content_type}" if response.status_code == 200 else "Failed to fetch favicon",
                    "favicon_url": str(response.url)
                }
        except httpx.RequestError as e:
            return {
                "success": False,
                "domain": domain,
                "error": str(e),
                "message": "Failed to connect to Favicon API service"
            }


@mcp.tool()
async def check_health() -> dict:
    """Check the health and availability of the Favicon API service.
    Use this to verify the service is running correctly before making other requests,
    or to diagnose connectivity issues."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                return {
                    "healthy": True,
                    "status_code": response.status_code,
                    "data": data
                }
            else:
                return {
                    "healthy": False,
                    "status_code": response.status_code,
                    "message": "Service returned non-200 status"
                }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "error": str(e),
                "message": "Could not connect to Favicon API service"
            }


@mcp.tool()
async def get_favicon_batch(
    domains: List[str],
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch favicons for multiple domains at once.
    Use this when you need icons for several websites and want to retrieve them
    efficiently in parallel rather than making multiple individual requests."""
    params = {"response": "json"}
    if size is not None:
        params["size"] = str(size)
    if format is not None:
        params["format"] = format

    async def fetch_single(client: httpx.AsyncClient, domain: str) -> dict:
        url = f"{BASE_URL}/{domain}"
        try:
            response = await client.get(url, params=params)
            if response.headers.get("content-type", "").startswith("application/json"):
                return {
                    "domain": domain,
                    "success": True,
                    "status_code": response.status_code,
                    "data": response.json()
                }
            else:
                content_type = response.headers.get("content-type", "unknown")
                return {
                    "domain": domain,
                    "success": response.status_code == 200,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "favicon_url": str(response.url),
                    "message": f"Favicon fetched as {content_type}" if response.status_code == 200 else "Failed to fetch favicon"
                }
        except httpx.RequestError as e:
            return {
                "domain": domain,
                "success": False,
                "error": str(e)
            }

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [fetch_single(client, domain) for domain in domains]
        results = await asyncio.gather(*tasks)

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    return {
        "total": len(domains),
        "successful": len(successful),
        "failed": len(failed),
        "results": list(results)
    }


@mcp.tool()
async def resolve_favicon_url(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Resolve and return the direct URL to the best favicon for a given domain
    without downloading the image content. Use this when you need the favicon URL
    to embed in HTML, store as a reference, or pass to other systems rather than
    the raw image bytes."""
    params: dict = {}
    if size is not None:
        params["size"] = str(size)
    if format is not None:
        params["format"] = format

    query_string = ""
    if params:
        query_parts = [f"{k}={v}" for k, v in params.items()]
        query_string = "&" + "&".join(query_parts)

    api_url = f"{BASE_URL}/{domain}{query_string}"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        try:
            response = await client.head(api_url)
            if response.status_code in (200, 301, 302, 307, 308):
                resolved_url = str(response.url)
                return {
                    "success": True,
                    "domain": domain,
                    "favicon_api_url": api_url,
                    "resolved_url": resolved_url,
                    "status_code": response.status_code,
                    "embed_html": f'<img src="{api_url}" alt="{domain} favicon" />',
                    "parameters": params
                }
            else:
                return {
                    "success": False,
                    "domain": domain,
                    "favicon_api_url": api_url,
                    "status_code": response.status_code,
                    "message": "Could not resolve favicon URL"
                }
        except httpx.RequestError as e:
            return {
                "success": False,
                "domain": domain,
                "favicon_api_url": api_url,
                "error": str(e),
                "message": "Failed to connect to Favicon API service"
            }


@mcp.tool()
async def validate_domain(domain: str) -> dict:
    """Validate whether a given domain or URL is valid and safe to fetch a favicon from.
    Use this before attempting to fetch favicons for user-supplied domains to check for
    validity, private IP ranges, or other security concerns."""
    import re
    import ipaddress

    result = {
        "domain": domain,
        "is_valid": False,
        "is_safe": False,
        "issues": [],
        "normalized_domain": None
    }

    # Strip protocol if present
    normalized = domain.strip()
    if normalized.startswith("http://") or normalized.startswith("https://"):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(normalized)
            normalized = parsed.netloc or normalized
        except Exception:
            pass

    # Remove path and port
    normalized = normalized.split("/")[0].split("?")[0]
    result["normalized_domain"] = normalized

    # Basic domain format validation
    domain_pattern = re.compile(
        r'^(?:[a-zA-Z0-9]'
        r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
        r'\.)+[a-zA-Z]{2,}$'
    )

    # Check if it's an IP address
    is_ip = False
    ip_obj = None
    try:
        # Remove port if present
        ip_str = normalized.split(":")[0]
        ip_obj = ipaddress.ip_address(ip_str)
        is_ip = True
    except ValueError:
        pass

    if is_ip and ip_obj is not None:
        result["is_valid"] = True
        issues = []

        if ip_obj.is_private:
            issues.append("IP address is in a private range (RFC 1918)")
        if ip_obj.is_loopback:
            issues.append("IP address is a loopback address")
        if ip_obj.is_link_local:
            issues.append("IP address is link-local")
        if ip_obj.is_multicast:
            issues.append("IP address is multicast")
        if ip_obj.is_reserved:
            issues.append("IP address is reserved")

        result["issues"] = issues
        result["is_safe"] = len(issues) == 0
        result["is_ip_address"] = True
        result["ip_type"] = "IPv6" if ip_obj.version == 6 else "IPv4"
    elif domain_pattern.match(normalized):
        result["is_valid"] = True
        result["is_safe"] = True
        result["is_ip_address"] = False

        # Check for suspicious patterns
        issues = []
        if "localhost" in normalized.lower():
            issues.append("Domain contains 'localhost'")
            result["is_safe"] = False
        if normalized.lower().endswith(".local"):
            issues.append("Domain is a .local mDNS domain")
            result["is_safe"] = False
        if normalized.lower().endswith(".internal"):
            issues.append("Domain is an internal domain")
            result["is_safe"] = False

        result["issues"] = issues
    else:
        result["is_valid"] = False
        result["is_safe"] = False
        result["issues"] = ["Domain format is invalid"]
        result["is_ip_address"] = False

    # Also verify with the API service if it's reachable
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            test_url = f"{BASE_URL}/{domain}"
            response = await client.head(test_url, params={"response": "json"})
            result["api_reachable"] = True
            result["api_status_code"] = response.status_code
            result["api_would_serve"] = response.status_code == 200
        except httpx.RequestError:
            result["api_reachable"] = False
            result["api_would_serve"] = None

    return result


@mcp.tool()
async def get_service_config() -> dict:
    """Retrieve the current runtime configuration of the Favicon API service,
    including cache settings, timeout values, fallback behavior, CORS policy,
    and security settings. Use this to understand service capabilities and
    limits before making requests."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # First check if the service is healthy
            health_response = await client.get(f"{BASE_URL}/health")

            service_info = {
                "service_url": BASE_URL,
                "health_status": "ok" if health_response.status_code == 200 else "degraded",
                "health_data": health_response.json() if health_response.status_code == 200 else None,
                "known_configuration": {
                    "description": "Configuration values based on default settings and environment variables",
                    "server": {
                        "port": int(os.environ.get("PORT", 3000)),
                        "host": os.environ.get("HOST", "0.0.0.0")
                    },
                    "cache": {
                        "cache_control_success_seconds": int(os.environ.get("CACHE_CONTROL_SUCCESS", 604800)),
                        "cache_control_error_seconds": int(os.environ.get("CACHE_CONTROL_ERROR", 604800)),
                        "cache_control_success_human": "7 days (default)",
                        "cache_control_error_human": "7 days (default)"
                    },
                    "request_handling": {
                        "request_timeout_ms": int(os.environ.get("REQUEST_TIMEOUT", 5000)),
                        "max_image_size_bytes": int(os.environ.get("MAX_IMAGE_SIZE", 5242880)),
                        "max_image_size_human": "5MB (default)",
                        "max_redirects": int(os.environ.get("MAX_REDIRECTS", 5))
                    },
                    "fallback": {
                        "use_fallback_api": os.environ.get("USE_FALLBACK_API", "true").lower() == "true",
                        "fallback_description": "Falls back to Google's favicon API on primary fetch failure",
                        "default_image_url": os.environ.get("DEFAULT_IMAGE_URL", "not configured")
                    },
                    "security": {
                        "block_private_ips": os.environ.get("BLOCK_PRIVATE_IPS", "true").lower() == "true",
                        "allowed_origins": os.environ.get("ALLOWED_ORIGINS", "*")
                    },
                    "supported_formats": ["png", "jpg", "ico", "webp", "svg"],
                    "size_limits": {
                        "min_size_pixels": 16,
                        "max_size_pixels": 512
                    },
                    "response_types": ["image", "json"]
                }
            }
            return service_info
        except httpx.RequestError as e:
            return {
                "service_url": BASE_URL,
                "health_status": "unreachable",
                "error": str(e),
                "message": "Could not connect to Favicon API service",
                "known_defaults": {
                    "cache_control_success_seconds": 604800,
                    "cache_control_error_seconds": 604800,
                    "request_timeout_ms": 5000,
                    "max_image_size_bytes": 5242880,
                    "use_fallback_api": True,
                    "block_private_ips": True,
                    "allowed_origins": "*",
                    "supported_formats": ["png", "jpg", "ico", "webp", "svg"]
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
