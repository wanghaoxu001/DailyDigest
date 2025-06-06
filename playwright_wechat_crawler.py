import asyncio
from playwright.async_api import async_playwright, TimeoutError
import os
import time
import random
import json
from datetime import datetime
from typing import Dict, Any, Optional, List


class WechatArticleCrawler:
    """微信公众号文章爬虫类"""

    def __init__(
        self,
        headless: bool = True,
        image_enabled: bool = True,
        timeout: int = 60000,
        retry_times: int = 2,
        user_agent: Optional[str] = None,
    ):
        """
        初始化爬虫

        Args:
            headless: 是否使用无头模式
            image_enabled: 是否加载图片
            timeout: 超时时间(毫秒)
            retry_times: 重试次数
            user_agent: 自定义User-Agent
        """
        self.headless = headless
        self.image_enabled = image_enabled
        self.timeout = timeout
        self.retry_times = retry_times

        # 随机选择一个User-Agent
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        ]
        self.user_agent = user_agent or random.choice(self.user_agents)

        # 输出目录
        self.output_dir = "wechat_articles"
        os.makedirs(self.output_dir, exist_ok=True)

    async def crawl_article(self, url: str) -> Dict[str, Any]:
        """
        爬取微信公众号文章

        Args:
            url: 微信公众号文章链接

        Returns:
            dict: 包含标题、作者、正文内容、图片等信息的字典
        """
        # 为每个URL创建唯一的文件名前缀
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url_id = url.split("/")[-1].split("?")[0]
        file_prefix = f"{timestamp}_{url_id[:8]}"

        # 重试机制
        for attempt in range(self.retry_times + 1):
            if attempt > 0:
                print(f"第 {attempt} 次重试...")
                # 每次重试增加随机等待时间
                await asyncio.sleep(2 + random.random() * 3)

            try:
                return await self._crawl_with_playwright(url, file_prefix)
            except Exception as e:
                print(f"第 {attempt+1}/{self.retry_times+1} 次尝试失败: {str(e)}")
                if attempt == self.retry_times:
                    # 最后一次尝试失败，返回错误信息
                    return {
                        "title": "爬取失败",
                        "author": "爬取失败",
                        "content": f"多次尝试后爬取失败: {str(e)}",
                        "url": url,
                        "crawl_time": datetime.now().isoformat(),
                        "success": False,
                    }

    async def _crawl_with_playwright(
        self, url: str, file_prefix: str
    ) -> Dict[str, Any]:
        """使用Playwright实现具体的爬取逻辑"""
        async with async_playwright() as p:
            # 浏览器启动参数
            browser_args = []
            if self.image_enabled is False:
                browser_args.append("--disable-images")

            # 启动浏览器
            browser = await p.chromium.launch(headless=self.headless, args=browser_args)

            # 创建浏览器上下文
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1.5,  # 高DPI显示
                java_script_enabled=True,
                locale="zh-CN",  # 设置中文环境
                timezone_id="Asia/Shanghai",  # 设置中国时区
                geolocation={"latitude": 39.9042, "longitude": 116.4074},  # 北京位置
                permissions=["geolocation"],
                is_mobile=False,
            )

            # 创建新页面
            page = await context.new_page()

            try:
                # 模拟真实浏览行为的预处理
                await self._simulate_real_browser(page)

                # 访问URL
                print(f"正在访问链接: {url}")
                try:
                    # 先使用domcontentloaded，加快首次加载速度
                    await page.goto(
                        url, wait_until="domcontentloaded", timeout=self.timeout
                    )

                    # 等待关键元素出现
                    try:
                        print("等待页面标题元素加载...")
                        await page.wait_for_selector(
                            "#activity-name, .rich_media_title", timeout=10000
                        )
                        print("页面标题已加载")
                    except TimeoutError:
                        print("标题元素加载超时，尝试继续处理...")

                    # 模拟用户滚动
                    await self._simulate_reading(page)

                except TimeoutError as e:
                    print(f"页面加载超时: {str(e)}")
                    # 即使超时，也尝试获取已加载的内容

                # 检查是否遇到验证码页面
                if await self._is_verification_page(page):
                    result = await self._handle_verification(page, file_prefix)
                    await browser.close()
                    return result

                # 提取文章内容
                return await self._extract_content(page, url, file_prefix)

            except Exception as e:
                print(f"爬取过程中发生错误: {str(e)}")
                try:
                    # 保存出错页面
                    error_screenshot = os.path.join(
                        self.output_dir, f"{file_prefix}_error.png"
                    )
                    await page.screenshot(path=error_screenshot, full_page=True)

                    error_html_path = os.path.join(
                        self.output_dir, f"{file_prefix}_error.html"
                    )
                    error_html = await page.content()
                    with open(error_html_path, "w", encoding="utf-8") as f:
                        f.write(error_html)

                    print(f"已保存错误页面截图和HTML到 {self.output_dir} 目录")

                    # 尝试从错误页面提取内容
                    try:
                        return await self._extract_content_from_error_page(
                            page, url, file_prefix
                        )
                    except Exception as extract_error:
                        print(f"从错误页面提取内容失败: {str(extract_error)}")
                        raise e
                except:
                    print("保存错误页面失败")
                    raise e
            finally:
                await browser.close()

    async def _simulate_real_browser(self, page):
        """模拟真实浏览器行为"""
        # 设置请求拦截
        await page.route("**/*", self._route_intercept)

        # 设置一些浏览器特性
        await page.evaluate(
            """
        () => {
            // 添加一些常见浏览器特性
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        }
        """
        )

    async def _route_intercept(self, route):
        """请求拦截处理"""
        # 可以在这里对请求进行过滤、修改或阻止
        # 例如，阻止追踪脚本、广告等
        await route.continue_()

    async def _simulate_reading(self, page):
        """模拟用户阅读行为"""
        # 慢慢滚动页面，模拟阅读
        await page.evaluate(
            """
        () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                let distance = 100;
                let timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    
                    if(totalHeight >= document.body.scrollHeight * 0.8){
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
        """
        )

        # 随机暂停，模拟阅读
        await page.wait_for_timeout(1000 + random.random() * 2000)

    async def _is_verification_page(self, page) -> bool:
        """检查是否是验证码页面"""
        page_content = await page.content()
        verification_keywords = [
            "当前环境异常，完成验证后即可继续访问",
            "按住验证码",
            "滑动验证码",
            "安全验证",
        ]

        for keyword in verification_keywords:
            if keyword in page_content:
                return True

        return False

    async def _handle_verification(self, page, file_prefix: str) -> Dict[str, Any]:
        """处理验证码页面"""
        print("警告：遇到验证码页面！需要人工处理")

        # 截图保存
        screenshot_path = os.path.join(
            self.output_dir, f"{file_prefix}_verification.png"
        )
        await page.screenshot(path=screenshot_path, full_page=True)

        # 保存HTML
        html_path = os.path.join(self.output_dir, f"{file_prefix}_verification.html")
        verification_html = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(verification_html)

        print(f"已保存验证码截图和HTML到 {self.output_dir} 目录")

        # 如果不是无头模式，可以等待用户手动处理验证码
        if not self.headless:
            print("请在浏览器中完成验证，完成后按Enter继续...")
            # 在实际使用中，这里需要一个用户输入机制
            # 现在我们只等待一段时间
            await page.wait_for_timeout(30000)  # 等待30秒

            # 检查验证是否完成
            if not await self._is_verification_page(page):
                print("验证完成，继续提取内容")
                return await self._extract_content(page, "", file_prefix)

        return {
            "title": "验证页面",
            "author": "验证页面",
            "content": "遇到验证码页面，无法获取内容",
            "url": await page.url(),
            "crawl_time": datetime.now().isoformat(),
            "success": False,
        }

    async def _extract_content(
        self, page, url: str, file_prefix: str
    ) -> Dict[str, Any]:
        """提取文章内容"""
        print("开始提取文章内容...")

        # 获取文章标题
        title = await self._extract_title(page)

        # 获取作者信息
        author = await self._extract_author(page)

        # 获取发布时间
        publish_time = await self._extract_publish_time(page)

        # 获取文章内容
        content, html_content = await self._extract_article_content(page)

        # 获取图片链接
        images = await self._extract_images(page)

        # 保存截图
        screenshot_path = os.path.join(self.output_dir, f"{file_prefix}_full.png")
        await page.screenshot(path=screenshot_path, full_page=True)

        # 保存HTML源码
        html_path = os.path.join(self.output_dir, f"{file_prefix}_article.html")
        page_content = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page_content)

        # 保存提取的数据为JSON
        result = {
            "title": title,
            "author": author,
            "publish_time": publish_time,
            "content": content,
            "html_content": html_content,
            "images": images,
            "url": url or await page.url(),
            "crawl_time": datetime.now().isoformat(),
            "success": True,
        }

        # 保存结果到JSON文件
        json_path = os.path.join(self.output_dir, f"{file_prefix}_data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"文章内容已提取并保存到 {self.output_dir} 目录")
        return result

    async def _extract_content_from_error_page(
        self, page, url: str, file_prefix: str
    ) -> Dict[str, Any]:
        """从错误页面提取可能的内容"""
        print("尝试从错误页面提取内容...")

        try:
            # 首先检查页面是否有内容
            title = await self._extract_title(page)

            # 如果能提取到标题，说明页面可能已经加载了一部分内容
            if title and title != "无法获取标题":
                print(f"从错误页面提取到标题: {title}")
                return await self._extract_content(page, url, file_prefix)
        except:
            pass

        # 如果无法提取内容，返回错误信息
        return {
            "title": "无法提取内容",
            "author": "无法提取内容",
            "content": "页面加载不完整，无法提取有效内容",
            "url": url or await page.url(),
            "crawl_time": datetime.now().isoformat(),
            "success": False,
        }

    async def _extract_title(self, page) -> str:
        """提取文章标题"""
        try:
            # 尝试多个可能的标题选择器
            selectors = ["#activity-name", ".rich_media_title", "h1"]

            for selector in selectors:
                title_element = await page.query_selector(selector)
                if title_element:
                    title = await title_element.inner_text()
                    title = title.strip()
                    if title:
                        return title

            return "无法获取标题"
        except:
            return "无法获取标题"

    async def _extract_author(self, page) -> str:
        """提取作者信息"""
        try:
            # 尝试多个可能的作者选择器
            selectors = ["#js_name", ".rich_media_meta_text", ".profile_nickname"]

            for selector in selectors:
                author_element = await page.query_selector(selector)
                if author_element:
                    author = await author_element.inner_text()
                    author = author.strip()
                    if author:
                        return author

            return "未知作者"
        except:
            return "未知作者"

    async def _extract_publish_time(self, page) -> str:
        """提取发布时间"""
        try:
            # 尝试多个可能的时间选择器
            selectors = ["#publish_time", ".rich_media_meta_text", ".publish_time"]

            for selector in selectors:
                time_element = await page.query_selector(selector)
                if time_element:
                    publish_time = await time_element.inner_text()
                    publish_time = publish_time.strip()
                    if publish_time:
                        return publish_time

            return ""
        except:
            return ""

    async def _extract_article_content(self, page) -> tuple:
        """提取文章内容文本和HTML"""
        try:
            # 内容选择器
            content_selectors = ["#js_content", ".rich_media_content"]

            for selector in content_selectors:
                content_element = await page.query_selector(selector)
                if content_element:
                    # 获取文本内容
                    text_content = await content_element.inner_text()

                    # 获取HTML内容
                    html_content = await content_element.inner_html()

                    # 获取所有段落
                    paragraphs = await content_element.query_selector_all("p")

                    # 如果段落很少，尝试获取其他元素
                    if len(paragraphs) < 3:
                        # 尝试其他常见元素
                        paragraphs = await content_element.query_selector_all(
                            "p, section, div > span"
                        )

                    # 提取段落文本
                    content_list = []
                    for p in paragraphs:
                        p_text = await p.inner_text()
                        if p_text.strip():
                            content_list.append(p_text.strip())

                    # 如果能提取到段落内容，使用段落内容
                    if content_list:
                        return "\n\n".join(content_list), html_content
                    # 否则使用整个内容区域的文本
                    elif text_content.strip():
                        return text_content.strip(), html_content

            return "无法获取文章内容", ""
        except Exception as e:
            print(f"提取文章内容时出错: {str(e)}")
            return "无法获取文章内容", ""

    async def _extract_images(self, page) -> List[str]:
        """提取文章中的图片链接"""
        try:
            # 内容选择器
            content_selectors = ["#js_content", ".rich_media_content"]

            for selector in content_selectors:
                content_element = await page.query_selector(selector)
                if content_element:
                    # 获取所有图片元素
                    img_elements = await content_element.query_selector_all("img")

                    # 提取图片URL
                    image_urls = []
                    for img in img_elements:
                        # 尝试不同的属性获取图片URL
                        for attr in ["src", "data-src", "data-original"]:
                            img_url = await img.get_attribute(attr)
                            if img_url and img_url.startswith(("http://", "https://")):
                                image_urls.append(img_url)
                                break

                    return image_urls

            return []
        except:
            return []


async def main():
    """主函数"""
    # 创建爬虫实例
    crawler = WechatArticleCrawler(
        headless=True,  # 设置为False可显示浏览器界面，方便调试
        image_enabled=True,  # 是否加载图片
        timeout=60000,  # 超时时间
        retry_times=2,  # 重试次数
    )

    # 目标微信公众号文章URL
    article_url = "https://mp.weixin.qq.com/s/gkt_xlO5FFqdNj6Z12hAaQ"

    print(f"开始爬取微信文章: {article_url}")
    result = await crawler.crawl_article(article_url)

    print("\n" + "=" * 50)
    print(f"标题: {result['title']}")
    print(f"作者: {result['author']}")
    if "publish_time" in result and result["publish_time"]:
        print(f"发布时间: {result['publish_time']}")

    print("=" * 50)
    print(result["content"])

    print("=" * 50)
    print("文章抓取结果已保存到 wechat_articles 目录")


# 运行异步主函数
if __name__ == "__main__":
    asyncio.run(main())
