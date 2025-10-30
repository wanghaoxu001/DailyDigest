import asyncio
import re
from typing import Optional, Dict

import requests
from bs4 import BeautifulSoup

try:
    # Playwright 是可选的，若环境未安装浏览器，也能仅用 requests 退化运行
    from playwright.async_api import async_playwright  # type: ignore
    HAS_PLAYWRIGHT = True
except Exception:  # pragma: no cover
    HAS_PLAYWRIGHT = False


# 基础浏览器头，尽量贴近真实浏览器
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
}


def _is_cloudflare_interstitial(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"Just a moment\.",
        r"Checking your browser before accessing",
        r"Attention Required! \| Cloudflare",
        r"Please enable JavaScript and cookies to continue",
    ]
    for p in patterns:
        if re.search(p, text, flags=re.I):
            return True
    return False


def _strip_noise_tags(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    # 结构性噪声
    for sel in [
        "header",
        "footer",
        "nav",
        "aside",
        ".sidebar",
        ".ads, .advert, .advertisement",
        "#sidebar",
        "#comments",
    ]:
        for node in soup.select(sel):
            try:
                node.decompose()
            except Exception:
                pass


def _choose_main_container(soup: BeautifulSoup) -> BeautifulSoup:
    candidates = [
        "article",
        "main",
        "#content",
        ".content",
        ".article",
        ".post",
        ".post-content",
        ".entry-content",
        ".rich_media_content",  # 微信
        "#js_content",  # 微信
    ]
    for sel in candidates:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 200:
            return node
    # 回退：选择文本最多的 div
    best_node = soup.body or soup
    max_len = 0
    for div in soup.find_all(["div", "section", "article"]):
        text_len = len(div.get_text(strip=True))
        if text_len > max_len:
            max_len = text_len
            best_node = div
    return best_node


def _extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    return ""


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _requests_fetch_html(url: str, timeout: int = 20) -> Optional[str]:
    try:
        with requests.Session() as s:
            s.headers.update(BROWSER_HEADERS)
            resp = s.get(url, timeout=timeout)
            if resp.status_code >= 400:
                return None
            text = resp.text or ""
            if _is_cloudflare_interstitial(text):
                return None
            return text
    except Exception:
        return None


async def _playwright_fetch_html(url: str, timeout_ms: int = 30000) -> Optional[str]:
    if not HAS_PLAYWRIGHT:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=BROWSER_HEADERS["User-Agent"])  # type: ignore
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # 一些页面需要额外等待资源或延迟渲染
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            html = await page.content()
            await context.close()
            await browser.close()
            if _is_cloudflare_interstitial(html):
                return None
            return html
    except Exception:
        return None


def _parse_html_to_text(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    _strip_noise_tags(soup)
    container = _choose_main_container(soup)
    title = _extract_title(soup)
    text = container.get_text(separator=" ", strip=True)
    text = _clean_text(text)
    return {"title": title, "content": text}


async def crawl_article_content(url: str, timeout_ms: int = 30000) -> Optional[Dict[str, str]]:
    """
    通用文章爬虫：优先 requests，失败或不足再回退 Playwright。

    Returns: {"title": str, "content": str, "url": str, "success": bool}
    """
    # 1) requests 优先
    html = _requests_fetch_html(url)
    if html:
        parsed = _parse_html_to_text(html)
        if len(parsed.get("content", "")) >= 200:
            return {
                "title": parsed.get("title", ""),
                "content": parsed.get("content", ""),
                "url": url,
                "success": True,
            }

    # 2) 回退 Playwright（如可用）
    html = await _playwright_fetch_html(url, timeout_ms=timeout_ms)
    if html:
        parsed = _parse_html_to_text(html)
        if len(parsed.get("content", "")) >= 200:
            return {
                "title": parsed.get("title", ""),
                "content": parsed.get("content", ""),
                "url": url,
                "success": True,
            }

    return None



