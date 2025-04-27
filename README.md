# Web of Science 论文自动化下载工具包

## 项目简介
本工具包包含两个自动化脚本，分别用于学术论文信息采集和文献自动下载，助力科研工作者高效获取学术资源。

## 组件构成
1. WOS.py - Web of Science论文信息采集器
2. auto_dwn.py - 学术论文自动下载器

---

# 📚 WOS.py - Web of Science论文采集器

## 核心功能
### ✅ 智能页面解析
• 自动滚动加载完整页面内容

• 动态识别摘要展开按钮

• 支持中断续爬功能


### ✅ 数据精准提取
• 论文标题

• 发表日期

• 被引次数

• 完整摘要内容


### ✅ 反爬对抗策略
• 拟人化滚动模式

• 随机操作延迟

• 动态元素定位


## 使用说明
```bash
# 启动前准备（需手动操作）
chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\chrome_temp
```
修改
```python
main(start_page, pages_num, target_count)
```
中的参数

参数说明
| 参数       | 说明                  | 
|------------|-----------------------|
| start_page    | 起始页       | 
| pages_num   | 获取页面数量          |
| target_count   | 每一页最多有多少条论文信息          |


## 注意事项
⚠️ 程序开始运行时会有120s登录Web of Science
⚠️ 浏览器需保持登录状态  
⚠️ 建议单次采集不超过100页  
⚠️ 数据存储为UTF-8格式CSV

---

# 📥 auto_dwn.py - 学术论文自动下载器

## 核心功能
### 🚀 多源下载支持
• Sci-Hub镜像自动切换

• arXiv直接下载

• 智能DOI解析


### ⚡ 高效下载机制
• 多线程并发下载（默认5线程）

• 请求失败自动重试

• 智能缓存系统


### 📊 数据管理
• 下载日志记录

• 结果统计报表

• 断点续下支持


## 使用说明
修改
```python
main(input_csv, save_dir, max_workers)
```
中的参数

参数说明
| 参数       | 说明                  | 
|------------|-----------------------|
| input_csv    | 输入CSV文件路径       | 
| save_dir   | 论文保存目录          |
| max_workers  | 并行下载线程数        |

---

# 🛠 环境依赖

必备组件
```python
Python >= 3.8
requests >= 2.26
beautifulsoup4 >= 4.9
selenium >= 4.0
undetected-chromedriver >= 3.1
pandas >= 1.3
tqdm >= 4.62
```

---

# ⚠️ 重要声明
1. 遵守目标网站的Robots协议
2. 控制合理请求频率
3. 下载文献仅供学术研究使用
4. 请在24小时内删除已下载文献

---

# 典型工作流程
1. 使用WOS.py获取文献目录
2. 生成包含标题的CSV文件
3. 通过auto_dwn.py批量下载
4. 查看download_results.csv获取下载详情


*注：实际使用请遵守相关法律法规和学术规范*
