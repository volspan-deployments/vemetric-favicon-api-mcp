from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import base64
import re
from typing import Optional, List
from urllib.parse import urlencode, urlparse

mcp = FastMCP("Favicon API")

BASE_URL = os.environ.get("FAVICON_API_BASE_URL", "http://localhost:3000")


def normalize_base_url(url: str) -> str:
    """Remove trailing slash from base URL."""
    return url.rstrip("/")


def build_favicon_url(domain: str, size: Optional[int] = None, fmt: Optional[str] = None, base_url: str = BASE_URL) -> str:
    """Construct favicon API URL for a domain."""
    base = normalize_base_url(base_url)
    params = {}
    if size is not None:
        params["size"] = size
    if fmt is not None:
        params["format"] = fmt
    query = urlencode(params)
    if query:
        return f"{base}/{domain}&{query}"
    return f"{base}/{domain}"


@mcp.tool()
async def get_favicon(domain: str, size: Optional[int] = None, format: Optional[str] = None) -> dict:
    """Fetch a favicon for a given domain or URL. Returns the image as base64-encoded data along with metadata."""
    url = build_favicon_url(domain, size, format, BASE_URL)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            content_type = response.headers.get("content-type", "")
            status_code = response.status_code
            if status_code == 200:
                image_data = base64.b64encode(response.content).decode("utf-8")
                return {
                    "success": True,
                    "domain": domain,
                    "url": url,
                    "status_code": status_code,
                    "content_type": content_type,
                    "size_bytes": len(response.content),
                    "image_base64": image_data,
                    "requested_size": size,
                    "requested_format": format,
                }
            else:
                return {
                    "success": False,
                    "domain": domain,
                    "url": url,
                    "status_code": status_code,
                    "error": f"Request failed with status {status_code}",
                    "requested_size": size,
                    "requested_format": format,
                }
    except httpx.TimeoutException:
        return {
            "success": False,
            "domain": domain,
            "url": url,
            "error": "Request timed out",
            "requested_size": size,
            "requested_format": format,
        }
    except Exception as e:
        return {
            "success": False,
            "domain": domain,
            "url": url,
            "error": str(e),
            "requested_size": size,
            "requested_format": format,
        }


@mcp.tool()
async def check_health(base_url: Optional[str] = None) -> dict:
    """Check if the Favicon API service is running and healthy."""
    target = normalize_base_url(base_url or BASE_URL)
    health_url = f"{target}/health"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text}
                return {
                    "healthy": True,
                    "status_code": response.status_code,
                    "base_url": target,
                    "response": data,
                }
            else:
                return {
                    "healthy": False,
                    "status_code": response.status_code,
                    "base_url": target,
                    "error": f"Health check returned status {response.status_code}",
                }
    except httpx.ConnectError:
        return {
            "healthy": False,
            "base_url": target,
            "error": "Connection refused — service may be down",
        }
    except httpx.TimeoutException:
        return {
            "healthy": False,
            "base_url": target,
            "error": "Health check timed out",
        }
    except Exception as e:
        return {
            "healthy": False,
            "base_url": target,
            "error": str(e),
        }


@mcp.tool()
async def get_favicon_url(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Construct and return the full Favicon API URL for a given domain without fetching the image."""
    effective_base = normalize_base_url(base_url or BASE_URL)
    url = build_favicon_url(domain, size, format, effective_base)
    return {
        "domain": domain,
        "favicon_url": url,
        "base_url": effective_base,
        "size": size,
        "format": format,
        "html_embed": f'<img src="{url}" alt="{domain} favicon" />',
    }


@mcp.tool()
async def batch_get_favicons(
    domains: List[str],
    size: Optional[int] = None,
    format: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict:
    """Fetch favicons for multiple domains at once. Returns results for each domain."""
    effective_base = normalize_base_url(base_url or BASE_URL)
    results = []
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for domain in domains:
            url = build_favicon_url(domain, size, format, effective_base)
            try:
                response = await client.get(url)
                content_type = response.headers.get("content-type", "")
                if response.status_code == 200:
                    image_data = base64.b64encode(response.content).decode("utf-8")
                    results.append({
                        "domain": domain,
                        "success": True,
                        "url": url,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "size_bytes": len(response.content),
                        "image_base64": image_data,
                    })
                else:
                    results.append({
                        "domain": domain,
                        "success": False,
                        "url": url,
                        "status_code": response.status_code,
                        "error": f"Request failed with status {response.status_code}",
                    })
            except httpx.TimeoutException:
                results.append({
                    "domain": domain,
                    "success": False,
                    "url": url,
                    "error": "Request timed out",
                })
            except Exception as e:
                results.append({
                    "domain": domain,
                    "success": False,
                    "url": url,
                    "error": str(e),
                })
    success_count = sum(1 for r in results if r.get("success"))
    return {
        "total": len(domains),
        "success_count": success_count,
        "failure_count": len(domains) - success_count,
        "requested_size": size,
        "requested_format": format,
        "results": results,
    }


@mcp.tool()
async def discover_favicon_sources(domain: str) -> dict:
    """Inspect a website and discover all potential favicon sources available for a domain."""
    # Normalize domain to a URL
    if not domain.startswith("http://") and not domain.startswith("https://"):
        site_url = f"https://{domain}"
    else:
        site_url = domain

    parsed = urlparse(site_url)
    base_site = f"{parsed.scheme}://{parsed.netloc}"
    sources = []

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Try fetching the HTML page
            try:
                response = await client.get(site_url, headers={"User-Agent": "Mozilla/5.0 FaviconDiscovery/1.0"})
                html = response.text

                # Find link tags with rel containing 'icon'
                icon_pattern = re.compile(
                    r'<link[^>]+rel=["\'][^"\']*(icon|apple-touch-icon|shortcut icon)[^"\'>]*["\'][^>]*>',
                    re.IGNORECASE
                )
                href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
                sizes_pattern = re.compile(r'sizes=["\']([^"\']+)["\']', re.IGNORECASE)
                type_pattern = re.compile(r'type=["\']([^"\']+)["\']', re.IGNORECASE)
                rel_pattern = re.compile(r'rel=["\']([^"\']+)["\']', re.IGNORECASE)

                for match in icon_pattern.finditer(html):
                    tag = match.group(0)
                    href_m = href_pattern.search(tag)
                    if href_m:
                        href = href_m.group(1)
                        if href.startswith("//"):
                            href = f"https:{href}"
                        elif href.startswith("/"):
                            href = f"{base_site}{href}"
                        elif not href.startswith("http"):
                            href = f"{base_site}/{href}"

                        sizes_m = sizes_pattern.search(tag)
                        type_m = type_pattern.search(tag)
                        rel_m = rel_pattern.search(tag)
                        sources.append({
                            "type": "link_tag",
                            "rel": rel_m.group(1) if rel_m else "icon",
                            "href": href,
                            "sizes": sizes_m.group(1) if sizes_m else None,
                            "mime_type": type_m.group(1) if type_m else None,
                        })

                # Check for web manifest
                manifest_pattern = re.compile(
                    r'<link[^>]+rel=["\'][^"\'>]*manifest[^"\'>]*["\'][^>]*>',
                    re.IGNORECASE
                )
                for match in manifest_pattern.finditer(html):
                    tag = match.group(0)
                    href_m = href_pattern.search(tag)
                    if href_m:
                        manifest_href = href_m.group(1)
                        if manifest_href.startswith("/"):
                            manifest_href = f"{base_site}{manifest_href}"
                        # Try to fetch manifest
                        try:
                            manifest_resp = await client.get(manifest_href)
                            if manifest_resp.status_code == 200:
                                manifest_data = manifest_resp.json()
                                icons = manifest_data.get("icons", [])
                                for icon in icons:
                                    src = icon.get("src", "")
                                    if src.startswith("/"):
                                        src = f"{base_site}{src}"
                                    elif not src.startswith("http"):
                                        src = f"{base_site}/{src}"
                                    sources.append({
                                        "type": "manifest_icon",
                                        "href": src,
                                        "sizes": icon.get("sizes"),
                                        "mime_type": icon.get("type"),
                                        "purpose": icon.get("purpose"),
                                    })
                        except Exception:
                            pass

            except Exception as page_err:
                pass

            # Always check standard favicon locations
            standard_paths = [
                "/favicon.ico",
                "/favicon.png",
                "/apple-touch-icon.png",
                "/apple-touch-icon-precomposed.png",
            ]
            for path in standard_paths:
                check_url = f"{base_site}{path}"
                try:
                    head_resp = await client.head(check_url)
                    if head_resp.status_code == 200:
                        content_type = head_resp.headers.get("content-type", "")
                        sources.append({
                            "type": "standard_path",
                            "href": check_url,
                            "sizes": None,
                            "mime_type": content_type or None,
                            "status": "available",
                        })
                except Exception:
                    pass

        return {
            "domain": domain,
            "site_url": site_url,
            "total_sources_found": len(sources),
            "sources": sources,
        }
    except Exception as e:
        return {
            "domain": domain,
            "site_url": site_url,
            "total_sources_found": 0,
            "sources": [],
            "error": str(e),
        }


@mcp.tool()
async def configure_api_instance(base_url: Optional[str] = None) -> dict:
    """Retrieve or describe the current configuration of the Favicon API instance."""
    effective_base = normalize_base_url(base_url or BASE_URL)

    # First check health to confirm the service is up
    health_result = {}
    config_data = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check health
            health_resp = await client.get(f"{effective_base}/health")
            if health_resp.status_code == 200:
                try:
                    health_result = health_resp.json()
                except Exception:
                    health_result = {"raw": health_resp.text}

            # Try common config/info endpoints
            for endpoint in ["/config", "/info", "/settings", "/status"]:
                try:
                    resp = await client.get(f"{effective_base}{endpoint}")
                    if resp.status_code == 200:
                        try:
                            config_data[endpoint] = resp.json()
                        except Exception:
                            config_data[endpoint] = resp.text
                except Exception:
                    pass

    except Exception as e:
        return {
            "base_url": effective_base,
            "service_reachable": False,
            "error": str(e),
            "known_configuration": _get_known_config_docs(),
        }

    return {
        "base_url": effective_base,
        "service_reachable": bool(health_result),
        "health": health_result,
        "config_endpoints": config_data,
        "known_configuration": _get_known_config_docs(),
    }


def _get_known_config_docs() -> dict:
    """Return documented configuration options for the Favicon API."""
    return {
        "environment_variables": {
            "PORT": {"default": "3000", "description": "Server port"},
            "HOST": {"default": "0.0.0.0", "description": "Server host"},
            "DEFAULT_IMAGE_URL": {"default": None, "description": "URL of default image when no favicon found"},
            "USE_FALLBACK_API": {"default": "true", "description": "Use Google favicon API as fallback"},
            "CACHE_CONTROL_SUCCESS": {"default": "604800", "description": "Cache duration for successful responses (seconds)"},
            "CACHE_CONTROL_ERROR": {"default": "604800", "description": "Cache duration for error responses (seconds)"},
            "REQUEST_TIMEOUT": {"default": "5000", "description": "Timeout for external requests (ms)"},
            "MAX_IMAGE_SIZE": {"default": "5242880", "description": "Maximum image fetch size (bytes, default 5MB)"},
            "ALLOWED_ORIGINS": {"default": "*", "description": "CORS allowed origins"},
            "BLOCK_PRIVATE_IPS": {"default": "true", "description": "Block SSRF via private IP ranges"},
            "MAX_REDIRECTS": {"default": "5", "description": "Maximum redirects to follow"},
        },
        "api_parameters": {
            "size": "Desired favicon size in pixels (16-512)",
            "format": "Output format: png, jpg, webp, ico, svg",
            "response": "Response type: image (default) or json",
            "default": "Fallback image URL (overrides server config)",
        },
    }


@mcp.tool()
async def validate_domain(domain: str) -> dict:
    """Validate whether a given domain or URL is acceptable for favicon fetching."""
    issues = []
    warnings = []
    is_valid = True

    # Normalize
    original_input = domain
    if not domain.startswith("http://") and not domain.startswith("https://"):
        check_url = f"https://{domain}"
    else:
        check_url = domain

    # Parse URL
    try:
        parsed = urlparse(check_url)
    except Exception as e:
        return {
            "domain": original_input,
            "is_valid": False,
            "issues": [f"Failed to parse URL: {e}"],
            "warnings": [],
            "normalized_url": None,
        }

    # Check scheme
    if parsed.scheme not in ("http", "https"):
        issues.append(f"Invalid scheme '{parsed.scheme}'. Only http and https are supported.")
        is_valid = False

    # Check host
    host = parsed.hostname or ""
    if not host:
        issues.append("No hostname found in the domain/URL.")
        is_valid = False
    else:
        # Check for private IP ranges (SSRF protection)
        private_ip_patterns = [
            r"^127\.",           # loopback
            r"^10\.",            # private class A
            r"^192\.168\.",      # private class C
            r"^172\.(1[6-9]|2[0-9]|3[01])\.",  # private class B
            r"^169\.254\.",      # link-local
            r"^::1$",            # IPv6 loopback
            r"^fc00:",           # IPv6 private
            r"^fe80:",           # IPv6 link-local
            r"^0\.",             # 0.x.x.x
            r"^255\.",           # broadcast
            r"^localhost$",      # localhost
        ]
        for pattern in private_ip_patterns:
            if re.match(pattern, host, re.IGNORECASE):
                issues.append(f"Host '{host}' appears to be a private/reserved IP address. This would be blocked by SSRF protection (BLOCK_PRIVATE_IPS=true).")
                is_valid = False
                break

        # Check for numeric IP (not necessarily private)
        ip_pattern = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
        if ip_pattern.match(host) and is_valid:
            warnings.append(f"Host '{host}' is a raw IP address. Some configurations may block IP-based requests.")

        # Check domain has a TLD (basic check)
        if "." not in host and not ip_pattern.match(host) and host != "localhost":
            warnings.append(f"Host '{host}' does not appear to have a TLD. This may not be a valid public domain.")

    # Try reachability via the Favicon API
    reachability = None
    if is_valid:
        try:
            test_url = build_favicon_url(domain, None, None, BASE_URL)
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                response = await client.get(test_url)
                reachability = {
                    "status_code": response.status_code,
                    "reachable": response.status_code in (200, 301, 302, 304),
                    "content_type": response.headers.get("content-type", ""),
                }
        except Exception as e:
            reachability = {
                "reachable": False,
                "error": str(e),
            }

    return {
        "domain": original_input,
        "normalized_url": check_url if is_valid else None,
        "is_valid": is_valid,
        "issues": issues,
        "warnings": warnings,
        "reachability_test": reachability,
        "recommendation": (
            "Domain appears valid and should work with the Favicon API."
            if is_valid and not issues
            else "Domain has issues that may prevent successful favicon fetching."
        ),
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
