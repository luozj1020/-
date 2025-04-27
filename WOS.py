import random
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
import undetected_chromedriver as uc


def connect_existing_browser(port=9222):
    """连接已打开的浏览器实例"""
    options = uc.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

    # 伪装参数
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-popup-blocking")

    return uc.Chrome(options=options, use_subprocess=False)


def dynamic_scroll(driver, target_count=50, max_attempts=1000):
    """智能滚动加载(增强版)"""
    last_record_count = 0
    unchanged_cycles = 0
    scroll_attempt = 0
    is_bottom_reached = False

    while scroll_attempt < max_attempts and not is_bottom_reached:
        # 获取页面高度参数
        scroll_top = driver.execute_script("return window.pageYOffset;")
        window_height = driver.execute_script("return window.innerHeight;")
        body_height = driver.execute_script("return document.body.scrollHeight;")

        # 智能底部检测
        if scroll_top + window_height >= body_height - 100:
            print("🛑 检测到页面底部")
            is_bottom_reached = True
            break

        # 生成拟人化滚动参数
        scroll_step = random.randint(500, 800)
        smooth_behavior = random.choice(['smooth', 'auto', 'smooth'])
        scroll_delay = random.uniform(1.8, 3.5)

        # 执行带随机扰动的滚动
        driver.execute_script(f"""
            window.scrollBy({{
                top: {scroll_step},
                behavior: '{smooth_behavior}'
            }});
        """)

        # 拟人化等待（包含网络延迟模拟）
        time.sleep(scroll_delay * random.uniform(0.5, 1.0))

        # 反向滚动补偿（10%概率）
        if random.random() > 0.9:
            back_step = random.randint(200, 400)
            driver.execute_script(f"window.scrollBy({{top: -{back_step}, behavior: 'smooth'}});")
            time.sleep(random.uniform(0.5, 1.0))

        # 动态内容检测
        current_records = len(driver.find_elements(By.CSS_SELECTOR, "div.summary-record"))
        if current_records >= target_count:
            print(f"✅ 达到目标记录数 {current_records}/{target_count}")
            return True
        if current_records == last_record_count:
            unchanged_cycles += 1
            if unchanged_cycles >= 2:  # 连续2次无变化即终止
                print(f"⚠️ 内容稳定在 {current_records} 条")
                return False
        else:
            last_record_count = current_records
            unchanged_cycles = 0

        scroll_attempt += 1

        # 强制等待加载状态消失
        WebDriverWait(driver, 10).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.loading-bar"))
        )

    # 底部二次验证
    if is_bottom_reached:
        final_records = len(driver.find_elements(By.CSS_SELECTOR, "div.summary-record"))
        print(f"🔚 最终获取 {final_records} 条记录")
        return final_records > 0
    return False



def extract_article_data(start_page, article, idx, current_page, target_count):
    """改进的摘要提取方法"""
    data = {}
    try:
        data['Title'] = article.find_element(
            By.CSS_SELECTOR, 'a.title').text.strip()
    except:
        data['Title'] = None

    try:
        data['Date'] = article.find_element(
            By.CSS_SELECTOR, 'div > div > div.data-section > div:nth-child(2) > div.jcr-and-pub-info-section > span.value.ng-star-inserted').text.strip()
    except:
        data['Date'] = None

    try:
        data['Citation'] = article.find_element(
            By.CSS_SELECTOR, 'div > div > div.stats-container > div > div.stats-section-section > div.no-bottom-border.citations.ng-star-inserted > a').text.strip()
    except:
        data['Citation'] = None

    try:
        # 处理摘要展开
        abstract_btn = article.find_element(
            By.CSS_SELECTOR, 'button.show-more')
        abstract_btn.click()
        time.sleep(0.5)
        # 使用动态生成的摘要ID
        abstract_id = f"rec{(start_page+current_page-2) * target_count + idx + 1}AbstractPart0"  # 索引从1开始
        data['Abstract'] = article.find_element(
            By.ID, abstract_id).text.strip()
    except Exception as e:
        print(f"摘要提取失败: {str(e)}")
        data['Abstract'] = None

    return data


def main(start_page, pages_num, target_count):
    driver = connect_existing_browser(9222)
    time.sleep(10)

    data = []
    current_page = 1

    try:
        while current_page <= pages_num:
            print(f"正在处理第 {current_page} 页...")

            # 执行动态滚动加载
            if current_page==1:
                time.sleep(120)
                print("start...")
            dynamic_scroll(driver)

            articles = driver.find_elements(By.CSS_SELECTOR, 'div.summary-record')
            print(f"本页检测到 {len(articles)} 条记录")

            for idx, article in enumerate(articles):
                try:
                    item = extract_article_data(start_page, article, idx, current_page, target_count)
                    item['Page'] = start_page + current_page - 1
                    data.append(item)
                    print(f"已提取第 {idx + 1} 篇论文数据")
                except Exception as e:
                    print(f"第 {idx + 1} 篇数据提取失败: {str(e)}")

            # 改进的翻页逻辑
            if current_page < pages_num:
                # 使用用户提供的精确CSS路径
                next_btn = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR,
                                                'body > app-wos > main > div > div > div.holder > div > div > div.held > app-input-route > app-base-summary-component > div > div.results.ng-star-inserted > app-page-controls.app-page-controls.summary-bottom-border > div > form > div > button:nth-child(4)'))
                )

                # 增强点击可靠性
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_btn)
                time.sleep(1)
                ActionChains(driver).move_to_element(next_btn).pause(
                    random.uniform(0.8, 1.5)).click().perform()

                # 等待页面稳定
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                                                    'div.summary-record:not(.loading)'))
                )
                # 增加页面加载缓冲
                time.sleep(random.uniform(2.5, 4.0))

            current_page += 1
            if current_page % 10 == 0:
                df = pd.DataFrame(data)
                df.to_csv("wos_results.csv", index=False, encoding='utf-8-sig')


    finally:
        df = pd.DataFrame(data)
        df.to_csv("wos_results.csv", index=False, encoding='utf-8-sig')
        print(f"数据已保存，共提取 {len(data)} 条记录")


if __name__ == "__main__":
    # 使用方法：
    # 1. 手动启动Chrome：
    #    chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\chrome_temp
    # 2. 登录并导航到目标页面
    # 3. 运行此脚本
    main(355, 786-355+1, 50)  # example
