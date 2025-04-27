import requests
from bs4 import BeautifulSoup
import feedparser
import re
import logging
import csv
import os
import random
import time
from typing import Optional, Tuple, Dict, List, Any
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import functools
import hashlib
import json
import urllib

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def setup_logging():
    """初始化日志配置，每次运行清空日志文件"""
    log_file = 'paper_downloader.log'

    # 清空文件内容（如果文件存在）
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            pass  # 打开文件并立即关闭以清空内容
    except Exception as e:
        print(f"⚠️ 无法清空日志文件: {str(e)}")

    # 配置日志（使用追加模式但文件已被清空）
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        encoding='gbk',
        force=True
    )

    # 添加控制台处理器
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    logging.info("🆕 程序启动，日志文件已清空")


class SciHubDownloader:
    DEFAULT_CONFIG = [
        {  # 默认配置示例
            "domain": "https://www.sci-hub.ru/",
            "selectors": {
                "input": "#request",
                "search_btn": "#enter > button",
                "download_btn": "#buttons > button",
                "unavailable": "#return > a"
            }
        },
        {  # 备用配置
            "domain": "https://www.sci-hub.se/",
            "selectors": {
                "input": "#request",
                "search_btn": "#enter > button",
                "download_btn": "#buttons > button",
                "unavailable": "#return > a"
            }
        }
    ]

    def __init__(self, headless=True):
        self.domain_config = self.DEFAULT_CONFIG
        self.current_domain_idx = 0
        self.driver = self._init_driver(headless)
        self.wait = WebDriverWait(self.driver, 20)

    def _init_driver(self, headless):
        """初始化浏览器配置（无头模式）"""
        chrome_options = webdriver.ChromeOptions()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        return webdriver.Chrome(options=chrome_options)

    def _switch_domain(self):
        """切换备用域名"""
        self.current_domain_idx = (self.current_domain_idx + 1) % len(self.domain_config)
        logging.debug(f"切换到备用域名: {self.current_domain()}")

    def current_domain(self):
        return self.domain_config[self.current_domain_idx]["domain"]

    def current_selectors(self):
        return self.domain_config[self.current_domain_idx]["selectors"]

    def _parse_pdf_url(self, soup):
        """解析PDF链接（与原有逻辑一致）"""
        try:
            if button := soup.find('button', {'id': 'save'}):
                if onclick := button.get('onclick'):
                    return onclick.split("'")[1]
            if iframe := soup.find('iframe') or soup.find('embed'):
                return iframe['src']
            if pdf_link := soup.find('a', href=re.compile(r'.*\.pdf$')):
                return pdf_link['href']
        except Exception:
            return None
        return None

    def fetch_pdf_url(self, title):
        """返回 (PDF链接, 错误信息)"""
        for _ in range(len(self.domain_config)):
            try:
                # 访问当前域名
                self.driver.get(self.current_domain())

                # 执行搜索
                input_box = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, self.current_selectors()["input"])
                    )
                )
                input_box.clear()
                input_box.send_keys(title)

                self.driver.find_element(
                    By.CSS_SELECTOR, self.current_selectors()["search_btn"]
                ).click()

                # 检查是否可用
                try:
                    self.wait.until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, self.current_selectors()["unavailable"])
                        )
                    )
                    self._switch_domain()
                    continue
                except TimeoutException:
                    pass

                # 解析PDF链接
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                if pdf_url := self._parse_pdf_url(soup):
                    # 处理相对路径
                    if not pdf_url.startswith('http'):
                        base_url = urllib.parse.urlparse(self.current_domain()).scheme + "://" + \
                                   urllib.parse.urlparse(self.current_domain()).netloc
                        pdf_url = urllib.parse.urljoin(base_url, pdf_url)
                    return pdf_url, None

            except Exception as e:
                logging.error(f"Selenium请求失败: {str(e)}")
                self._switch_domain()

        return None, "所有镜像尝试失败"

    def close(self):
        self.driver.quit()


class RequestCache:
    """简单的请求缓存类，避免对同一资源重复请求"""

    def __init__(self, cache_file='request_cache.json'):
        self.cache_file = cache_file
        self.cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except:
                self.cache = {}

    def _save_cache(self):
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f)

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value
        # 定期保存缓存
        if len(self.cache) % 10 == 0:
            self._save_cache()

    def __del__(self):
        self._save_cache()


class PaperDownloader:
    def __init__(self, max_workers=5):
        self.max_workers = max_workers
        self.scihub_urls = [
            "https://www.sci-hub.ru/",
            "https://www.sci-hub.se/",
            "https://sci-hub.box/",
            "https://sci-hub.red/",
            "https://sci-hub.al/",
            "https://www.sci-hub.ee/",
            "https://sci-hub.lu/",
            "https://www.sci-hub.ren/",
            "https://sci-hub.shop/",
            "https://sci-hub.vg/"
        ]
        # 将工作良好的镜像移到前面
        random.shuffle(self.scihub_urls)

        self.arxiv_api = "http://export.arxiv.org/api/query?search_query=ti:{}"
        self.crossref_api = "https://api.crossref.org/works?query.title={}"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://scholar.google.com/",
            "DNT": "1"
        }

        # 创建更可靠的session
        self.session = self._create_robust_session()
        self.cache = RequestCache()
        self.active_mirrors = []  # 跟踪工作良好的镜像

    def _create_robust_session(self):
        """创建具有自动重试功能的会话"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.headers)
        return session

    def _get_doi_from_title(self, title: str) -> Tuple[Optional[str], Optional[str]]:
        """返回 (DOI, 错误信息)"""
        # 检查缓存
        cache_key = f"doi:{hashlib.md5(title.encode()).hexdigest()}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached.get('doi'), cached.get('error')

        try:
            search_url = self.crossref_api.format(title.replace(' ', '+'))
            resp = self.session.get(search_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data['message']['items']:
                    doi = data['message']['items'][0]['DOI']
                    self.cache.set(cache_key, {'doi': doi, 'error': None})
                    return doi, None

            self.cache.set(cache_key, {'doi': None, 'error': "未找到DOI"})
            return None, "未找到DOI"
        except Exception as e:
            self.cache.set(cache_key, {'doi': None, 'error': f"CrossRef查询失败: {str(e)}"})
            return None, f"CrossRef查询失败: {str(e)}"

    def _fetch_arxiv(self, title: str) -> Tuple[Optional[str], Optional[str]]:
        """返回 (PDF链接, 错误信息)"""
        # 检查缓存
        cache_key = f"arxiv:{hashlib.md5(title.encode()).hexdigest()}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached.get('url'), cached.get('error')

        try:
            search_url = self.arxiv_api.format(title.replace(' ', '+'))
            resp = self.session.get(search_url, timeout=15)
            feed = feedparser.parse(resp.text)
            if feed.entries:
                for link in feed.entries[0].links:
                    if link.get('type') == 'application/pdf':
                        pdf_url = link.href.replace('http:', 'https:', 1)
                        self.cache.set(cache_key, {'url': pdf_url, 'error': None})
                        return pdf_url, None

            self.cache.set(cache_key, {'url': None, 'error': "未找到arXiv论文"})
            return None, "未找到arXiv论文"
        except Exception as e:
            self.cache.set(cache_key, {'url': None, 'error': f"arXiv检索失败: {str(e)}"})
            return None, f"arXiv检索失败: {str(e)}"

    def _fetch_scihub(self, search_param: str) -> Tuple[Optional[str], Optional[str]]:
        """返回 (PDF链接, 错误信息)"""
        # 首先尝试已知工作的镜像
        all_mirrors = self.active_mirrors.copy() + [m for m in self.scihub_urls if m not in self.active_mirrors]

        for base_url in all_mirrors:
            try:
                search_url = f"{base_url}/{search_param}"
                resp = self.session.get(search_url, timeout=20)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    if pdf_url := self._parse_scihub_pdf_url(soup):
                        # 添加到活跃镜像列表
                        if base_url not in self.active_mirrors:
                            self.active_mirrors.append(base_url)

                        if pdf_url.startswith('//'):
                            return f"https:{pdf_url}", None
                        if pdf_url.startswith('/'):
                            return f"{base_url.rstrip('/')}{pdf_url}", None
                        if not pdf_url.startswith(('http://', 'https://')):
                            return f"{base_url.rstrip('/')}/{pdf_url.lstrip('/')}", None
                        return pdf_url, None
                elif resp.status_code == 403:
                    logging.warning(f"镜像 {base_url} 触发反爬机制")

            except Exception as e:
                logging.debug(f"镜像 {base_url} 请求失败: {str(e)}")

            # 短暂等待后继续尝试下一个镜像
            time.sleep(random.uniform(0.5, 1.5))

        return None, "所有镜像均失败"

    def _parse_scihub_pdf_url(self, soup: BeautifulSoup) -> Optional[str]:
        try:
            if button := soup.find('button', {'id': 'save'}):
                if onclick := button.get('onclick'):
                    return onclick.split("'")[1]
            if iframe := soup.find('iframe') or soup.find('embed'):
                return iframe['src']
            if pdf_link := soup.find('a', href=re.compile(r'.*\.pdf$')):
                return pdf_link['href']
        except Exception:
            return None
        return None

    def _fetch_scihub_selenium(self, title: str) -> Tuple[Optional[str], Optional[str]]:
        """使用Selenium获取PDF链接"""
        try:
            downloader = SciHubDownloader(headless=True)
            pdf_url, error = downloader.fetch_pdf_url(title)
            downloader.close()
            return pdf_url, error
        except Exception as e:
            return None, f"Selenium获取失败: {str(e)}"

            # 短暂等待后继续尝试下一个镜像
            time.sleep(random.uniform(0.5, 1.5))

        return None, "所有镜像均失败"

    def _download_pdf(self, url: str, save_path: str) -> Tuple[bool, Optional[str]]:
        try:
            if url.startswith('//'):
                url = f"https:{url}"
            resp = self.session.get(url, stream=True, timeout=60)

            # 检查是否为PDF
            content_type = resp.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower() and resp.content[:4] != b'%PDF':
                return False, "下载内容不是PDF文件"

            if resp.status_code == 200:
                total_size = int(resp.headers.get('Content-Length', 0))

                if total_size > 0:
                    bar_format = "{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}"
                    desc = f"下载 {os.path.basename(save_path)[:20]}..."

                    with open(save_path, 'wb') as f, tqdm(
                            desc=desc,
                            total=total_size,
                            unit='B',
                            unit_scale=True,
                            bar_format=bar_format,
                            leave=False
                    ) as pbar:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                else:
                    with open(save_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                # 检查PDF文件大小
                if os.path.getsize(save_path) < 10000:  # 文件太小，可能不是完整PDF
                    with open(save_path, 'rb') as f:
                        content = f.read(100)
                        if not content.startswith(b'%PDF'):
                            os.remove(save_path)  # 删除无效文件
                            return False, "下载的文件不是有效的PDF"

                return True, None
            return False, f"下载失败 HTTP {resp.status_code}"
        except Exception as e:
            if os.path.exists(save_path):
                os.remove(save_path)  # 清理部分下载的文件
            return False, f"下载异常: {str(e)}"

    def download_by_title(self, title: str, save_path: str, retries=3) -> dict:
        """返回包含完整状态信息的字典"""
        result = {
            'title': title,
            'status': '失败',
            'method': None,
            'error': None,
            'save_path': save_path
        }

        logging.info(f"🔍 开始处理: {title}")

        # 尝试不同来源
        # 使用可延迟执行的函数，防止不必要的API调用
        sources = [
            ('Sci-Hub (DOI)', functools.partial(self._try_doi_fetch, title)),
            ('arXiv', lambda: self._fetch_arxiv(title)),
            ('Sci-Hub (Selenium)', lambda: self._fetch_scihub_selenium(title)),
        ]

        for source_name, fetcher in sources:
            for attempt in range(retries):
                try:
                    logging.debug(f"尝试来源: {source_name} (第{attempt + 1}次重试)")
                    # 获取PDF链接
                    pdf_url, error = fetcher()
                    if not pdf_url:
                        result['error'] = error
                        logging.warning(f"❓ {source_name} 未找到资源: {error}")
                        continue

                    # 执行下载
                    logging.info(f"⬇️ 尝试下载: {pdf_url}")
                    success, dl_error = self._download_pdf(pdf_url, save_path)
                    if success:
                        result.update({
                            'status': '成功',
                            'method': source_name,
                            'error': None
                        })
                        logging.info(f"✅ 下载成功: {title} via {source_name}")
                        return result

                    result['error'] = dl_error
                    logging.warning(f"⚠️ 下载失败: {dl_error}")

                except Exception as e:
                    error_msg = f"异常: {str(e)}"
                    result['error'] = error_msg
                    logging.error(f"🔥 发生异常: {error_msg}")

                # 智能退避
                delay = min(2 ** attempt, 10)  # 指数退避最大10秒
                time.sleep(delay)

        if result['status'] == '失败':
            logging.error(f"❌ 最终失败: {title} | 错误: {result.get('error', '未知错误')}")
        return result

    def _try_doi_fetch(self, title):
        """先获取DOI再尝试Sci-Hub"""
        doi, error = self._get_doi_from_title(title)
        if doi:
            return self._fetch_scihub(doi)
        return None, error or "未找到DOI"

    def download_papers(self, titles: List[str], save_dir: str) -> Dict[str, int]:
        """使用线程池并行下载多篇论文"""
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        total = len(titles)
        stats = {'success': 0, 'fail': 0, 'skipped': 0}
        results = []

        # 初始化结果记录文件
        result_csv = 'download_results.csv'
        fieldnames = ['title', 'status', 'method', 'error', 'save_path']

        if not os.path.exists(result_csv):
            with open(result_csv, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
        else:
            with open(result_csv, 'w', encoding='utf-8-sig') as f:
                pass  # 打开文件并立即关闭以清空内容

        # 创建结果记录对象
        result_file = open(result_csv, 'a', newline='', encoding='utf-8-sig')
        result_writer = csv.DictWriter(result_file, fieldnames=fieldnames)

        with tqdm(
                total=total,
                desc="📥 论文下载进度",
                unit="篇",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [已用:{elapsed}<剩余:{remaining}]"
        ) as pbar:
            # 创建并提交任务
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_title = {}

                for title in titles:
                    safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)[:100]
                    save_path = os.path.join(save_dir, f"{safe_title}.pdf")

                    # 检查文件是否存在
                    if os.path.exists(save_path):
                        result = {
                            'title': title,
                            'status': '跳过',
                            'method': None,
                            'error': '文件已存在',
                            'save_path': save_path
                        }
                        result_writer.writerow(result)
                        stats['skipped'] += 1
                        pbar.update(1)
                        pbar.set_postfix(stats, refresh=True)
                        continue

                    # 提交任务
                    future = executor.submit(self.download_by_title, title, save_path)
                    future_to_title[future] = title

                # 处理完成的任务
                for future in as_completed(future_to_title):
                    title = future_to_title[future]
                    try:
                        result = future.result()
                        if result['status'] == '成功':
                            stats['success'] += 1
                        else:
                            stats['fail'] += 1

                        # 记录结果
                        result_writer.writerow(result)
                        result_file.flush()  # 立即写入磁盘

                    except Exception as e:
                        logging.error(f"处理任务结果时出错: {str(e)}")
                        stats['fail'] += 1

                    pbar.update(1)
                    pbar.set_postfix(stats, refresh=True)

        # 关闭结果文件
        result_file.close()
        return stats


def read_titles_from_csv(file_path: str) -> List[str]:
    """从CSV文件读取论文标题"""
    titles = []
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            titles = [row.get('Title', '').strip() for row in reader if row.get('Title', '').strip()]
        logging.info(f"成功读取 {len(titles)} 篇论文标题")
    except Exception as e:
        logging.critical(f"💥 无法读取输入文件: {str(e)}")
    return titles


def main(input_csv, save_dir, max_workers):
    # 设置日志
    setup_logging()

    # 初始化下载器，设置并行数
    downloader = PaperDownloader(max_workers=max_workers)  # 调整线程数量

    # 读取输入文件
    titles = read_titles_from_csv(input_csv)
    if not titles:
        logging.error("没有找到要下载的论文标题!")
        return

    # 执行下载
    stats = downloader.download_papers(titles, save_dir)

    # 最终输出
    print(f"\n✅ 下载完成！成功: {stats['success']} 篇 | 失败: {stats['fail']} 篇 | 跳过: {stats['skipped']} 篇")
    logging.info(f"最终统计 - {stats}")
    logging.info("🏁 程序运行结束")


if __name__ == "__main__":
    input_csv = 'wos_results.csv'
    save_dir = 'pulsed_laser_deposition'
    main(input_csv, save_dir, 5)
