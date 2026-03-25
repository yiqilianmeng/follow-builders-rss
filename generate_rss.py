import requests
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from xml.dom import minidom


URLS = {
    "x": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json",
    "podcasts": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-podcasts.json",
    "blogs": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-blogs.json",
}

RSS_TITLE = "Follow Builders RSS"
RSS_LINK = "https://github.com/zarazhangrui/follow-builders"
RSS_DESCRIPTION = "聚合 AI 领域建设者的 X、播客和博客内容。"
RSS_LANGUAGE = "zh-cn"
OUTPUT_FILENAME = "follow_builders_rss.xml"
MAX_ITEMS = 300


def fetch_data(url):
    headers = {
        "User-Agent": "follow-builders-rss-generator/1.0"
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def clean_text(text, max_len=8000):
    if text is None:
        return ""
    text = str(text).strip()
    if not text:
        return ""
    # 去掉常见非法控制字符，避免 XML 异常
    for ch in ["\x00", "\x01", "\x02", "\x03", "\x04", "\x05", "\x06", "\x07", "\x08", "\x0b", "\x0c", "\x0e", "\x0f"]:
        text = text.replace(ch, "")
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def first_non_empty(*values, default=""):
    for value in values:
        if value is None:
            continue
        s = str(value).strip()
        if s:
            return s
    return default


def parse_iso_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    normalized = date_str.strip().replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    try:
        # 去掉小数秒再兜底解析
        if "." in normalized:
            left, right = normalized.split(".", 1)
            if "+" in right:
                tz_part = "+" + right.split("+", 1)[1]
                dt = datetime.fromisoformat(left + tz_part)
            elif "-" in right[1:]:
                tz_part = "-" + right[1:].split("-", 1)[1]
                dt = datetime.fromisoformat(left + tz_part)
            else:
                dt = datetime.fromisoformat(left)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass

    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def format_rfc2822(dt):
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")


def build_x_items(data):
    result = []
    profiles = data.get("x", [])
    if not isinstance(profiles, list):
        print(f"⚠️ x 顶层字段不是数组: {type(profiles)}")
        return result

    for profile in profiles:
        if not isinstance(profile, dict):
            continue

        author_name = clean_text(first_non_empty(profile.get("name"), profile.get("handle"), default="未知作者"), 200)
        handle = clean_text(profile.get("handle"), 100)
        bio = clean_text(profile.get("bio"), 1000)

        tweets = profile.get("tweets", [])
        if not isinstance(tweets, list):
            continue

        for tweet in tweets:
            if not isinstance(tweet, dict):
                continue

            text = clean_text(first_non_empty(tweet.get("text"), default=""))
            tweet_url = first_non_empty(tweet.get("url"), default=RSS_LINK)
            tweet_id = first_non_empty(tweet.get("id"), tweet_url, default=tweet_url)
            created_at = parse_iso_date(tweet.get("createdAt"))

            if text:
                title = clean_text(text.replace("\n", " "), 300)
            else:
                title = f"{author_name} @{handle}" if handle else author_name

            description_parts = [f"作者：{author_name}"]
            if handle:
                description_parts.append(f"账号：@{handle}")
            if bio:
                description_parts.append(f"简介：{bio}")
            description_parts.append("")
            description_parts.append(text or "无正文")

            description = "\n".join(description_parts)

            result.append({
                "title": title,
                "link": tweet_url,
                "description": description,
                "pubDate": created_at,
                "guid": str(tweet_id),
            })

    return result


def build_podcast_items(data):
    result = []
    podcasts = data.get("podcasts", [])
    if not isinstance(podcasts, list):
        print(f"⚠️ podcasts 顶层字段不是数组: {type(podcasts)}")
        return result

    for ep in podcasts:
        if not isinstance(ep, dict):
            continue

        show_name = clean_text(first_non_empty(ep.get("name"), default="未知播客"), 200)
        title = clean_text(first_non_empty(ep.get("title"), ep.get("name"), default="未命名播客内容"), 300)
        link = first_non_empty(ep.get("url"), default=RSS_LINK)
        published_at = parse_iso_date(first_non_empty(ep.get("publishedAt"), ep.get("date_published"), default=""))
        transcript = clean_text(first_non_empty(ep.get("transcript"), ep.get("summary"), ep.get("description"), default="无正文"))
        video_id = clean_text(first_non_empty(ep.get("videoId"), default=""), 100)

        description_parts = [f"播客：{show_name}"]
        if video_id:
            description_parts.append(f"视频 ID：{video_id}")
        description_parts.append("")
        description_parts.append(transcript)

        guid = first_non_empty(ep.get("videoId"), ep.get("url"), title, default=link)

        result.append({
            "title": title,
            "link": link,
            "description": "\n".join(description_parts),
            "pubDate": published_at,
            "guid": str(guid),
        })

    return result


def build_blog_items(data):
    result = []
    blogs = data.get("blogs", [])
    if not isinstance(blogs, list):
        print(f"⚠️ blogs 顶层字段不是数组: {type(blogs)}")
        return result

    for post in blogs:
        if not isinstance(post, dict):
            continue

        author = clean_text(first_non_empty(post.get("name"), post.get("author"), default="未知作者"), 200)
        title = clean_text(first_non_empty(post.get("title"), post.get("name"), default="未命名博客文章"), 300)
        link = first_non_empty(post.get("url"), post.get("link"), default=RSS_LINK)
        published_at = parse_iso_date(first_non_empty(
            post.get("publishedAt"),
            post.get("date_published"),
            post.get("createdAt"),
            default=""
        ))
        content = clean_text(first_non_empty(
            post.get("content"),
            post.get("summary"),
            post.get("description"),
            default="无正文"
        ))
        guid = first_non_empty(post.get("id"), post.get("url"), post.get("link"), title, default=link)

        description = f"作者：{author}\n\n{content}"

        result.append({
            "title": title,
            "link": link,
            "description": description,
            "pubDate": published_at,
            "guid": str(guid),
        })

    return result


def generate_rss():
    print("🚀 开始抓取内容...")

    all_items = []

    # X
    try:
        print(f"\n📦 抓取 x: {URLS['x']}")
        x_data = fetch_data(URLS["x"])
        x_items = build_x_items(x_data)
        print(f"  - x 解析后条数: {len(x_items)}")
        all_items.extend(x_items)
    except Exception as e:
        print(f"❌ x 抓取失败: {e}")

    # Podcasts
    try:
        print(f"\n📦 抓取 podcasts: {URLS['podcasts']}")
        podcast_data = fetch_data(URLS["podcasts"])
        podcast_items = build_podcast_items(podcast_data)
        print(f"  - podcasts 解析后条数: {len(podcast_items)}")
        all_items.extend(podcast_items)
    except Exception as e:
        print(f"❌ podcasts 抓取失败: {e}")

    # Blogs
    try:
        print(f"\n📦 抓取 blogs: {URLS['blogs']}")
        blog_data = fetch_data(URLS["blogs"])
        blog_items = build_blog_items(blog_data)
        print(f"  - blogs 解析后条数: {len(blog_items)}")
        all_items.extend(blog_items)
    except Exception as e:
        print(f"❌ blogs 抓取失败: {e}")

    all_items.sort(key=lambda x: x["pubDate"], reverse=True)
    all_items = all_items[:MAX_ITEMS]

    print(f"\n✅ 内容处理完成，共 {len(all_items)} 条。")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = RSS_TITLE
    ET.SubElement(channel, "link").text = RSS_LINK
    ET.SubElement(channel, "description").text = RSS_DESCRIPTION
    ET.SubElement(channel, "language").text = RSS_LANGUAGE
    ET.SubElement(channel, "lastBuildDate").text = format_rfc2822(datetime.now(timezone.utc))

    for item in all_items:
        item_elem = ET.SubElement(channel, "item")
        ET.SubElement(item_elem, "title").text = item["title"]
        ET.SubElement(item_elem, "link").text = item["link"]
        ET.SubElement(item_elem, "description").text = item["description"]
        ET.SubElement(item_elem, "pubDate").text = format_rfc2822(item["pubDate"])

        guid_elem = ET.SubElement(item_elem, "guid")
        guid_elem.text = item["guid"]
        if item["guid"] != item["link"]:
            guid_elem.set("isPermaLink", "false")

    xml_bytes = ET.tostring(rss, encoding="utf-8")
    pretty_xml = minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")

    with open(OUTPUT_FILENAME, "wb") as f:
        f.write(pretty_xml)

    print(f"🎉 成功生成：{OUTPUT_FILENAME}")


if __name__ == "__main__":
    generate_rss()