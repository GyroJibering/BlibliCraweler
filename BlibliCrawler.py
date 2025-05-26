import os
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import json
from pymongo import MongoClient
from datetime import datetime
import logging
import tools

# 设置日志配置
logging.basicConfig(level=logging.INFO,  # 设置日志级别
                    format='%(asctime)s - %(levelname)s - %(message)s',  # 设置日志格式
                    handlers=[
                        logging.StreamHandler(),  # 输出到控制台
                        logging.FileHandler("app.log", mode='a', encoding='utf-8')  # 输出到文件
                    ])


# 连接 MongoDB 数据库
def get_db_connection():
    # 连接到本地 MongoDB 数据库
    client = MongoClient("mongodb")  # 根据实际配置修改
    db = client['bilibili']  # 使用 'blibli' 数据库
    collection = db['user_info']  # 使用 'user_info' 集合
    return collection


# 存储用户信息到 MongoDB
async def store_user_info_in_db(all_user_info):
    collection = get_db_connection()

    # 插入数据到 MongoDB，插入之前检查重复
    for user in all_user_info:
        # 检查是否已经存在该用户
        if not collection.find_one({'uid': user['uid']}):
            collection.insert_one(user)
            logging.info(f"用户 {user['uid']} 信息已保存到数据库")
        else:
            logging.info(f"用户 {user['uid']} 信息已存在，跳过插入")


async def save_vid_to_mongodb(video_info: dict):
    client = MongoClient("mongodb://adminUser:snprsPassword@10.176.122.229:27017/?authSource=admin")  # 根据实际配置修改
    db = client['bilibili']  # 使用 'blibli' 数据库
    collection = db['video_info']  # 使用 'user_info' 集合

    # 对每条视频数据执行更新（存在则更新，不存在则插入）
    for video_id, title in video_info.items():
        await collection.insert_one(
            {"video_id": video_id},
            {"$set": {"title": title, "label": False}},  # 添加 label 字段，默认设置为 False
            upsert=True
        )
    logging.info("推荐视频号和标题信息已保存到 MongoDB")
    client.close()


async def fetch_user_info(video_ids: list, user_info_filename: str, storage_state_file: str, used_video_ids: list):
    all_user_info = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for video_id in video_ids:
                if video_id in used_video_ids:
                    logging.info(f"视频 {video_id} 已处理过，跳过...")
                    continue
                logging.info(f"正在获取视频 {video_id} 的用户信息...")
                # 为每个 video_id 创建独立的上下文
                async with await browser.new_context(
                        storage_state=storage_state_file if os.path.exists(storage_state_file) else None
                ) as context:
                    page = await context.new_page()
                    try:
                        await page.goto(f"https://www.bilibili.com/video/{video_id}", timeout=60000)
                        await page.wait_for_timeout(5000)

                        # 优化滚动逻辑
                        max_retries = 5
                        retries = 0
                        last_height = await page.evaluate("document.documentElement.scrollHeight")
                        while True:
                            await page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                            await page.wait_for_timeout(2000)
                            new_height = await page.evaluate("document.documentElement.scrollHeight")
                            if new_height == last_height:
                                retries += 1
                                if retries >= max_retries:
                                    break
                            else:
                                retries = 0
                                last_height = new_height

                        # 确保评论用户信息加载
                        await page.wait_for_selector('bili-comment-user-info', state='attached', timeout=6000)

                        user_info_elements = await page.query_selector_all('bili-comment-user-info')
                        comment_contents = await page.query_selector_all('#content #contents')

                        for index, user_info in enumerate(user_info_elements):
                            try:
                                user_name_tag = await user_info.query_selector('#user-name a')
                                user_level_tag = await user_info.query_selector('#user-level img')

                                uid = user_nickname = user_level = comment_content = None

                                if user_name_tag:
                                    uid = (await user_name_tag.get_attribute('href')).split('/')[-1]
                                    user_nickname = await user_name_tag.inner_text()

                                if user_level_tag:
                                    level_src = await user_level_tag.get_attribute('src')
                                    user_level = level_src.split('/')[-1].split('.')[0] if level_src else None

                                # 确保评论内容与用户信息索引匹配
                                if index < len(comment_contents):
                                    comment_content = await comment_contents[index].inner_text()

                                if user_level and ('level_2' in user_level or 'level_3' in user_level):
                                    all_user_info.append({
                                        'uid': uid,
                                        'nickname': user_nickname,
                                        'level': user_level,
                                        'comment': comment_content,
                                        'label': 0,
                                        'timestamp': datetime.now().isoformat()
                                    })
                            except Exception as e:
                                logging.error(f"提取第 {index} 条用户信息失败: {e}")

                        # 将数据存入数据库
                        await store_user_info_in_db(all_user_info)

                        logging.info(f"用户信息已保存到数据库")

                    except Exception as e:
                        logging.error(f"处理视频 {video_id} 时发生严重错误: {e}")
                    finally:
                        await page.close()
        finally:
            await browser.close()


# 获取视频号并继续遍历爬取
async def fetch_bilibili_html(storage_state_file: str, video_ids: list, account_info_filename: str,
                              user_info_filename: str, used_video_ids: list):
    all_video_info = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for video_id in video_ids:
            if video_id in used_video_ids:
                logging.info(f"视频 {video_id} 已处理过，跳过...")
                continue
            logging.info(f"正在爬取视频：{video_id}...")

            context = await browser.new_context(
                storage_state=storage_state_file if os.path.exists(storage_state_file) else None)
            page = await context.new_page()

            if not os.path.exists(storage_state_file):
                # 打开B站登录页面，让用户手动输入账号密码
                logging.info("请在弹出的窗口中手动登录B站...")
                await page.goto("https://www.bilibili.com/")
                await page.wait_for_timeout(60000)  # 等待60秒，让用户手动完成登录

                # 保存登录状态到文件，下次可直接使用
                await context.storage_state(path=storage_state_file)

            # 确保跳转到目标视频页面
            logging.info(f"正在访问视频页面：https://www.bilibili.com/video/{video_id}...")
            await page.goto(f"https://www.bilibili.com/video/{video_id}")
            await page.wait_for_timeout(5000)  # 等待页面加载完成

            # 获取渲染后的完整 HTML
            html_content = await page.content()

            # 解析HTML并提取推荐视频封面和视频号
            soup = BeautifulSoup(html_content, 'html.parser')

            # 提取推荐视频数据
            for rec_video_card in soup.find_all('div', class_='video-page-card-small'):
                video_url_tag = rec_video_card.find('a', href=True)
                if video_url_tag:
                    href = video_url_tag['href']

                    # 确保链接是视频链接，并获取视频号
                    if "/video/" in href:
                        rec_video_id = href.split('/')[2]  # 获取视频号
                        logging.info(rec_video_id)
                    else:
                        continue  # 如果不是视频链接，跳过

                    rec_title = video_url_tag.find('img')
                    if rec_title in used_video_ids:
                        logging.info(f"视频 {rec_title} 已处理过，跳过...")
                        continue
                    rec_video_title = rec_title.get('alt', '无标题')

                    # 保存推荐视频号和标题信息
                    all_video_info[rec_video_id] = rec_video_title

            # 保存推荐视频号和标题信息到JSON文件（追加模式）
            if os.path.exists(account_info_filename) and os.path.getsize(account_info_filename) > 0:
                with open(account_info_filename, "r", encoding="utf-8") as json_file:
                    existing_data = json.load(json_file)
                    existing_data.update(all_video_info)  # 更新已有数据
            else:
                existing_data = all_video_info  # 如果文件不存在或为空，则初始化为空字典

            # 保存合并后的标题信息到JSON文件
            with open(account_info_filename, "w", encoding="utf-8") as json_file:
                json.dump(existing_data, json_file, ensure_ascii=False, indent=4)

            logging.info(f"推荐视频号和标题信息已保存到: {account_info_filename}")

        # 关闭浏览器
        await browser.close()


async def main_async():
    # 初始化配置
    video_ids = ["BV1bBoTYJEkU"]
    storage_state_file = "bilibili_storage_state.json"
    account_info_filename = "account1_info.json"
    user_info_filename = "user_info.json"
    output_filename = "video_ids.json"
    n = 10  # 循环次数

    # 主流程控制
    async with async_playwright() as p:
        # 浏览器实例在整个流程中只创建一次
        browser = await p.chromium.launch(headless=False)

        try:
            # 首次执行
            used_video_ids_filename = "used_ids.json"

            # 加载已处理视频号列表
            if os.path.exists(used_video_ids_filename) and os.path.getsize(used_video_ids_filename) > 0:
                with open(used_video_ids_filename, "r", encoding="utf-8") as f:
                    used_video_ids = json.load(f)
            else:
                used_video_ids = []
            await fetch_bilibili_html(storage_state_file, video_ids, account_info_filename, user_info_filename, used_video_ids)
            video_ids_comments = tools.extract_video_ids(account_info_filename, output_filename)

            await fetch_user_info(video_ids_comments, user_info_filename, storage_state_file, used_video_ids)

            # 循环执行
            while n > 0:
                tools.merge_json_data_and_clear_first_file(account_info_filename, "used_ids.json")
                video_ids = video_ids_comments
                await fetch_bilibili_html(storage_state_file, video_ids, account_info_filename, user_info_filename, used_video_ids)
                video_ids_comments = tools.extract_video_ids(account_info_filename, output_filename)

                if os.path.exists(used_video_ids_filename) and os.path.getsize(used_video_ids_filename) > 0:
                    with open(used_video_ids_filename, "r", encoding="utf-8") as f:
                        used_video_ids = json.load(f)
                else:
                    used_video_ids = []
                await fetch_user_info(video_ids_comments, user_info_filename, storage_state_file, used_video_ids)
                n -= 1

            # 最终处理
            tools.remove_duplicate_uids(user_info_filename)

        finally:
            await browser.close()  # 确保最终关闭浏览器


if __name__ == "__main__":
    asyncio.run(main_async())  # 单一入口点
