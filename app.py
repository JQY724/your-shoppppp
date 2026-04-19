import streamlit as st
import requests
import base64
import json
import pandas as pd
from datetime import datetime
from uuid import uuid4

st.set_page_config(page_title="GitHub 商城", layout="wide")

# =========================
# 配置
# =========================
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "")
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN", "")
GITHUB_REPO = st.secrets.get("GITHUB_REPO", "")   # 例如 yourname/my-shop
GITHUB_BRANCH = st.secrets.get("GITHUB_BRANCH", "main")

missing = []
if not ADMIN_PASSWORD:
    missing.append("ADMIN_PASSWORD")
if not GITHUB_TOKEN:
    missing.append("GITHUB_TOKEN")
if not GITHUB_REPO:
    missing.append("GITHUB_REPO")

if missing:
    st.error("缺少 Secrets 配置：" + ", ".join(missing))
    st.info("请到 Streamlit Cloud -> App settings -> Secrets 中配置这些值，然后保存并重启应用。")
    st.stop()

API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"

PRODUCTS_PATH = "data/products.json"
SETTINGS_PATH = "data/settings.json"
STATS_PATH = "data/stats.json"
IMAGES_DIR = "data/images"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}


# =========================
# GitHub 文件操作
# =========================
def github_get_file(path):
    url = f"{API_BASE}/{path}?ref={GITHUB_BRANCH}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        return None
    raise Exception(f"读取 GitHub 文件失败: {path} / {r.status_code} / {r.text}")


def github_put_file(path, content_bytes, message):
    existing = github_get_file(path)
    sha = existing["sha"] if existing else None

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
        "branch": GITHUB_BRANCH
    }
    if sha:
        payload["sha"] = sha

    url = f"{API_BASE}/{path}"
    r = requests.put(url, headers=HEADERS, json=payload, timeout=30)
    if r.status_code not in [200, 201]:
        raise Exception(f"写入 GitHub 文件失败: {path} / {r.status_code} / {r.text}")
    return r.json()


def github_delete_file(path, message):
    existing = github_get_file(path)
    if not existing:
        return

    payload = {
        "message": message,
        "sha": existing["sha"],
        "branch": GITHUB_BRANCH
    }

    url = f"{API_BASE}/{path}"
    r = requests.delete(url, headers=HEADERS, json=payload, timeout=30)
    if r.status_code not in [200]:
        raise Exception(f"删除 GitHub 文件失败: {path} / {r.status_code} / {r.text}")


def github_read_json(path, default_value):
    file_data = github_get_file(path)
    if not file_data:
        return default_value

    content = base64.b64decode(file_data["content"]).decode("utf-8")
    return json.loads(content)


def github_write_json(path, data, message):
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    github_put_file(path, content, message)


def github_upload_image(uploaded_file):
    ext = uploaded_file.name.split(".")[-1].lower() if "." in uploaded_file.name else "jpg"
    filename = f"{uuid4().hex}.{ext}"
    path = f"{IMAGES_DIR}/{filename}"
    github_put_file(path, uploaded_file.read(), f"upload image {filename}")
    return path


def github_image_url(path):
    return f"{RAW_BASE}/{path}"


# =========================
# 初始化远程数据
# =========================
def init_repo_data():
    if not github_get_file(PRODUCTS_PATH):
        github_write_json(PRODUCTS_PATH, [], "init products.json")

    if not github_get_file(SETTINGS_PATH):
        github_write_json(
            SETTINGS_PATH,
            {
                "shop_name": "我的店铺",
                "wechat_link": "",
                "alipay_link": "",
                "external_link": "",
                "contact_text": "请联系商家"
            },
            "init settings.json"
        )

    if not github_get_file(STATS_PATH):
        github_write_json(STATS_PATH, [], "init stats.json")


# =========================
# 数据层
# =========================
@st.cache_data(ttl=5)
def get_products():
    return github_read_json(PRODUCTS_PATH, [])


@st.cache_data(ttl=5)
def get_settings():
    return github_read_json(SETTINGS_PATH, {
        "shop_name": "我的店铺",
        "wechat_link": "",
        "alipay_link": "",
        "external_link": "",
        "contact_text": "请联系商家"
    })


@st.cache_data(ttl=5)
def get_stats():
    return github_read_json(STATS_PATH, [])


def clear_cache():
    st.cache_data.clear()


def save_products(products):
    github_write_json(PRODUCTS_PATH, products, "update products")
    clear_cache()


def save_settings(settings):
    github_write_json(SETTINGS_PATH, settings, "update settings")
    clear_cache()


def save_stats(stats):
    github_write_json(STATS_PATH, stats, "update stats")
    clear_cache()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gen_id():
    return uuid4().hex[:12]


def track_event(product_id, event_type, method=""):
    stats = get_stats()
    stats.append({
        "id": gen_id(),
        "product_id": product_id,
        "event_type": event_type,
        "method": method,
        "created_at": now_str()
    })
    save_stats(stats)


def get_product_by_id(product_id):
    products = get_products()
    for p in products:
        if p["id"] == product_id:
            return p
    return None


def get_product_stats(product_id):
    stats = get_stats()
    views = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "product_view"])
    pay_clicks = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "pay_click"])
    wechat = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "pay_click" and x["method"] == "wechat"])
    alipay = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "pay_click" and x["method"] == "alipay"])
    external = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "pay_click" and x["method"] == "external"])
    contact = len([x for x in stats if x["product_id"] == product_id and x["event_type"] == "pay_click" and x["method"] == "contact"])
    rate = round(pay_clicks / views * 100, 1) if views else 0
    return {
        "views": views,
        "pay_clicks": pay_clicks,
        "wechat": wechat,
        "alipay": alipay,
        "external": external,
        "contact": contact,
        "conversion_rate": rate
    }


def admin_logged_in():
    return st.session_state.get("admin_logged_in", False)


# =========================
# 登录
# =========================
def render_admin_login():
    st.subheader("管理员登录")
    pwd = st.text_input("管理员密码", type="password")
    if st.button("登录", use_container_width=True):
        if pwd == ADMIN_PASSWORD:
            st.session_state.admin_logged_in = True
            st.success("登录成功")
            st.rerun()
        else:
            st.error("密码错误")


# =========================
# 前台首页
# =========================
def render_home():
    settings = get_settings()
    products = [p for p in get_products() if p.get("status", "up") == "up"]

    st.title(settings.get("shop_name", "我的店铺"))
    st.caption("GitHub + Streamlit 商城")

    if not st.session_state.get("home_tracked", False):
        track_event("", "home_view")
        st.session_state.home_tracked = True

    categories = sorted(list(set([p.get("category", "") for p in products if p.get("category", "")])))
    selected_category = st.selectbox("分类筛选", ["全部"] + categories)

    if selected_category != "全部":
        products = [p for p in products if p.get("category", "") == selected_category]

    if not products:
        st.info("暂无商品")
        return

    cols = st.columns(3)
    for i, p in enumerate(products):
        with cols[i % 3]:
            with st.container(border=True):
                if p.get("cover_image"):
                    st.image(github_image_url(p["cover_image"]), use_container_width=True)
                else:
                    st.write("暂无封面图")
                st.markdown(f"**{p['name']}**")
                st.write(f"¥ {p.get('price', 0)}")
                if p.get("original_price", 0) > p.get("price", 0):
                    st.caption(f"原价：¥ {p['original_price']}")
                if st.button("查看详情", key=f"view_{p['id']}", use_container_width=True):
                    st.session_state.page = "product"
                    st.session_state.current_product_id = p["id"]
                    st.rerun()


# =========================
# 商品详情
# =========================
def render_product_detail(product_id):
    settings = get_settings()
    product = get_product_by_id(product_id)

    if not product or product.get("status") != "up":
        st.error("商品不存在或已下架")
        return

    track_key = f"tracked_product_{product_id}"
    if not st.session_state.get(track_key, False):
        track_event(product_id, "product_view")
        st.session_state[track_key] = True

    st.button("← 返回商品列表", on_click=lambda: st.session_state.update({"page": "home"}))
    st.title(product["name"])

    col1, col2 = st.columns([1, 1])

    with col1:
        if product.get("cover_image"):
            st.image(github_image_url(product["cover_image"]), use_container_width=True)
        else:
            st.write("暂无主图")

        colors = product.get("colors", [])
        if colors:
            color_names = [c["name"] for c in colors]
            selected_color = st.selectbox("选择颜色", color_names)
            current = next((c for c in colors if c["name"] == selected_color), None)
            if current and current.get("images"):
                for img in current["images"]:
                    st.image(github_image_url(img), use_container_width=True)

    with col2:
        st.subheader(f"¥ {product.get('price', 0)}")
        if product.get("original_price", 0) > product.get("price", 0):
            st.caption(f"原价：¥ {product['original_price']}")

        st.write(product.get("intro", ""))
        st.write(f"分类：{product.get('category', '-')}")
        st.write(f"库存：{product.get('stock', 0)}")

        wechat_link = product.get("wechat_link") or settings.get("wechat_link", "")
        alipay_link = product.get("alipay_link") or settings.get("alipay_link", "")
        external_link = product.get("external_link") or settings.get("external_link", "")
        contact_text = product.get("contact_text") or settings.get("contact_text", "请联系商家")

        st.markdown("### 购买方式")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("微信支付", use_container_width=True):
                track_event(product_id, "pay_click", "wechat")
                if wechat_link:
                    st.link_button("打开微信支付链接", wechat_link, use_container_width=True)
                else:
                    st.warning("未设置微信支付链接")

            if st.button("支付宝支付", use_container_width=True):
                track_event(product_id, "pay_click", "alipay")
                if alipay_link:
                    st.link_button("打开支付宝链接", alipay_link, use_container_width=True)
                else:
                    st.warning("未设置支付宝链接")

        with c2:
            if st.button("外部购买", use_container_width=True):
                track_event(product_id, "pay_click", "external")
                if external_link:
                    st.link_button("打开外部购买链接", external_link, use_container_width=True)
                else:
                    st.warning("未设置外部购买链接")

            if st.button("联系购买", use_container_width=True):
                track_event(product_id, "pay_click", "contact")
                st.info(contact_text)

    st.markdown("---")
    st.markdown("## 详情图")
    detail_images = product.get("detail_images", [])
    if detail_images:
        for img in detail_images:
            st.image(github_image_url(img), use_container_width=True)
    else:
        st.write("暂无详情图")


# =========================
# 后台数据看板
# =========================
def render_admin_dashboard():
    st.title("数据看板")

    stats = get_stats()
    products = get_products()

    today = datetime.now().strftime("%Y-%m-%d")

    today_home = len([x for x in stats if x["event_type"] == "home_view" and x["created_at"].startswith(today)])
    today_views = len([x for x in stats if x["event_type"] == "product_view" and x["created_at"].startswith(today)])
    today_pay = len([x for x in stats if x["event_type"] == "pay_click" and x["created_at"].startswith(today)])

    a, b, c = st.columns(3)
    a.metric("今日首页访问", today_home)
    b.metric("今日商品浏览", today_views)
    c.metric("今日支付点击", today_pay)

    st.markdown("## 商品对比数据")
    rows = []
    for p in products:
        s = get_product_stats(p["id"])
        rows.append({
            "商品ID": p["id"],
            "名称": p["name"],
            "价格": p.get("price", 0),
            "状态": "上架" if p.get("status") == "up" else "下架",
            "浏览量": s["views"],
            "支付点击": s["pay_clicks"],
            "转化率%": s["conversion_rate"]
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    else:
        st.info("暂无数据")

    st.markdown("## 最近统计记录")
    if stats:
        df = pd.DataFrame(stats[::-1][:100])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("暂无统计记录")


# =========================
# 后台支付设置
# =========================
def render_admin_settings():
    st.title("支付设置")
    settings = get_settings()

    with st.form("settings_form"):
        shop_name = st.text_input("店铺名称", value=settings.get("shop_name", "我的店铺"))
        wechat_link = st.text_input("默认微信支付链接", value=settings.get("wechat_link", ""))
        alipay_link = st.text_input("默认支付宝链接", value=settings.get("alipay_link", ""))
        external_link = st.text_input("默认外部购买链接", value=settings.get("external_link", ""))
        contact_text = st.text_input("默认联系购买说明", value=settings.get("contact_text", "请联系商家"))

        if st.form_submit_button("保存设置", use_container_width=True):
            save_settings({
                "shop_name": shop_name,
                "wechat_link": wechat_link,
                "alipay_link": alipay_link,
                "external_link": external_link,
                "contact_text": contact_text
            })
            st.success("设置已保存")
            st.rerun()


# =========================
# 后台商品管理
# =========================
def render_admin_products():
    st.title("商品管理")

    tab1, tab2 = st.tabs(["商品列表", "新增商品"])

    with tab1:
        products = get_products()

        rows = []
        for p in products:
            s = get_product_stats(p["id"])
            rows.append({
                "ID": p["id"],
                "名称": p["name"],
                "价格": p.get("price", 0),
                "分类": p.get("category", ""),
                "状态": "上架" if p.get("status") == "up" else "下架",
                "浏览": s["views"],
                "支付点击": s["pay_clicks"],
                "转化率%": s["conversion_rate"]
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("还没有商品")

        if not products:
            return

        product_ids = [p["id"] for p in products]
        selected_id = st.selectbox(
            "选择商品进行编辑",
            product_ids,
            format_func=lambda x: f"{x} - {get_product_by_id(x)['name']}"
        )

        product = get_product_by_id(selected_id)
        stats = get_product_stats(selected_id)

        with st.expander("编辑基础信息", expanded=True):
            with st.form(f"edit_{selected_id}"):
                name = st.text_input("商品名称", value=product.get("name", ""))
                price = st.number_input("价格", value=float(product.get("price", 0.0)))
                original_price = st.number_input("原价", value=float(product.get("original_price", 0.0)))
                category = st.text_input("分类", value=product.get("category", ""))
                intro = st.text_area("简介", value=product.get("intro", ""))
                stock = st.number_input("库存", value=int(product.get("stock", 0)), step=1)
                status = st.selectbox("状态", ["up", "down"], index=0 if product.get("status") == "up" else 1)

                st.markdown("#### 商品支付设置")
                wechat_link = st.text_input("微信支付链接", value=product.get("wechat_link", ""))
                alipay_link = st.text_input("支付宝支付链接", value=product.get("alipay_link", ""))
                external_link = st.text_input("外部购买链接", value=product.get("external_link", ""))
                contact_text = st.text_input("联系购买说明", value=product.get("contact_text", ""))

                if st.form_submit_button("保存商品", use_container_width=True):
                    products = get_products()
                    for i, p in enumerate(products):
                        if p["id"] == selected_id:
                            products[i].update({
                                "name": name,
                                "price": price,
                                "original_price": original_price,
                                "category": category,
                                "intro": intro,
                                "stock": int(stock),
                                "status": status,
                                "wechat_link": wechat_link,
                                "alipay_link": alipay_link,
                                "external_link": external_link,
                                "contact_text": contact_text,
                                "updated_at": now_str()
                            })
                            break
                    save_products(products)
                    st.success("商品已保存")
                    st.rerun()

        with st.expander("封面图管理"):
            if product.get("cover_image"):
                st.image(github_image_url(product["cover_image"]), width=220)

            cover = st.file_uploader("上传封面图", type=["png", "jpg", "jpeg"], key=f"cover_{selected_id}")
            if st.button("保存封面图", key=f"save_cover_{selected_id}", use_container_width=True):
                if cover:
                    new_path = github_upload_image(cover)
                    products = get_products()
                    old_cover = ""
                    for i, p in enumerate(products):
                        if p["id"] == selected_id:
                            old_cover = p.get("cover_image", "")
                            products[i]["cover_image"] = new_path
                            products[i]["updated_at"] = now_str()
                            break
                    save_products(products)
                    if old_cover:
                        try:
                            github_delete_file(old_cover, f"delete old cover {selected_id}")
                        except:
                            pass
                    st.success("封面图已更新")
                    st.rerun()

            if st.button("删除封面图", key=f"delete_cover_{selected_id}", use_container_width=True):
                products = get_products()
                old_cover = ""
                for i, p in enumerate(products):
                    if p["id"] == selected_id:
                        old_cover = p.get("cover_image", "")
                        products[i]["cover_image"] = ""
                        products[i]["updated_at"] = now_str()
                        break
                save_products(products)
                if old_cover:
                    try:
                        github_delete_file(old_cover, f"delete cover {selected_id}")
                    except:
                        pass
                st.success("封面图已删除")
                st.rerun()

        with st.expander("详情图管理"):
            detail_images = product.get("detail_images", [])
            if detail_images:
                cols = st.columns(3)
                for i, path in enumerate(detail_images):
                    with cols[i % 3]:
                        st.image(github_image_url(path), use_container_width=True)
                        if st.button("删除", key=f"del_detail_{selected_id}_{i}"):
                            products = get_products()
                            deleted_path = ""
                            for j, p in enumerate(products):
                                if p["id"] == selected_id:
                                    deleted_path = products[j]["detail_images"].pop(i)
                                    products[j]["updated_at"] = now_str()
                                    break
                            save_products(products)
                            if deleted_path:
                                try:
                                    github_delete_file(deleted_path, f"delete detail image {selected_id}")
                                except:
                                    pass
                            st.success("已删除")
                            st.rerun()

            detail_files = st.file_uploader(
                "上传详情图",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
                key=f"detail_upload_{selected_id}"
            )
            if st.button("保存详情图", key=f"save_detail_{selected_id}", use_container_width=True):
                if detail_files:
                    new_paths = [github_upload_image(f) for f in detail_files]
                    products = get_products()
                    for i, p in enumerate(products):
                        if p["id"] == selected_id:
                            products[i]["detail_images"].extend(new_paths)
                            products[i]["updated_at"] = now_str()
                            break
                    save_products(products)
                    st.success("详情图上传成功")
                    st.rerun()

        with st.expander("颜色图管理"):
            new_color_name = st.text_input("新增颜色名称", key=f"new_color_name_{selected_id}")
            if st.button("新增颜色", key=f"add_color_{selected_id}", use_container_width=True):
                if new_color_name.strip():
                    products = get_products()
                    for i, p in enumerate(products):
                        if p["id"] == selected_id:
                            p.setdefault("colors", []).append({
                                "id": gen_id(),
                                "name": new_color_name.strip(),
                                "images": []
                            })
                            p["updated_at"] = now_str()
                            break
                    save_products(products)
                    st.success("颜色已新增")
                    st.rerun()

            colors = product.get("colors", [])
            for c_idx, color in enumerate(colors):
                st.markdown(f"### {color['name']}")

                if st.button("删除该颜色", key=f"del_color_{selected_id}_{c_idx}"):
                    deleted_images = []
                    products = get_products()
                    for i, p in enumerate(products):
                        if p["id"] == selected_id:
                            deleted_images = p["colors"][c_idx].get("images", [])
                            p["colors"].pop(c_idx)
                            p["updated_at"] = now_str()
                            break
                    save_products(products)
                    for img in deleted_images:
                        try:
                            github_delete_file(img, f"delete color image {selected_id}")
                        except:
                            pass
                    st.success("颜色已删除")
                    st.rerun()

                imgs = color.get("images", [])
                if imgs:
                    cols = st.columns(3)
                    for img_i, path in enumerate(imgs):
                        with cols[img_i % 3]:
                            st.image(github_image_url(path), use_container_width=True)
                            if st.button("删除颜色图", key=f"del_color_img_{selected_id}_{c_idx}_{img_i}"):
                                deleted_path = ""
                                products = get_products()
                                for i, p in enumerate(products):
                                    if p["id"] == selected_id:
                                        deleted_path = p["colors"][c_idx]["images"].pop(img_i)
                                        p["updated_at"] = now_str()
                                        break
                                save_products(products)
                                if deleted_path:
                                    try:
                                        github_delete_file(deleted_path, f"delete color image {selected_id}")
                                    except:
                                        pass
                                st.success("已删除")
                                st.rerun()

                color_files = st.file_uploader(
                    f"上传 {color['name']} 图片",
                    type=["png", "jpg", "jpeg"],
                    accept_multiple_files=True,
                    key=f"upload_color_{selected_id}_{c_idx}"
                )
                if st.button("保存颜色图", key=f"save_color_{selected_id}_{c_idx}", use_container_width=True):
                    if color_files:
                        new_paths = [github_upload_image(f) for f in color_files]
                        products = get_products()
                        for i, p in enumerate(products):
                            if p["id"] == selected_id:
                                p["colors"][c_idx]["images"].extend(new_paths)
                                p["updated_at"] = now_str()
                                break
                        save_products(products)
                        st.success("颜色图上传成功")
                        st.rerun()

        with st.expander("商品统计"):
            st.write(f"浏览量：{stats['views']}")
            st.write(f"支付点击：{stats['pay_clicks']}")
            st.write(f"微信点击：{stats['wechat']}")
            st.write(f"支付宝点击：{stats['alipay']}")
            st.write(f"外链点击：{stats['external']}")
            st.write(f"联系点击：{stats['contact']}")
            st.write(f"转化率：{stats['conversion_rate']}%")

        st.markdown("---")
        if st.button("删除该商品", type="primary", use_container_width=True):
            products = get_products()
            target = None
            remain = []
            for p in products:
                if p["id"] == selected_id:
                    target = p
                else:
                    remain.append(p)

            save_products(remain)

            if target:
                paths = []
                if target.get("cover_image"):
                    paths.append(target["cover_image"])
                paths.extend(target.get("detail_images", []))
                for c in target.get("colors", []):
                    paths.extend(c.get("images", []))

                for path in paths:
                    try:
                        github_delete_file(path, f"delete image of product {selected_id}")
                    except:
                        pass

            stats_data = get_stats()
            stats_data = [x for x in stats_data if x.get("product_id") != selected_id]
            save_stats(stats_data)

            st.success("商品已删除")
            st.rerun()

    with tab2:
        with st.form("create_product_form"):
            name = st.text_input("商品名称")
            price = st.number_input("价格", value=0.0)
            original_price = st.number_input("原价", value=0.0)
            category = st.text_input("分类")
            intro = st.text_area("简介")
            stock = st.number_input("库存", value=0, step=1)
            status = st.selectbox("状态", ["up", "down"])

            st.markdown("#### 商品支付设置")
            wechat_link = st.text_input("微信支付链接")
            alipay_link = st.text_input("支付宝支付链接")
            external_link = st.text_input("外部购买链接")
            contact_text = st.text_input("联系购买说明")

            submitted = st.form_submit_button("新增商品", use_container_width=True)
            if submitted:
                if not name.strip():
                    st.error("商品名称不能为空")
                else:
                    products = get_products()
                    products.insert(0, {
                        "id": gen_id(),
                        "name": name.strip(),
                        "price": float(price),
                        "original_price": float(original_price),
                        "category": category.strip(),
                        "intro": intro.strip(),
                        "stock": int(stock),
                        "status": status,
                        "cover_image": "",
                        "detail_images": [],
                        "colors": [],
                        "wechat_link": wechat_link.strip(),
                        "alipay_link": alipay_link.strip(),
                        "external_link": external_link.strip(),
                        "contact_text": contact_text.strip(),
                        "created_at": now_str(),
                        "updated_at": now_str()
                    })
                    save_products(products)
                    st.success("商品新增成功")
                    st.rerun()


# =========================
# 主流程
# =========================
try:
    init_repo_data()
except Exception as e:
    st.error("初始化 GitHub 数据失败")
    st.exception(e)
    st.stop()

if "page" not in st.session_state:
    st.session_state.page = "home"

if "current_product_id" not in st.session_state:
    st.session_state.current_product_id = ""

with st.sidebar:
    st.title("菜单")
    mode = st.radio("模式", ["前台", "后台"])

    if mode == "前台":
        if st.button("商品首页", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()

    if mode == "后台":
        if admin_logged_in():
            page = st.radio("后台页面", ["数据看板", "商品管理", "支付设置"])
            if page == "数据看板":
                st.session_state.page = "admin_dashboard"
            elif page == "商品管理":
                st.session_state.page = "admin_products"
            elif page == "支付设置":
                st.session_state.page = "admin_settings"

            if st.button("退出登录", use_container_width=True):
                st.session_state.admin_logged_in = False
                st.success("已退出")
                st.rerun()
        else:
            render_admin_login()

if st.session_state.page == "home":
    render_home()
elif st.session_state.page == "product" and st.session_state.current_product_id:
    render_product_detail(st.session_state.current_product_id)
elif st.session_state.page == "admin_dashboard" and admin_logged_in():
    render_admin_dashboard()
elif st.session_state.page == "admin_products" and admin_logged_in():
    render_admin_products()
elif st.session_state.page == "admin_settings" and admin_logged_in():
    render_admin_settings()
else:
    render_home()