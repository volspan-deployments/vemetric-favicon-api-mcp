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
async def get_favicon(domain: str, size: Optional[int] = None, format: Optional[str] = None) -> dict:
    """Fetch a favicon for a given domain or URL. This is the primary tool — use it whenever you need to retrieve, display, or check the favicon for any website. Supports format conversion and resizing on-the-fly."""
    params = {}
    if size is not None:
        params["size"] = size
    if format is not None:
        params["format"] = format
    params["response"] = "json"

    url = f"{BASE_URL}/{domain}"

    async with httpx.AsyncClient(timeout=30.0) as client:
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
                    # Binary image response
                    image_b64 = base64.b64encode(response.content).decode("utf-8")
                    return {
                        "success": True,
                        "domain": domain,
                        "status_code": response.status_code,
                        "content_type": content_type,
                        "image_base64": image_b64,
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
    """Check the health and availability of the Favicon API service. Use this to verify the service is running before making other requests, or to monitor uptime."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                return {
                    "healthy": True,
                    "status_code": response.status_code,
                    "data": response.json()
                }
            else:
                return {
                    "healthy": False,
                    "status_code": response.status_code,
                    "error": response.text
                }
        except httpx.RequestError as e:
            return {
                "healthy": False,
                "error": str(e),
                "message": "Could not connect to the Favicon API service"
            }


@mcp.tool()
async def fetch_favicon_with_fallback(
    domain: str,
    use_fallback_api: bool = True,
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch a favicon for a domain with explicit control over fallback behavior. Use this when you want to handle bot-protected sites or need a guaranteed response — either from the primary source, Google's favicon API fallback, or a default image."""
    params = {"response": "json"}
    if size is not None:
        params["size"] = size
    if format is not None:
        params["format"] = format

    url = f"{BASE_URL}/{domain}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, params=params)
            content_type = response.headers.get("content-type", "")

            if response.status_code == 200:
                if "application/json" in content_type:
                    result_data = response.json()
                else:
                    image_b64 = base64.b64encode(response.content).decode("utf-8")
                    result_data = {
                        "content_type": content_type,
                        "image_base64": image_b64,
                        "image_size_bytes": len(response.content)
                    }

                return {
                    "success": True,
                    "domain": domain,
                    "use_fallback_api": use_fallback_api,
                    "status_code": response.status_code,
                    "data": result_data
                }
            else:
                result = {
                    "success": False,
                    "domain": domain,
                    "status_code": response.status_code,
                    "error": response.text
                }

                # If primary fails and fallback is enabled, try Google's favicon API
                if use_fallback_api:
                    google_size = size if size else 32
                    google_url = f"https://www.google.com/s2/favicons?domain={domain}&sz={google_size}"
                    try:
                        fallback_response = await client.get(google_url, follow_redirects=True)
                        if fallback_response.status_code == 200:
                            fallback_b64 = base64.b64encode(fallback_response.content).decode("utf-8")
                            result["fallback_used"] = True
                            result["fallback_source"] = "google"
                            result["fallback_data"] = {
                                "content_type": fallback_response.headers.get("content-type", ""),
                                "image_base64": fallback_b64,
                                "image_size_bytes": len(fallback_response.content)
                            }
                    except httpx.RequestError:
                        result["fallback_used"] = False
                        result["fallback_error"] = "Google fallback also failed"

                return result

        except httpx.RequestError as e:
            result = {
                "success": False,
                "domain": domain,
                "error": str(e)
            }

            if use_fallback_api:
                google_size = size if size else 32
                google_url = f"https://www.google.com/s2/favicons?domain={domain}&sz={google_size}"
                try:
                    async with httpx.AsyncClient(timeout=10.0) as fallback_client:
                        fallback_response = await fallback_client.get(google_url, follow_redirects=True)
                        if fallback_response.status_code == 200:
                            fallback_b64 = base64.b64encode(fallback_response.content).decode("utf-8")
                            result["fallback_used"] = True
                            result["fallback_source"] = "google"
                            result["fallback_data"] = {
                                "content_type": fallback_response.headers.get("content-type", ""),
                                "image_base64": fallback_b64,
                                "image_size_bytes": len(fallback_response.content)
                            }
                except httpx.RequestError:
                    result["fallback_used"] = False

            return result


@mcp.tool()
async def batch_get_favicons(
    domains: List[str],
    size: Optional[int] = None,
    format: Optional[str] = None
) -> dict:
    """Fetch favicons for multiple domains at once. Use this when you need to retrieve favicons for a list of websites efficiently, such as enriching a list of bookmarks or displaying icons in a dashboard."""
    params = {"response": "json"}
    if size is not None:
        params["size"] = size
    if format is not None:
        params["format"] = format

    results = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for domain in domains:
            url = f"{BASE_URL}/{domain}"
            try:
                response = await client.get(url, params=params)
                content_type = response.headers.get("content-type", "")

                if response.status_code == 200:
                    if "application/json" in content_type:
                        results.append({
                            "domain": domain,
                            "success": True,
                            "status_code": response.status_code,
                            "data": response.json()
                        })
                    else:
                        image_b64 = base64.b64encode(response.content).decode("utf-8")
                        results.append({
                            "domain": domain,
                            "success": True,
                            "status_code": response.status_code,
                            "content_type": content_type,
                            "image_base64": image_b64,
                            "image_size_bytes": len(response.content)
                        })
                else:
                    results.append({
                        "domain": domain,
                        "success": False,
                        "status_code": response.status_code,
                        "error": response.text
                    })
            except httpx.RequestError as e:
                results.append({
                    "domain": domain,
                    "success": False,
                    "error": str(e)
                })

    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful

    return {
        "total": len(domains),
        "successful": successful,
        "failed": failed,
        "results": results
    }


@mcp.tool()
async def validate_domain(domain: str) -> dict:
    """Validate whether a given domain or URL is a valid, publicly accessible target for favicon fetching. Use this before fetching to avoid errors, or to check if a user-supplied domain is safe and well-formed."""
    import re
    import ipaddress

    result = {
        "domain": domain,
        "is_valid": False,
        "issues": []
    }

    # Strip protocol if present
    clean_domain = domain
    for prefix in ["https://", "http://"]:
        if clean_domain.startswith(prefix):
            clean_domain = clean_domain[len(prefix):]
            break
    clean_domain = clean_domain.split("/")[0].split("?")[0]

    if not clean_domain:
        result["issues"].append("Empty domain")
        return result

    # Check if it's an IP address
    try:
        ip = ipaddress.ip_address(clean_domain)
        if ip.is_private:
            result["issues"].append("Private IP addresses are not allowed (SSRF protection)")
            result["is_private_ip"] = True
            return result
        elif ip.is_loopback:
            result["issues"].append("Loopback addresses are not allowed")
            return result
        elif ip.is_link_local:
            result["issues"].append("Link-local addresses are not allowed")
            return result
        else:
            result["is_valid"] = True
            result["is_ip_address"] = True
            result["clean_domain"] = clean_domain
            return result
    except ValueError:
        pass  # Not an IP, continue with domain validation

    # Basic domain format validation
    domain_regex = re.compile(
        r'^(?:[a-zA-Z0-9]'
        r'(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
        r'\.)+[a-zA-Z]{2,}$'
    )

    if not domain_regex.match(clean_domain):
        result["issues"].append(f"'{clean_domain}' does not appear to be a valid domain name")
        return result

    # Check for localhost
    if clean_domain.lower() in ["localhost", "localhost.localdomain"]:
        result["issues"].append("Localhost is not allowed")
        return result

    # Try to reach the domain via the API
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            test_url = f"{BASE_URL}/{clean_domain}"
            response = await client.get(test_url, params={"response": "json"})
            result["is_valid"] = True
            result["clean_domain"] = clean_domain
            result["reachable"] = response.status_code != 404
            result["api_status_code"] = response.status_code
            result["message"] = "Domain is valid and was tested against the API"
        except httpx.RequestError as e:
            result["is_valid"] = True  # Domain format is valid even if API is unreachable
            result["clean_domain"] = clean_domain
            result["reachable"] = None
            result["api_error"] = str(e)
            result["message"] = "Domain format is valid but API could not be reached for reachability check"

    return result


@mcp.tool()
async def get_favicon_url(
    domain: str,
    size: Optional[int] = None,
    format: Optional[str] = None,
    base_url: str = "http://localhost:3000"
) -> dict:
    """Build and return the full API URL for fetching a favicon without actually downloading the image. Use this when you need to embed a favicon image URL in HTML, markdown, or a UI component rather than fetching the binary content."""
    effective_base = base_url.rstrip("/")

    params = []
    if size is not None:
        params.append(f"size={size}")
    if format is not None:
        params.append(f"format={format}")

    query_string = "&".join(params)
    favicon_url = f"{effective_base}/{domain}"
    if query_string:
        favicon_url = f"{favicon_url}&{query_string}"

    html_tag = f'<img src="{favicon_url}" alt="{domain} favicon"'
    if size:
        html_tag += f' width="{size}" height="{size}"'
    html_tag += ' />'

    markdown_img = f'![{domain} favicon]({favicon_url})'

    return {
        "domain": domain,
        "favicon_url": favicon_url,
        "base_url": effective_base,
        "parameters": {
            "size": size,
            "format": format
        },
        "html_tag": html_tag,
        "markdown": markdown_img
    }


@mcp.tool()
async def inspect_favicon_sources(domain: str) -> dict:
    """Discover and list all favicon sources found for a given domain (e.g. from HTML link tags, /favicon.ico, Apple touch icons, manifests). Use this when you want to understand what favicon options a site exposes, or debug why a favicon is not loading correctly."""
    sources = []
    issues = []

    # Strip protocol
    clean_domain = domain
    for prefix in ["https://", "http://"]:
        if clean_domain.startswith(prefix):
            clean_domain = clean_domain[len(prefix):]
            break
    clean_domain = clean_domain.split("/")[0]

    base_site_url = f"https://{clean_domain}"

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={"User-Agent": "FaviconAPI/1.0"}
    ) as client:
        # 1. Try fetching the HTML page to find link tags
        try:
            html_response = await client.get(base_site_url)
            if html_response.status_code == 200:
                content = html_response.text

                # Find standard favicon link tags
                import re
                link_pattern = re.compile(
                    r'<link[^>]+rel=["\']([^"\']*icon[^"\']*)["\'][^>]*href=["\']([^"\']+)["\'][^>]*/?>',
                    re.IGNORECASE
                )
                href_first_pattern = re.compile(
                    r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']([^"\']*icon[^"\']*)["\'][^>]*/?>',
                    re.IGNORECASE
                )

                for match in link_pattern.finditer(content):
                    rel, href = match.group(1), match.group(2)
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = base_site_url + href
                    sources.append({
                        "type": "html_link_tag",
                        "rel": rel,
                        "url": href
                    })

                for match in href_first_pattern.finditer(content):
                    href, rel = match.group(1), match.group(2)
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = base_site_url + href
                    # Avoid duplicates
                    if not any(s["url"] == href for s in sources):
                        sources.append({
                            "type": "html_link_tag",
                            "rel": rel,
                            "url": href
                        })

                # Check for manifest
                manifest_pattern = re.compile(
                    r'<link[^>]+rel=["\']manifest["\'][^>]*href=["\']([^"\']+)["\']',
                    re.IGNORECASE
                )
                for match in manifest_pattern.finditer(content):
                    manifest_href = match.group(1)
                    if manifest_href.startswith("/"):
                        manifest_href = base_site_url + manifest_href
                    sources.append({
                        "type": "web_manifest",
                        "url": manifest_href,
                        "note": "Web app manifest may contain icon definitions"
                    })
            else:
                issues.append(f"Could not fetch HTML page: HTTP {html_response.status_code}")
        except httpx.RequestError as e:
            issues.append(f"Could not fetch HTML page: {str(e)}")

        # 2. Check /favicon.ico directly
        favicon_ico_url = f"{base_site_url}/favicon.ico"
        try:
            ico_response = await client.head(favicon_ico_url)
            sources.append({
                "type": "standard_favicon_ico",
                "url": favicon_ico_url,
                "accessible": ico_response.status_code == 200,
                "status_code": ico_response.status_code,
                "content_type": ico_response.headers.get("content-type", "unknown")
            })
        except httpx.RequestError as e:
            sources.append({
                "type": "standard_favicon_ico",
                "url": favicon_ico_url,
                "accessible": False,
                "error": str(e)
            })

        # 3. Check /apple-touch-icon.png
        apple_icon_url = f"{base_site_url}/apple-touch-icon.png"
        try:
            apple_response = await client.head(apple_icon_url)
            sources.append({
                "type": "apple_touch_icon",
                "url": apple_icon_url,
                "accessible": apple_response.status_code == 200,
                "status_code": apple_response.status_code
            })
        except httpx.RequestError as e:
            sources.append({
                "type": "apple_touch_icon",
                "url": apple_icon_url,
                "accessible": False,
                "error": str(e)
            })

        # 4. Fetch what the Favicon API itself resolves to
        try:
            api_url = f"{BASE_URL}/{clean_domain}"
            api_response = await client.get(api_url, params={"response": "json"})
            sources.append({
                "type": "favicon_api_resolved",
                "url": api_url,
                "status_code": api_response.status_code,
                "api_resolved": api_response.status_code == 200,
                "data": api_response.json() if "application/json" in api_response.headers.get("content-type", "") else None
            })
        except httpx.RequestError as e:
            issues.append(f"Could not query Favicon API: {str(e)}")

    accessible_count = sum(1 for s in sources if s.get("accessible") is True or s.get("api_resolved") is True)

    return {
        "domain": clean_domain,
        "base_url": base_site_url,
        "total_sources_found": len(sources),
        "accessible_sources": accessible_count,
        "sources": sources,
        "issues": issues
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
