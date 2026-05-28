"""Web page fetcher that returns markdown content with timeout/size limits."""

import re

from .base import ToolExecutor

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

try:
    import html2text
except ImportError:
    html2text = None  # type: ignore[assignment]


class WebFetchExecutor(ToolExecutor):
    """Fetch a URL and return its content converted to Markdown.

    Uses ``httpx`` for HTTP requests and ``html2text`` for HTML-to-Markdown
    conversion.  Falls back to plain text extraction if ``html2text`` is
    not installed.
    """

    DEFAULT_TIMEOUT = 30.0  # seconds
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_RESPONSE_CHARS = 1_000_000  # prevent giant markdown strings

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a URL and convert it to Markdown. "
            "Supports timeout (seconds) and size limits."
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        url: str = ""
        if args:
            url = args.get("url", "")
        if not url:
            return {"url": "", "markdown": "", "success": False, "error": "No url provided"}

        timeout: float = args.get("timeout", self.DEFAULT_TIMEOUT)

        if httpx is None:
            return {
                "url": url,
                "markdown": "",
                "success": False,
                "error": "httpx is not installed; run `pip install httpx`",
            }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "HermesAgent/1.0 (NousResearch; +https://hermes-agent.nousresearch.com)"
                    ),
                },
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Enforce size limit on raw content
                content_bytes = response.content
                if len(content_bytes) > self.MAX_RESPONSE_SIZE:
                    return {
                        "url": url,
                        "markdown": "",
                        "success": False,
                        "error": (
                            f"Response too large: {len(content_bytes)} bytes "
                            f"(limit {self.MAX_RESPONSE_SIZE})"
                        ),
                    }

                content_type = response.headers.get("content-type", "")
                html = response.text

        except httpx.TimeoutException:
            return {
                "url": url,
                "markdown": "",
                "success": False,
                "error": f"Request timed out after {timeout}s",
            }
        except httpx.HTTPStatusError as exc:
            return {
                "url": url,
                "markdown": "",
                "success": False,
                "error": f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
            }
        except httpx.RequestError as exc:
            return {
                "url": url,
                "markdown": "",
                "success": False,
                "error": f"Request failed: {exc}",
            }

        # Convert to Markdown
        markdown = self._to_markdown(html, content_type, url)

        # Enforce character limit on output
        if len(markdown) > self.MAX_RESPONSE_CHARS:
            markdown = markdown[: self.MAX_RESPONSE_CHARS]
            markdown += (
                f"\n\n**... truncated at {self.MAX_RESPONSE_CHARS} characters **"
            )

        return {
            "url": url,
            "markdown": markdown,
            "success": True,
            "content_type": content_type,
        }

    # ------------------------------------------------------------------
    # HTML -> Markdown conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_markdown(html: str, content_type: str, url: str) -> str:
        """Convert HTML to Markdown, falling back to plain text if needed."""
        if html2text is not None and ("html" in content_type or not content_type):
            converter = html2text.HTML2Text()
            converter.body_width = 0  # no wrapping
            converter.ignore_links = False
            converter.ignore_images = False
            converter.ignore_emphasis = False
            converter.ignore_tables = False
            converter.mark_code = True
            return converter.handle(html)

        # Fallback: strip tags
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        pass

    async def on_complete(self, result: dict) -> None:
        pass
