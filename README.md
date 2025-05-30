# Bilibili 用户信息爬虫项目

## 项目概述

这是一个基于 Python 的异步爬虫系统，专门用于从 Bilibili 视频平台爬取用户信息、评论内容和推荐视频数据。项目通过模拟用户行为登录 B站，自动爬取指定视频的评论用户信息和相关推荐视频，并将结果存储到 MongoDB 数据库中。

## 主要功能

- 🕵️‍♂️ **用户信息爬取**：获取评论用户的 UID、昵称、等级和评论内容
- 📹 **推荐视频发现**：自动发现相关推荐视频并提取视频ID和标题
- 💾 **数据存储**：将爬取结果存储到 MongoDB 数据库
- 🔐 **登录状态保持**：使用 Playwright 保存登录状态，避免重复登录
- 🔁 **循环爬取**：支持多轮爬取，自动扩展爬取范围
- 🚫 **数据去重**：自动跳过已处理的视频和用户
- 📝 **详细日志**：记录爬取过程和错误信息

## 技术栈

- **Python 3.7+**
- **Playwright** - 浏览器自动化和页面渲染
- **BeautifulSoup** - HTML 解析和数据提取
- **MongoDB** - 数据存储
- **Asyncio** - 异步爬取实现
- **Logging** - 日志记录系统

## 安装与使用

### 前置要求

1. Python 3.7+
2. MongoDB 服务运行中
3. Playwright 浏览器内核

### 安装步骤

```bash
# 克隆项目
git clone https://github.com/yourusername/bilibili-user-crawler.git
cd bilibili-user-crawler

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
