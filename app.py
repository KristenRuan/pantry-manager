import datetime
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import streamlit as st

# =====================================================================
# 全域常數 (集中管理，避免魔術字串散落各處)
# =====================================================================
DB_PATH = Path(__file__).parent / "pantry.db"

# --- 庫存狀態 ---
STATUS_UNOPENED = "未開封"
STATUS_OPENED = "已開封"
STATUS_IN_USE = "使用中"
STATUS_FINISHED = "已用完"
STATUS_DISCARDED = "已丟棄"
INVENTORY_STATUSES = [
    STATUS_UNOPENED,
    STATUS_OPENED,
    STATUS_IN_USE,
    STATUS_FINISHED,
    STATUS_DISCARDED,
]
# 入庫時可選的狀態 (較單純)
INTAKE_STATUSES = [STATUS_UNOPENED, STATUS_OPENED, STATUS_FINISHED]
# 代表「已消耗完畢、不需再列入庫存」的狀態
CONSUMED_STATUSES = (STATUS_FINISHED, STATUS_DISCARDED)

# --- 餐別 ---
MEAL_TYPES = ["早餐", "午餐", "晚餐", "點心"]

# --- 商品屬性代碼 (資料庫儲存代碼；畫面顯示中文) ---
ITEM_FOOD = "食品"
ITEM_DAILY = "日常消耗品"
ITEM_SKINCARE = "美妝保養品"
ITEM_TYPE_LABELS = {
    ITEM_FOOD: "食品",
    ITEM_DAILY: "日常消耗品",
    ITEM_SKINCARE: "美妝保養品 (支援效期與PAO開封期)",
}
ITEM_TYPE_OPTIONS = list(ITEM_TYPE_LABELS.keys())

# --- 保養時段 ---
ROUTINE_AM = "早安 AM"
ROUTINE_PM = "晚安 PM"
ROUTINE_BOTH = "早晚皆可"
ROUTINE_TIMES = [ROUTINE_AM, ROUTINE_PM, ROUTINE_BOTH]

# --- 想買清單優先度 ---
WISH_PRIORITIES = ["🔴 高 (急需)", "🟡 普通", "🟢 低 (有空再買)"]

ACTIVITY_OPTIONS = [1.2, 1.375, 1.55, 1.725, 1.9]
ACTIVITY_LABELS = {
    1.2: "久坐不動（幾乎不運動）",
    1.375: "輕度活動（每周運動 1-3 天）",
    1.55: "中度活動（每周運動 3-5 天）",
    1.725: "高度活動（每周運動 6-7 天）",
    1.9: "極高度活動（勞力密集工作或每天雙練）",
}

# 頁面基本設定
st.set_page_config(
    page_title="個人與多成員居家、食品、代購與美妝保養實驗庫",
    page_icon="🏠",
    layout="wide",
)


# =====================================================================
# 資料庫連線 (共用 context manager，自動 commit / close)
# =====================================================================
@contextmanager
def get_conn():
    """提供資料庫連線，離開區塊時自動 commit 並關閉。發生例外時仍會關閉。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def read_df(query, params=()):
    """執行查詢並回傳 DataFrame，失敗時回傳空 DataFrame 並顯示錯誤。"""
    try:
        with get_conn() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        st.error(f"讀取資料發生錯誤: {e}")
        return pd.DataFrame()


# =====================================================================
# 資料庫初始化
# =====================================================================
def init_db():
    with get_conn() as conn:
        c = conn.cursor()

        # 1. 分類表
        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)
        default_cats = [
            "零食", "生鮮", "冷凍", "飲料", "主食", "調味料",
            "日常消耗品", "衛浴清潔", "個人護理", "臉部保養",
            "彩妝香氛", "身體護理", "其他",
        ]
        for cat in default_cats:
            try:
                c.execute(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,)
                )
            except sqlite3.OperationalError:
                pass

        # 2. 商品/食品/保養品主檔
        c.execute("""
            CREATE TABLE IF NOT EXISTS food_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                barcode TEXT DEFAULT '',
                foreign_name TEXT,
                origin_country TEXT,
                brand TEXT,
                category TEXT,
                ingredients TEXT,
                usage_instructions TEXT,
                item_type TEXT DEFAULT '食品',
                routine_time TEXT DEFAULT '早晚皆可',
                routine_order INTEGER DEFAULT 1,
                skin_type TEXT DEFAULT '所有膚質',
                season TEXT DEFAULT '全年適用',
                calories REAL,
                protein REAL,
                fat REAL,
                carbs REAL,
                sugar REAL,
                sodium REAL
            )
        """)

        # 3. 批次庫存
        c.execute("""
            CREATE TABLE IF NOT EXISTS inventory_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_id INTEGER,
                channel TEXT,
                is_imported INTEGER DEFAULT 0,
                foreign_price TEXT,
                weight REAL,
                current_weight REAL,
                original_price REAL,
                price REAL,
                discount_info TEXT,
                unit_price REAL,
                purchase_date TEXT,
                expiry_date TEXT,
                opened_date TEXT,
                pao_months INTEGER DEFAULT 12,
                status TEXT,
                FOREIGN KEY (catalog_id) REFERENCES food_catalog (id)
            )
        """)

        # 4. 保養品/商品使用心得與實驗筆記表
        c.execute("""
            CREATE TABLE IF NOT EXISTS item_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                catalog_id INTEGER,
                user_id INTEGER,
                review_date TEXT,
                rating INTEGER,
                texture_feel TEXT,
                effectiveness TEXT,
                side_effects TEXT,
                re_buy_intent TEXT,
                notes TEXT,
                image_path TEXT,
                FOREIGN KEY (catalog_id) REFERENCES food_catalog (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # 相容舊資料庫的欄位補齊 (若欄位已存在會拋 OperationalError，直接略過)
        for col_sql in [
            "ALTER TABLE inventory_batches ADD COLUMN purchase_date TEXT DEFAULT ''",
            "ALTER TABLE inventory_batches ADD COLUMN current_weight REAL DEFAULT 0.0",
            "ALTER TABLE inventory_batches ADD COLUMN is_imported INTEGER DEFAULT 0",
            "ALTER TABLE inventory_batches ADD COLUMN foreign_price TEXT DEFAULT ''",
            "ALTER TABLE inventory_batches ADD COLUMN opened_date TEXT DEFAULT ''",
            "ALTER TABLE inventory_batches ADD COLUMN pao_months INTEGER DEFAULT 12",
            "ALTER TABLE food_catalog ADD COLUMN barcode TEXT DEFAULT ''",
            "ALTER TABLE food_catalog ADD COLUMN foreign_name TEXT DEFAULT ''",
            "ALTER TABLE food_catalog ADD COLUMN origin_country TEXT DEFAULT '台灣'",
            "ALTER TABLE food_catalog ADD COLUMN item_type TEXT DEFAULT '食品'",
            "ALTER TABLE food_catalog ADD COLUMN usage_instructions TEXT DEFAULT ''",
            "ALTER TABLE food_catalog ADD COLUMN routine_time TEXT DEFAULT '早晚皆可'",
            "ALTER TABLE food_catalog ADD COLUMN routine_order INTEGER DEFAULT 1",
            "ALTER TABLE food_catalog ADD COLUMN skin_type TEXT DEFAULT '所有膚質'",
            "ALTER TABLE food_catalog ADD COLUMN season TEXT DEFAULT '全年適用'",
            "ALTER TABLE item_reviews ADD COLUMN image_path TEXT DEFAULT ''",
        ]:
            try:
                c.execute(col_sql)
            except sqlite3.OperationalError:
                pass

        # 5. 菜單資料表
        c.execute("""
            CREATE TABLE IF NOT EXISTS recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                ingredients_detail TEXT,
                instructions TEXT
            )
        """)

        # 6. 系統設定表
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 7. 使用者資料表
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                gender TEXT,
                age INTEGER,
                height REAL,
                weight REAL,
                activity_level REAL,
                goal_deficit REAL
            )
        """)

        # 8. 每日飲食紀錄表
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                log_date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                food_name TEXT NOT NULL,
                weight REAL,
                calories REAL,
                protein REAL,
                fat REAL,
                carbs REAL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # 9. 體重歷史紀錄表
        c.execute("""
            CREATE TABLE IF NOT EXISTS weight_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                log_date TEXT NOT NULL,
                weight REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        # 10. 想買/待買清單 (手動記錄想購買的品項)
        c.execute("""
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                category TEXT,
                priority TEXT DEFAULT '普通',
                est_price REAL DEFAULT 0,
                channel TEXT DEFAULT '',
                note TEXT DEFAULT '',
                is_bought INTEGER DEFAULT 0,
                created_date TEXT
            )
        """)


def _blob_to_int(value):
    """把舊版誤存成 8-byte BLOB 的整數 (numpy int64) 還原為 Python int。"""
    if isinstance(value, (bytes, bytearray)):
        try:
            return int.from_bytes(value.ljust(8, b"\x00")[:8], "little", signed=True)
        except Exception:
            return None
    return value


def repair_blob_ids():
    """修復舊資料：inventory_batches / item_reviews 中被存成 BLOB 的外鍵欄位。

    早期版本直接把 pandas/numpy 的 int64 寫進資料庫，導致 catalog_id 等欄位
    以 8-byte BLOB 儲存，無法與整數主鍵 JOIN，庫存總覽因此顯示不出來。
    """
    fixes = [
        ("inventory_batches", "catalog_id"),
        ("item_reviews", "catalog_id"),
        ("item_reviews", "user_id"),
        ("daily_logs", "user_id"),
        ("weight_logs", "user_id"),
    ]
    try:
        with get_conn() as conn:
            c = conn.cursor()
            for table, col in fixes:
                try:
                    rows = c.execute(
                        f"SELECT id, {col} FROM {table} WHERE typeof({col}) = 'blob'"
                    ).fetchall()
                except sqlite3.OperationalError:
                    continue
                for r in rows:
                    fixed = _blob_to_int(r[col])
                    if fixed is not None:
                        c.execute(
                            f"UPDATE {table} SET {col} = ? WHERE id = ?",
                            (int(fixed), r["id"]),
                        )
    except Exception:
        # 修復失敗不應阻擋程式啟動
        pass


init_db()
repair_blob_ids()


# =====================================================================
# 資料存取輔助函式
# =====================================================================
def get_users_df():
    return read_df("SELECT * FROM users")


def get_setting(key, default_val=""):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default_val
    except Exception:
        return default_val


def set_setting(key, value):
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value)),
            )
    except Exception as e:
        st.error(f"儲存設定發生錯誤: {e}")


def get_categories():
    fallback = [
        "零食", "生鮮", "冷凍", "飲料", "主食", "調味料",
        "日常消耗品", "衛浴清潔", "個人護理", "臉部保養",
        "彩妝香氛", "身體護理", "其他",
    ]
    try:
        with get_conn() as conn:
            cats = [r["name"] for r in conn.execute("SELECT name FROM categories")]
            return cats if cats else fallback
    except Exception:
        return fallback


def item_type_label(code):
    """把資料庫中的 item_type 值轉成畫面顯示文字 (相容舊資料)。"""
    return ITEM_TYPE_LABELS.get(code, code or ITEM_FOOD)


def is_skincare(code):
    """判斷主檔屬性是否為保養品 (相容舊的長字串寫法)。"""
    return code == ITEM_SKINCARE or (code is not None and "保養" in str(code))


def deduct_inventory(cursor, catalog_id, amount):
    """依效期先進先出扣除某商品的庫存。回傳實際扣除量。"""
    rows = cursor.execute(
        "SELECT id, current_weight FROM inventory_batches "
        "WHERE catalog_id = ? AND status != ? AND status != ? "
        "ORDER BY expiry_date ASC",
        (catalog_id, STATUS_FINISHED, STATUS_DISCARDED),
    ).fetchall()
    remaining = float(amount)
    deducted = 0.0
    for b in rows:
        if remaining <= 0:
            break
        cur_w = float(b["current_weight"] or 0.0)
        if cur_w <= 0:
            continue
        if cur_w > remaining:
            cursor.execute(
                "UPDATE inventory_batches SET current_weight = ?, status = ? WHERE id = ?",
                (cur_w - remaining, STATUS_OPENED, b["id"]),
            )
            deducted += remaining
            remaining = 0.0
        else:
            cursor.execute(
                "UPDATE inventory_batches SET current_weight = 0.0, status = ? WHERE id = ?",
                (STATUS_FINISHED, b["id"]),
            )
            deducted += cur_w
            remaining -= cur_w
    return deducted


def check_expiry(date_str, opened_date_str="", pao_months=12, status=STATUS_UNOPENED):
    """回傳效期狀態文字。已開封者優先以 PAO 開封效期計算。"""
    if (
        status in (STATUS_OPENED, STATUS_IN_USE)
        and opened_date_str
        and str(opened_date_str).strip() not in ["", "None", "NaT"]
    ):
        try:
            opened = datetime.datetime.strptime(
                str(opened_date_str).split()[0], "%Y-%m-%d"
            ).date()
            pao_days = int(pao_months * 30.44)
            pao_exp = opened + datetime.timedelta(days=pao_days)
            delta_pao = (pao_exp - datetime.date.today()).days
            if delta_pao < 0:
                return "🔴 已過 PAO 開封期限"
            elif delta_pao <= 30:
                return f"🟡 開封期將至 ({delta_pao}天)"
        except Exception:
            pass

    if not date_str or str(date_str).strip() in ["", "None", "NaT"]:
        return "未知"
    try:
        exp = datetime.datetime.strptime(str(date_str).split()[0], "%Y-%m-%d").date()
        delta = (exp - datetime.date.today()).days
        if delta < 0:
            return "🔴 已過期"
        elif delta <= 7:
            return f"🟡 即期 ({delta}天)"
        else:
            return f"🟢 正常 ({delta}天)"
    except Exception:
        return "未知"


# =====================================================================
# 側邊欄全域設定
# =====================================================================
st.sidebar.title("🏠 居家、飲食與美妝保養庫")

users_df = get_users_df()

if users_df.empty:
    st.sidebar.warning(
        "⚠️ 目前無任何成員資料！請先至【👥 成員管理與目標設定】建立您的個人資料。"
    )
    current_user_id = None
    selected_user_name = None
    current_user_row = None
else:
    user_names = users_df["name"].tolist()
    selected_user_name = st.sidebar.selectbox("👤 目前操作成員", user_names)
    current_user_row = users_df[users_df["name"] == selected_user_name].iloc[0]
    current_user_id = int(current_user_row["id"])

st.sidebar.markdown("---")
menu = st.sidebar.selectbox(
    "選擇功能",
    [
        "🔥 每日飲食打卡與減脂儀表板",
        "📦 庫存與批次總覽 (含海外代購與PAO)",
        "📥 新增購買批次 (快速入庫)",
        "🏷️ 商品與保養品主檔管理",
        "📷 條碼掃描快速入庫 / 查詢",
        "📋 菜單、烹飪與冰箱推薦",
        "🛒 智能自動補貨清單 (含日用品/保養品)",
        "📝 想買/待買清單",
        "🛒 支出分析、預算與比價",
        "🧴 晨間 (AM) 與夜間 (PM) 保養 Routine 推薦",
        "🧪 保養品/商品使用心得與實驗筆記 (含照片)",
        "👥 成員管理與目標設定",
        "⚙️ 系統設定與資料清空",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("🏷️ 分類管理 (新增與刪除)")
current_cats = get_categories()

with st.sidebar.form("cat_manage_form", clear_on_submit=True):
    new_cat_input = st.text_input("新增自訂分類")
    if st.form_submit_button("新增分類"):
        if new_cat_input.strip():
            try:
                with get_conn() as conn:
                    conn.execute(
                        "INSERT INTO categories (name) VALUES (?)",
                        (new_cat_input.strip(),),
                    )
                st.success(f"成功新增：「{new_cat_input.strip()}」")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("分類名稱已存在！")
            except Exception as e:
                st.error(f"發生錯誤: {e}")

del_cat_target = st.sidebar.selectbox(
    "選擇要刪除的分類", ["-- 請選擇 --"] + current_cats
)
if st.sidebar.button("刪除所選分類"):
    if del_cat_target != "-- 請選擇 --":
        try:
            with get_conn() as conn:
                conn.execute("DELETE FROM categories WHERE name = ?", (del_cat_target,))
            st.sidebar.error(f"已刪除分類：「{del_cat_target}」")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"刪除失敗: {e}")


# =====================================================================
# 功能一：成員管理與目標設定
# =====================================================================
if menu == "👥 成員管理與目標設定":
    st.header("👥 家庭成員、姓名修改與減脂目標設定")
    tab_m1, tab_m2, tab_m3 = st.tabs(
        ["➕ 新增成員", "✏️ 編輯或刪除現有成員", "📈 記錄今日體重與個人趨勢圖"]
    )

    with tab_m1:
        with st.form("add_user_form", clear_on_submit=True):
            u_name = st.text_input("成員姓名 (例如：小明)")
            u_gender = st.selectbox("生理性別", ["男", "女"])
            u_age = st.number_input("年齡", min_value=1, max_value=120, value=25)
            u_height = st.number_input(
                "身高 (cm)", min_value=50.0, max_value=250.0, value=170.0
            )
            u_weight = st.number_input(
                "體重 (kg)", min_value=20.0, max_value=300.0, value=65.0
            )
            u_activity = st.selectbox(
                "日常活動量係數",
                options=ACTIVITY_OPTIONS,
                format_func=lambda x: ACTIVITY_LABELS[x],
            )
            u_deficit = st.number_input(
                "減脂熱量赤字 (大卡，建議 300 ~ 500)",
                min_value=0.0, max_value=1000.0, value=400.0, step=50.0,
            )

            if st.form_submit_button("新增成員"):
                if not u_name.strip():
                    st.error("請輸入成員姓名！")
                else:
                    try:
                        with get_conn() as conn:
                            c = conn.cursor()
                            c.execute(
                                """INSERT INTO users
                                (name, gender, age, height, weight, activity_level, goal_deficit)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (u_name.strip(), u_gender, u_age, u_height,
                                 u_weight, u_activity, u_deficit),
                            )
                            new_uid = c.lastrowid
                            c.execute(
                                "INSERT INTO weight_logs (user_id, log_date, weight) VALUES (?, ?, ?)",
                                (new_uid, str(datetime.date.today()), u_weight),
                            )
                        st.success(f"成功新增成員：「{u_name}」！")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("此成員名稱已經存在！")
                    except Exception as e:
                        st.error(f"發生錯誤: {e}")

    with tab_m2:
        fresh_users_df = get_users_df()
        if fresh_users_df.empty:
            st.info("目前沒有成員資料。")
        else:
            with st.form("edit_user_form_combined"):
                edit_u_name = st.selectbox(
                    "選擇要編輯的成員", fresh_users_df["name"].tolist()
                )
                row_u = fresh_users_df[fresh_users_df["name"] == edit_u_name].iloc[0]

                st.markdown(f"**正在編輯：{row_u['name']} (ID: {row_u['id']})**")

                eu_name = st.text_input("修改成員姓名", value=str(row_u["name"]))
                eu_gender = st.selectbox(
                    "生理性別", ["男", "女"],
                    index=0 if row_u["gender"] == "男" else 1,
                )
                eu_age = st.number_input(
                    "年齡", min_value=1, max_value=120, value=int(row_u["age"] or 25)
                )
                eu_height = st.number_input(
                    "身高 (cm)", min_value=50.0, max_value=250.0,
                    value=float(row_u["height"] or 170.0),
                )
                eu_weight = st.number_input(
                    "體重 (kg)", min_value=20.0, max_value=300.0,
                    value=float(row_u["weight"] or 65.0),
                )

                default_act_idx = (
                    ACTIVITY_OPTIONS.index(row_u["activity_level"])
                    if row_u["activity_level"] in ACTIVITY_OPTIONS
                    else 0
                )
                eu_activity = st.selectbox(
                    "日常活動量係數",
                    options=ACTIVITY_OPTIONS,
                    index=default_act_idx,
                    format_func=lambda x: ACTIVITY_LABELS[x],
                )
                eu_deficit = st.number_input(
                    "減脂熱量赤字 (大卡)",
                    min_value=0.0, max_value=1000.0,
                    value=float(row_u["goal_deficit"] or 400.0),
                )

                if st.form_submit_button("儲存修改"):
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                """UPDATE users
                                SET name = ?, gender = ?, age = ?, height = ?,
                                    weight = ?, activity_level = ?, goal_deficit = ?
                                WHERE id = ?""",
                                (eu_name.strip(), eu_gender, eu_age, eu_height,
                                 eu_weight, eu_activity, eu_deficit, int(row_u["id"])),
                            )
                        st.success("成員資料與姓名更新成功！")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("此成員名稱已經存在，請更換其他名稱！")
                    except Exception as e:
                        st.error(f"更新失敗: {e}")

            st.markdown("---")
            with st.expander("⚠️ 危險區域：刪除成員"):
                del_target_name = st.selectbox(
                    "選擇要刪除的成員",
                    fresh_users_df["name"].tolist(),
                    key="del_select",
                )
                del_row = fresh_users_df[
                    fresh_users_df["name"] == del_target_name
                ].iloc[0]

                if st.button("確認永久刪除此成員", key="confirm_del_btn"):
                    if len(fresh_users_df) <= 1:
                        st.error("⚠️ 系統中至少需保留一位成員，無法全部刪除！")
                    else:
                        try:
                            uid = int(del_row["id"])
                            with get_conn() as conn:
                                c = conn.cursor()
                                c.execute("DELETE FROM daily_logs WHERE user_id = ?", (uid,))
                                c.execute("DELETE FROM weight_logs WHERE user_id = ?", (uid,))
                                c.execute("DELETE FROM item_reviews WHERE user_id = ?", (uid,))
                                c.execute("DELETE FROM users WHERE id = ?", (uid,))
                            st.success(f"已成功刪除成員：{del_target_name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗: {e}")

    with tab_m3:
        if users_df.empty:
            st.info("請先新增成員。")
        else:
            st.subheader(f"📈 【{selected_user_name}】的體重變化紀錄與趨勢")
            with st.form("weight_log_form", clear_on_submit=True):
                w_date = st.date_input("記錄日期", datetime.date.today())
                new_w = st.number_input(
                    "今日量測體重 (kg)", min_value=20.0, max_value=300.0,
                    value=float(current_user_row["weight"] or 65.0),
                )
                if st.form_submit_button("儲存體重並自動更新 TDEE"):
                    try:
                        with get_conn() as conn:
                            c = conn.cursor()
                            c.execute(
                                "INSERT INTO weight_logs (user_id, log_date, weight) VALUES (?, ?, ?)",
                                (current_user_id, str(w_date), new_w),
                            )
                            c.execute(
                                "UPDATE users SET weight = ? WHERE id = ?",
                                (new_w, current_user_id),
                            )
                        st.success(f"成功記錄體重 {new_w} kg！TDEE 已自動重新計算。")
                        st.rerun()
                    except Exception as e:
                        st.error(f"記錄失敗: {e}")

            st.markdown("---")
            w_logs_df = read_df(
                "SELECT log_date, weight FROM weight_logs WHERE user_id = ? ORDER BY log_date ASC",
                (current_user_id,),
            )
            if not w_logs_df.empty:
                w_logs_df["log_date"] = pd.to_datetime(w_logs_df["log_date"])
                st.line_chart(w_logs_df.set_index("log_date"), y="weight")
                st.caption("💡 堅持記錄體重，看著曲線穩健下降，減脂更有動力！")


# =====================================================================
# 功能二：每日飲食打卡與減脂儀表板
# =====================================================================
elif menu == "🔥 每日飲食打卡與減脂儀表板":
    if users_df.empty:
        st.warning("⚠️ 請先至【👥 成員管理與目標設定】建立成員！")
    else:
        st.header(f"🔥 【{selected_user_name}】的每日飲食打卡與減脂儀表板")
        gender = current_user_row["gender"]
        weight = float(current_user_row["weight"])
        height = float(current_user_row["height"])
        age = int(current_user_row["age"])
        activity = float(current_user_row["activity_level"])
        deficit = float(current_user_row["goal_deficit"])

        bmr = (
            (10 * weight) + (6.25 * height) - (5 * age) + 5
            if gender == "男"
            else (10 * weight) + (6.25 * height) - (5 * age) - 161
        )
        tdee = bmr * activity
        target_calories = max(tdee - deficit, 1200)

        # 三大營養素黃金比例
        target_protein = weight * 1.8
        protein_calories = target_protein * 4
        fat_calories = target_calories * 0.25
        target_fat = fat_calories / 9.0
        carb_calories = target_calories - protein_calories - fat_calories
        target_carbs = max(carb_calories / 4.0, 50.0)

        c1, c2, c3 = st.columns(3)
        c1.metric("基礎代謝 (BMR)", f"{bmr:.0f} 大卡")
        c2.metric("每日總消耗 (TDEE)", f"{tdee:.0f} 大卡")
        c3.metric("🎯 減脂建議熱量上限", f"{target_calories:.0f} 大卡")

        st.markdown("##### 🎯 三大營養素（Macros）每日建議目標")
        cm1, cm2, cm3 = st.columns(3)
        cm1.metric("💪 建議蛋白質", f"{target_protein:.1f} g", f"佔 {protein_calories:.0f} 大卡")
        cm2.metric("🥑 建議脂肪 (25%)", f"{target_fat:.1f} g", f"佔 {fat_calories:.0f} 大卡")
        cm3.metric("🍞 建議碳水", f"{target_carbs:.1f} g", f"佔 {carb_calories:.0f} 大卡")

        st.markdown("---")
        selected_log_date = st.date_input("選擇打卡日期", datetime.date.today())
        date_str = str(selected_log_date)

        logs_df = read_df(
            "SELECT * FROM daily_logs WHERE user_id = ? AND log_date = ?",
            (current_user_id, date_str),
        )
        recipes_df = read_df("SELECT id, title, ingredients_detail FROM recipes")
        cat_df = read_df(
            "SELECT id, name, foreign_name, calories, protein, fat, carbs "
            "FROM food_catalog WHERE item_type = ?",
            (ITEM_FOOD,),
        )

        def col_sum(df, col):
            return df[col].sum() if not df.empty and col in df else 0.0

        total_cal = col_sum(logs_df, "calories")
        total_pro = col_sum(logs_df, "protein")
        total_fat = col_sum(logs_df, "fat")
        total_carbs = col_sum(logs_df, "carbs")

        st.subheader(f"📊 {date_str} 營養攝取進度儀表板")
        cp1, cp2 = st.columns(2)
        with cp1:
            st.markdown(f"**熱量攝取：{total_cal:.1f} / {target_calories:.0f} 大卡**")
            st.progress(min(total_cal / target_calories, 1.0) if target_calories > 0 else 0)
            if total_cal > target_calories:
                st.warning("⚠️ 今日熱量已超過減脂目標上限！")
            else:
                st.success(f"🟢 距離熱量上限還有：{target_calories - total_cal:.1f} 大卡")
        with cp2:
            st.markdown("**三大營養素達成狀況**")
            st.info(
                f"💪 蛋白質: {total_pro:.1f} / {target_protein:.1f} g\n\n"
                f"🥑 脂肪: {total_fat:.1f} / {target_fat:.1f} g\n\n"
                f"🍞 碳水: {total_carbs:.1f} / {target_carbs:.1f} g"
            )

        if not logs_df.empty:
            st.markdown("#### 📝 今日已打卡明細")
            st.dataframe(
                logs_df[["meal_type", "food_name", "weight",
                         "calories", "protein", "fat", "carbs"]],
                width="stretch",
            )
            del_log_id = st.selectbox(
                "選擇要刪除的打卡紀錄",
                options=logs_df["id"].tolist(),
                format_func=lambda x: (
                    f"ID {x} - "
                    f"{logs_df[logs_df['id'] == x]['meal_type'].values[0]}: "
                    f"{logs_df[logs_df['id'] == x]['food_name'].values[0]}"
                ),
            )
            if st.button("刪除選定打卡紀錄"):
                try:
                    with get_conn() as conn:
                        conn.execute("DELETE FROM daily_logs WHERE id = ?", (int(del_log_id),))
                    st.success("已成功刪除該筆打卡！")
                    st.rerun()
                except Exception as e:
                    st.error(f"刪除失敗: {e}")

        st.markdown("---")
        tab_log1, tab_log2, tab_log3 = st.tabs(
            ["🍳 從智慧菜單匯入", "🥫 從現成食品主檔選取", "✍️ 自訂/外食輸入"]
        )

        with tab_log1:
            if recipes_df.empty:
                st.info("目前還沒有建立任何菜單！")
            else:
                with st.form("log_recipe_form", clear_on_submit=True):
                    meal_type = st.selectbox("餐別", MEAL_TYPES, key="meal_r")
                    selected_recipe_title = st.selectbox(
                        "選擇菜單", recipes_df["title"].tolist()
                    )
                    if st.form_submit_button("匯入此菜單營養"):
                        r_row = recipes_df[
                            recipes_df["title"] == selected_recipe_title
                        ].iloc[0]
                        details = r_row["ingredients_detail"]
                        r_cal = r_pro = r_fat = r_carbs = 0.0
                        full_c_df = read_df("SELECT * FROM food_catalog")
                        if details and not full_c_df.empty:
                            for item in details.split(","):
                                if ":" in item:
                                    fname, famt_str = item.split(":")
                                    try:
                                        famt = float(famt_str)
                                    except ValueError:
                                        continue
                                    m = full_c_df[full_c_df["name"] == fname]
                                    if not m.empty:
                                        ratio = famt / 100.0
                                        r_cal += float(m["calories"].values[0] or 0) * ratio
                                        r_pro += float(m["protein"].values[0] or 0) * ratio
                                        r_fat += float(m["fat"].values[0] or 0) * ratio
                                        r_carbs += float(m["carbs"].values[0] or 0) * ratio
                        try:
                            with get_conn() as conn:
                                conn.execute(
                                    """INSERT INTO daily_logs
                                    (user_id, log_date, meal_type, food_name, weight,
                                     calories, protein, fat, carbs)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (current_user_id, date_str, meal_type,
                                     f"[菜單] {selected_recipe_title}", 0.0,
                                     r_cal, r_pro, r_fat, r_carbs),
                                )
                            st.success("打卡成功！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"打卡失敗: {e}")

        with tab_log2:
            if cat_df.empty:
                st.info("目前沒有任何食品主檔，請先至「商品與保養品主檔管理」新增！")
            else:
                search_kw = st.text_input("🔍 輸入關鍵字搜尋食品", "", key="food_search_kw")
                if search_kw:
                    filtered_cat_df = cat_df[
                        cat_df["name"].str.contains(search_kw, case=False, na=False)
                        | cat_df["foreign_name"].str.contains(search_kw, case=False, na=False)
                    ]
                else:
                    filtered_cat_df = cat_df
                if filtered_cat_df.empty:
                    st.warning("找不到符合關鍵字的食品！")
                else:
                    with st.form("log_catalog_form", clear_on_submit=True):
                        meal_type_c = st.selectbox("餐別", MEAL_TYPES, key="meal_c")
                        selected_food_name = st.selectbox(
                            "選擇食品", filtered_cat_df["name"].tolist()
                        )
                        consume_weight = st.number_input(
                            "食用克數/毫升", min_value=1.0, value=100.0
                        )
                        auto_deduct = st.checkbox("同步自動扣除冰箱庫存", value=True)
                        if st.form_submit_button("確認打卡並計入營養素"):
                            f_row = cat_df[cat_df["name"] == selected_food_name].iloc[0]
                            ratio = consume_weight / 100.0
                            try:
                                with get_conn() as conn:
                                    c = conn.cursor()
                                    c.execute(
                                        """INSERT INTO daily_logs
                                        (user_id, log_date, meal_type, food_name, weight,
                                         calories, protein, fat, carbs)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                        (current_user_id, date_str, meal_type_c,
                                         f"[現成] {selected_food_name}", consume_weight,
                                         float(f_row["calories"] or 0) * ratio,
                                         float(f_row["protein"] or 0) * ratio,
                                         float(f_row["fat"] or 0) * ratio,
                                         float(f_row["carbs"] or 0) * ratio),
                                    )
                                    if auto_deduct:
                                        deduct_inventory(c, int(f_row["id"]), consume_weight)
                                msg = "打卡成功！"
                                if auto_deduct:
                                    msg += " 已同步扣除冰箱庫存。"
                                st.success(msg)
                                st.rerun()
                            except Exception as e:
                                st.error(f"打卡或扣庫存發生錯誤: {e}")

        with tab_log3:
            with st.form("log_manual_form", clear_on_submit=True):
                meal_type_m = st.selectbox("餐別", MEAL_TYPES, key="meal_m")
                manual_name = st.text_input("外食名稱")
                m_cal = st.number_input("總熱量 (大卡)", min_value=0.0, value=150.0)
                m_pro = st.number_input("蛋白質 (g)", min_value=0.0, value=15.0)
                m_fat = st.number_input("脂肪 (g)", min_value=0.0, value=5.0)
                m_carbs = st.number_input("碳水 (g)", min_value=0.0, value=10.0)
                if st.form_submit_button("確認新增外食打卡"):
                    if not manual_name.strip():
                        st.error("請輸入食物名稱！")
                    else:
                        try:
                            with get_conn() as conn:
                                conn.execute(
                                    """INSERT INTO daily_logs
                                    (user_id, log_date, meal_type, food_name, weight,
                                     calories, protein, fat, carbs)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (current_user_id, date_str, meal_type_m,
                                     manual_name.strip(), 100.0,
                                     m_cal, m_pro, m_fat, m_carbs),
                                )
                            st.success("新增成功！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"新增失敗: {e}")

        # 最近 7 天營養週報
        st.markdown("---")
        st.subheader("📅 最近 7 天平均每日攝取熱量週報")
        seven_days_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        week_df = read_df(
            "SELECT log_date, SUM(calories) as total_cal FROM daily_logs "
            "WHERE user_id = ? AND log_date >= ? GROUP BY log_date ORDER BY log_date DESC",
            (current_user_id, seven_days_ago),
        )
        if week_df.empty:
            st.info("最近 7 天尚無足夠的打卡紀錄可以產生週報。")
        else:
            avg_cal = week_df["total_cal"].mean()
            st.metric(
                "最近 7 天每日平均攝取熱量",
                f"{avg_cal:.1f} 大卡",
                f"目標上限: {target_calories:.0f} 大卡",
            )
            if avg_cal <= target_calories:
                st.success("🌟 過去一週平均熱量控制在減脂目標之內，表現非常棒！")
            else:
                st.warning("💡 過去一週平均熱量稍高，建議週末稍微調整飲食結構。")


# =====================================================================
# 功能三：庫存與批次總覽 (含海外代購與PAO、修改與刪除)
# =====================================================================
elif menu == "📦 庫存與批次總覽 (含海外代購與PAO)":
    st.header("📦 居家庫存與效期總覽 (含保養品 PAO 與海外代購)")

    query = """
        SELECT
            b.id as batch_id,
            b.catalog_id,
            COALESCE(c.name, '未知商品') as name,
            COALESCE(c.foreign_name, '') as foreign_name,
            COALESCE(c.usage_instructions, '') as 使用方法,
            c.routine_time as 保養時段,
            c.routine_order as 順序,
            COALESCE(c.origin_country, '台灣') as origin_country,
            COALESCE(c.item_type, '食品') as 屬性,
            CASE WHEN b.is_imported = 1 THEN '✈️ 海外代購' ELSE '🏠 本地一般' END as 採購來源,
            b.foreign_price as 外幣價格,
            b.channel as 購買管道,
            b.price as 台幣花費,
            b.current_weight as 剩餘量,
            b.status as 狀態,
            b.opened_date as 開封日期,
            b.pao_months as PAO月數,
            b.expiry_date as 有效期限
        FROM inventory_batches b
        LEFT JOIN food_catalog c ON b.catalog_id = c.id
    """
    df = read_df(query)
    catalog_df = read_df("SELECT id, name FROM food_catalog")

    if df.empty:
        st.info("目前庫存無資料。")
    else:
        df["效期狀態"] = df.apply(
            lambda row: check_expiry(
                row["有效期限"], row["開封日期"], row["PAO月數"], row["狀態"]
            ),
            axis=1,
        )

        # 非保養品不顯示保養時段與順序。
        # 統一轉成字串顯示，避免 Arrow 對 int/字串混合欄位序列化失敗。
        skincare_mask = df["屬性"].apply(is_skincare)
        for col in ["保養時段", "順序"]:
            df[col] = df.apply(
                lambda r, _c=col: (
                    ""
                    if not is_skincare(r["屬性"]) or pd.isna(r[_c])
                    else (
                        str(int(r[_c])) if _c == "順序" else str(r[_c])
                    )
                ),
                axis=1,
            )

        st.subheader("📋 目前庫存清單")
        display_df = df.drop(columns=["catalog_id"], errors="ignore")
        # 若清單中完全沒有保養品，直接隱藏保養相關欄位
        if not skincare_mask.any():
            display_df = display_df.drop(columns=["保養時段", "順序"], errors="ignore")
        st.dataframe(display_df, width="stretch")

        st.markdown("---")
        st.subheader("✏️ 庫存批次管理：修改與刪除")

        sel_batch_id = st.selectbox(
            "選擇要管理的庫存批次 ID",
            df["batch_id"].tolist(),
            format_func=lambda x: (
                f"ID {x} - {df[df['batch_id'] == x]['name'].values[0]} "
                f"(效期: {df[df['batch_id'] == x]['有效期限'].values[0]})"
            ),
        )

        if sel_batch_id:
            r_sel = df[df["batch_id"] == sel_batch_id].iloc[0]

            with st.form("edit_batch_form"):
                ce1, ce2 = st.columns(2)
                with ce1:
                    current_cat_id = r_sel["catalog_id"]
                    catalog_ids = catalog_df["id"].tolist() if not catalog_df.empty else []
                    default_index = (
                        catalog_ids.index(current_cat_id)
                        if current_cat_id in catalog_ids else 0
                    )
                    new_catalog_id = st.selectbox(
                        "關聯商品主檔 *",
                        catalog_ids,
                        index=default_index if catalog_ids else 0,
                        format_func=lambda x: (
                            catalog_df[catalog_df["id"] == x]["name"].values[0]
                            if not catalog_df.empty else str(x)
                        ),
                    )

                    current_status = str(r_sel["狀態"])
                    status_idx = (
                        INVENTORY_STATUSES.index(current_status)
                        if current_status in INVENTORY_STATUSES else 0
                    )
                    new_status = st.selectbox("狀態", INVENTORY_STATUSES, index=status_idx)

                    new_weight = st.number_input(
                        "剩餘量 / 重量",
                        value=float(r_sel["剩餘量"]) if pd.notna(r_sel["剩餘量"]) else 0.0,
                    )
                    new_price = st.number_input(
                        "台幣花費",
                        value=float(r_sel["台幣花費"]) if pd.notna(r_sel["台幣花費"]) else 0.0,
                    )

                with ce2:
                    import_val = "海外代購" in str(r_sel["採購來源"])
                    new_is_imported = st.checkbox("是否為海外代購", value=import_val)
                    new_channel = st.text_input(
                        "購買管道",
                        value=str(r_sel["購買管道"]) if pd.notna(r_sel["購買管道"]) else "",
                    )
                    new_pao = st.number_input(
                        "PAO 開封後有效月數", min_value=0,
                        value=int(r_sel["PAO月數"]) if pd.notna(r_sel["PAO月數"]) else 12,
                    )

                    try:
                        default_expiry = (
                            datetime.datetime.strptime(str(r_sel["有效期限"]), "%Y-%m-%d").date()
                            if pd.notna(r_sel["有效期限"]) and str(r_sel["有效期限"]) != ""
                            else datetime.date.today()
                        )
                    except Exception:
                        default_expiry = datetime.date.today()
                    new_expiry = st.date_input("有效期限", value=default_expiry)

                    try:
                        default_opened = (
                            datetime.datetime.strptime(str(r_sel["開封日期"]), "%Y-%m-%d").date()
                            if pd.notna(r_sel["開封日期"]) and str(r_sel["開封日期"]) != ""
                            else None
                        )
                    except Exception:
                        default_opened = None

                    if new_status in (STATUS_IN_USE, STATUS_OPENED) and not default_opened:
                        default_opened = datetime.date.today()

                    new_opened = st.date_input(
                        "開封日期 (若已開封請填寫)", value=default_opened
                    )

                cs1, cs2 = st.columns(2)
                update_btn = cs1.form_submit_button("💾 儲存修改")
                delete_btn = cs2.form_submit_button("🗑️ 刪除此批次", type="primary")

                if update_btn:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                """UPDATE inventory_batches
                                SET catalog_id = ?, status = ?, current_weight = ?, price = ?,
                                    is_imported = ?, channel = ?, pao_months = ?,
                                    expiry_date = ?, opened_date = ?
                                WHERE id = ?""",
                                (int(new_catalog_id), new_status, new_weight, new_price,
                                 1 if new_is_imported else 0, new_channel, new_pao,
                                 str(new_expiry), str(new_opened) if new_opened else None,
                                 int(sel_batch_id)),
                            )
                        st.success("庫存批次更新成功！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"更新失敗: {e}")

                if delete_btn:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                "DELETE FROM inventory_batches WHERE id = ?",
                                (int(sel_batch_id),),
                            )
                        st.success("已成功刪除該筆庫存批次！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"刪除失敗: {e}")


# =====================================================================
# 功能四：晨間 (AM) 與夜間 (PM) 保養 Routine 推薦
# =====================================================================
elif menu == "🧴 晨間 (AM) 與夜間 (PM) 保養 Routine 推薦":
    st.header("🧴 您的個人晨間 (AM) 與夜間 (PM) 保養步驟清單")
    routine_df = read_df(
        """SELECT c.name, c.foreign_name, c.brand, c.routine_time, c.routine_order,
                  c.usage_instructions, b.status, b.current_weight
           FROM inventory_batches b
           JOIN food_catalog c ON b.catalog_id = c.id
           WHERE (c.item_type = ? OR c.item_type LIKE '%保養%') AND b.status != ?
           ORDER BY c.routine_order ASC""",
        (ITEM_SKINCARE, STATUS_FINISHED),
    )

    if routine_df.empty:
        st.info("目前庫存中沒有找到庫存充足的保養品！請先至「新增購買批次」入庫您的保養品。")
    else:
        tab_am, tab_pm = st.tabs(["☀️ 晨間保養清單 (AM)", "🌙 夜間保養清單 (PM)"])

        def render_routine(items):
            for _, row in items.iterrows():
                with st.container():
                    st.markdown(f"### 步驟 {row['routine_order']}：{row['name']} ({row['brand']})")
                    if row["foreign_name"]:
                        st.caption(f"外文名：{row['foreign_name']}")
                    st.info(f"💡 **使用方法**：{row['usage_instructions'] or '無特別說明'}")
                    st.markdown("---")

        with tab_am:
            am_items = routine_df[routine_df["routine_time"].isin([ROUTINE_AM, ROUTINE_BOTH])]
            if am_items.empty:
                st.info("目前沒有設定晨間保養品。")
            else:
                render_routine(am_items)

        with tab_pm:
            pm_items = routine_df[routine_df["routine_time"].isin([ROUTINE_PM, ROUTINE_BOTH])]
            if pm_items.empty:
                st.info("目前沒有設定夜間保養品。")
            else:
                render_routine(pm_items)


# =====================================================================
# 功能五：商品與保養品主檔管理
# =====================================================================
elif menu == "🏷️ 商品與保養品主檔管理":
    st.header("🏷️ 商品與保養品主檔管理")
    tab1, tab2 = st.tabs(["📋 現有主檔列表", "➕ 新增商品主檔"])

    with tab1:
        cat_df = read_df("SELECT * FROM food_catalog")
        if cat_df.empty:
            st.info("目前尚無商品主檔。")
        else:
            st.dataframe(cat_df, width="stretch")
            st.markdown("---")
            st.subheader("🗑️ 刪除商品主檔")
            del_cat_id = st.selectbox(
                "選擇要刪除的主檔 ID (注意：若有庫存批次正在使用，請先刪除對應庫存)",
                cat_df["id"].tolist(),
                format_func=lambda x: f"ID {x} - {cat_df[cat_df['id'] == x]['name'].values[0]}",
            )
            if st.button("確認刪除此主檔", type="primary"):
                try:
                    with get_conn() as conn:
                        conn.execute(
                            "DELETE FROM food_catalog WHERE id = ?", (int(del_cat_id),)
                        )
                    st.success("主檔刪除成功！")
                    st.rerun()
                except Exception as e:
                    st.error(f"刪除失敗 (可能已有庫存批次正在使用此主檔): {e}")

    with tab2:
        st.subheader("新增商品或保養品主檔")
        with st.form("add_catalog_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("商品名稱 (中文) *")
                foreign_name = st.text_input("外文名稱 / 品牌規格 (選填)")
                brand = st.text_input("品牌")
                barcode = st.text_input("條碼 (選填)")
                origin_country = st.selectbox(
                    "產地", ["台灣", "日本", "韓國", "美國", "法國", "英國", "其他"]
                )
            with c2:
                category = st.selectbox("分類", current_cats)
                item_type = st.selectbox(
                    "商品屬性類型",
                    ITEM_TYPE_OPTIONS,
                    format_func=item_type_label,
                )
                ingredients = st.text_area("成分 / 材質說明")

            st.markdown("**營養標示 (每 100g / 100ml，非食品可留 0)**")
            n1, n2, n3, n4, n5, n6 = st.columns(6)
            calories = n1.number_input("熱量", min_value=0.0, value=0.0)
            protein = n2.number_input("蛋白質", min_value=0.0, value=0.0)
            fat = n3.number_input("脂肪", min_value=0.0, value=0.0)
            carbs = n4.number_input("碳水", min_value=0.0, value=0.0)
            sugar = n5.number_input("糖", min_value=0.0, value=0.0)
            sodium = n6.number_input("鈉", min_value=0.0, value=0.0)

            # 非保養品不帶入保養時段等專屬欄位
            routine_time, routine_order = None, None
            skin_type, season = None, None
            if item_type == ITEM_SKINCARE:
                st.markdown("---")
                st.markdown("**🧴 保養品專屬進階設定**")
                rt1, rt2, rt3, rt4 = st.columns(4)
                routine_time = rt1.selectbox("保養時段", ROUTINE_TIMES)
                routine_order = rt2.number_input(
                    "保養步驟順序", min_value=1, max_value=20, value=1
                )
                skin_type = rt3.selectbox(
                    "適用膚質", ["所有膚質", "油肌", "乾肌", "混合肌", "敏感肌"]
                )
                season = rt4.selectbox(
                    "適用季節", ["全年適用", "春季", "夏季", "秋季", "冬季"]
                )

            usage_instructions = st.text_area(
                "💡 使用方法 / 步驟說明 (例如：早晚清潔後，取適量於化妝棉輕拍全臉)"
            )

            if st.form_submit_button("💾 儲存新主檔"):
                if not name.strip():
                    st.error("請至少填寫商品名稱！")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                """INSERT INTO food_catalog (
                                    name, foreign_name, brand, barcode, origin_country,
                                    category, item_type, ingredients,
                                    routine_time, routine_order, skin_type, season,
                                    usage_instructions,
                                    calories, protein, fat, carbs, sugar, sodium
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (name.strip(), foreign_name, brand, barcode, origin_country,
                                 category, item_type, ingredients,
                                 routine_time, routine_order, skin_type, season,
                                 usage_instructions,
                                 calories, protein, fat, carbs, sugar, sodium),
                            )
                        st.success(f"成功新增主檔：{name}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("這個商品名稱已經存在主檔中囉！")
                    except Exception as e:
                        st.error(f"新增主檔失敗: {e}")


# =====================================================================
# 功能六：條碼掃描快速入庫 / 查詢
# =====================================================================
elif menu == "📷 條碼掃描快速入庫 / 查詢":
    st.header("📷 商品條碼快速掃描與入庫查詢")
    st.info("💡 您可以拍照上傳商品條碼照片，或直接輸入條碼編號快速進行商品識別！")

    scan_tab1, scan_tab2 = st.tabs(["📸 拍照/上傳條碼快速搜尋", "⌨️ 輸入條碼代碼查詢"])

    with scan_tab1:
        barcode_img = st.file_uploader(
            "拍下商品條碼或上傳條碼圖片", type=["jpg", "jpeg", "png"]
        )
        if barcode_img is not None:
            st.image(barcode_img, caption="已上傳的條碼照片", width=300)
            st.success("✅ 圖片上傳成功！(模擬條碼解析中...)")
            cat_df = read_df("SELECT name, brand, item_type, barcode FROM food_catalog")
            if not cat_df.empty:
                matched_items = cat_df[
                    cat_df["barcode"].notna() & (cat_df["barcode"] != "")
                ]
                if not matched_items.empty:
                    st.subheader("🎯 主檔中已登記條碼的商品：")
                    for _, row in matched_items.iterrows():
                        st.markdown(
                            f"**品名：** {row['name']} | **品牌：** {row['brand']} "
                            f"| **類型：** {item_type_label(row['item_type'])}"
                        )
                else:
                    st.warning("⚠️ 目前主檔中尚無登記條碼的商品，請至【商品主檔管理】補填條碼！")

    with scan_tab2:
        with st.form("manual_barcode_form"):
            input_code = st.text_input("請輸入或使用掃描器輸入條碼數字")
            if st.form_submit_button("搜尋條碼"):
                if input_code.strip():
                    res_df = read_df(
                        "SELECT name, brand FROM food_catalog WHERE barcode = ?",
                        (input_code.strip(),),
                    )
                    if not res_df.empty:
                        r = res_df.iloc[0]
                        st.success(f"🎉 找到對應商品：【{r['name']}】(品牌: {r['brand']})")
                    else:
                        st.error("❌ 找不到此條碼對應的商品，請先至主檔建立！")


# =====================================================================
# 功能七：使用心得與實驗筆記 (保養品 / 食品 / 日用品皆可，含照片)
# =====================================================================
elif menu == "🧪 保養品/商品使用心得與實驗筆記 (含照片)":
    st.header("🧪 商品「實驗與使用心得」筆記 (保養品 / 食品 / 日用品皆可，含照片)")

    cat_df = read_df(
        "SELECT id, name, brand, item_type, usage_instructions FROM food_catalog"
    )
    reviews_df = read_df(
        """SELECT r.*, c.name as product_name, c.item_type as item_type,
                  u.name as user_name
           FROM item_reviews r
           LEFT JOIN food_catalog c ON r.catalog_id = c.id
           LEFT JOIN users u ON r.user_id = u.id"""
    )

    # 依商品屬性提供對應的欄位文案 (保養品 / 食品 / 一般日用品)
    def review_labels(item_type):
        if is_skincare(item_type):
            return {
                "field2": "質地與吸收感受 (例如：質地清爽水潤)",
                "field3": "短期/長期效果 (例如：連續用7天毛孔變細)",
                "field4": "不良反應/副作用 (例如：無過敏)",
                "rating": "綜合評分 (⭐ 蜜糖到 💩 毒藥)",
                "photo": "📸 上傳膚況對比照 / 使用前後照片",
                "label2": "質地感受",
                "label3": "使用效果",
                "label4": "不良反應",
            }
        elif item_type == ITEM_FOOD:
            return {
                "field2": "口感/風味 (例如：口感綿密、不會太甜)",
                "field3": "料理/搭配方式 (例如：加燕麥當早餐很讚)",
                "field4": "身體反應/注意事項 (例如：乳糖不耐者少量)",
                "rating": "綜合評分 (⭐ 好吃到 💩 難吃)",
                "photo": "📸 上傳實品/開箱照片 (選填)",
                "label2": "口感風味",
                "label3": "料理搭配",
                "label4": "身體反應",
            }
        else:  # 日常消耗品 / 其他
            return {
                "field2": "使用感受 (例如：好推好清洗、味道好聞)",
                "field3": "實際效果 (例如：去污力強、很耐用)",
                "field4": "缺點/注意事項 (例如：包裝易漏)",
                "rating": "綜合評分 (⭐ 好用到 💩 難用)",
                "photo": "📸 上傳實品/使用照片 (選填)",
                "label2": "使用感受",
                "label3": "實際效果",
                "label4": "缺點注意",
            }

    tab_rev_add, tab_rev_list = st.tabs(
        ["✍️ 新增使用心得", "📖 查看所有心得與紀錄"]
    )

    with tab_rev_add:
        if cat_df.empty:
            st.warning("請先至「商品與保養品主檔管理」建立商品！")
        elif current_user_id is None:
            st.warning("請先至【👥 成員管理與目標設定】建立並選擇成員！")
        else:
            # 商品選擇放在表單外，切換商品時即時更新對應文案
            sel_prod = st.selectbox("選擇商品 (保養品 / 食品 / 日用品皆可)", cat_df["name"].tolist())
            selected_prod_row = cat_df[cat_df["name"] == sel_prod].iloc[0]
            sel_item_type = selected_prod_row["item_type"]
            st.caption(f"屬性：{item_type_label(sel_item_type)}")
            L = review_labels(sel_item_type)

            if (
                pd.notna(selected_prod_row["usage_instructions"])
                and str(selected_prod_row["usage_instructions"]).strip()
            ):
                st.info(f"💡 **記錄的使用方法**：{selected_prod_row['usage_instructions']}")

            with st.form("review_form", clear_on_submit=True):
                r_date = st.date_input("心得記錄日期", datetime.date.today())
                cr1, cr2 = st.columns(2)
                with cr1:
                    rating = st.slider(L["rating"], 1, 5, 4)
                    re_buy_intent = st.selectbox(
                        "回購意願",
                        ["🔥 必回購", "🤔 觀望中", "❌ 絕不回購 (踩雷)"],
                    )
                    texture_feel = st.text_input(L["field2"])
                with cr2:
                    effectiveness = st.text_input(L["field3"])
                    side_effects = st.text_input(L["field4"])

                notes = st.text_area("詳細心得筆記")
                uploaded_file = st.file_uploader(
                    L["photo"], type=["jpg", "jpeg", "png"]
                )

                if st.form_submit_button("儲存心得筆記"):
                    img_path_str = ""
                    if uploaded_file is not None:
                        try:
                            img_dir = Path(__file__).parent / "images"
                            img_dir.mkdir(exist_ok=True)
                            stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                            save_path = img_dir / f"{stamp}_{uploaded_file.name}"
                            save_path.write_bytes(uploaded_file.getbuffer())
                            img_path_str = str(save_path.relative_to(Path(__file__).parent))
                        except Exception as e:
                            st.warning(f"圖片儲存失敗，僅記錄檔名: {e}")
                            img_path_str = uploaded_file.name
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                """INSERT INTO item_reviews (
                                    catalog_id, user_id, review_date, rating, texture_feel,
                                    effectiveness, side_effects, re_buy_intent, notes, image_path
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (int(selected_prod_row["id"]), current_user_id, str(r_date),
                                 rating, texture_feel, effectiveness, side_effects,
                                 re_buy_intent, notes, img_path_str),
                            )
                        st.success(f"成功儲存「{sel_prod}」的使用心得筆記！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"儲存失敗: {e}")

    with tab_rev_list:
        if reviews_df.empty:
            st.info("目前還沒有任何使用心得筆記。")
        else:
            for _, row in reviews_df.iterrows():
                L = review_labels(row["item_type"])
                with st.expander(
                    f"⭐ {row['rating']}分 | {row['product_name']} "
                    f"({row['user_name']} - {row['review_date']})"
                ):
                    st.markdown(f"**回購意願：** {row['re_buy_intent']}")
                    if row["texture_feel"]:
                        st.markdown(f"**{L['label2']}：** {row['texture_feel']}")
                    if row["effectiveness"]:
                        st.markdown(f"**{L['label3']}：** {row['effectiveness']}")
                    if row["side_effects"]:
                        st.markdown(f"**{L['label4']}：** {row['side_effects']}")
                    st.markdown(f"**詳細筆記：**\n{row['notes']}")
                    if row["image_path"]:
                        img_full = Path(__file__).parent / str(row["image_path"])
                        if img_full.exists():
                            st.image(str(img_full), width=300)
                        else:
                            st.info(f"📸 附加照片檔名紀錄：{row['image_path']}")


# =====================================================================
# 功能八：新增購買批次 (快速入庫)
# =====================================================================
elif menu == "📥 新增購買批次 (快速入庫)":
    st.header("📥 記錄新進貨 / 購買批次 (支援海外代購與 PAO 開封設定)")
    cat_df = read_df(
        "SELECT id, name, origin_country, usage_instructions FROM food_catalog"
    )

    if cat_df.empty:
        st.warning("⚠️ 找不到商品主檔！請先至「商品與保養品主檔管理」建立主檔。")
    else:
        with st.form("batch_form", clear_on_submit=True):
            selected_catalog_name = st.selectbox("選擇商品 *", cat_df["name"].tolist())
            sel_cat_row = cat_df[cat_df["name"] == selected_catalog_name].iloc[0]

            if (
                pd.notna(sel_cat_row["usage_instructions"])
                and str(sel_cat_row["usage_instructions"]).strip()
            ):
                st.info(f"📖 **使用方法提示**：{sel_cat_row['usage_instructions']}")

            ci1, ci2 = st.columns(2)
            with ci1:
                is_imported_chk = st.checkbox("✈️ 海外代購 / 國外購入", value=False)
            with ci2:
                foreign_price_input = st.text_input("外幣價格備註 (例如：￥4,500)", value="")

            col1, col2 = st.columns(2)
            with col1:
                channel = st.text_input("購買管道 (例如：日本藥妝店、專櫃)")
                weight = st.number_input("總容量/數量 (g, ml 或 件)", min_value=0.0, value=1.0)
            with col2:
                price = st.number_input("台幣結帳金額 (NT$，不記得可填 0)", min_value=0.0)
                discount_info = st.text_input("優惠備註")

            col3, col4, col5 = st.columns(3)
            purchase_date = col3.date_input("購買日期", datetime.date.today())
            expiry_date = col4.date_input(
                "有效期限 (瓶身印的總效期)",
                datetime.date.today() + datetime.timedelta(days=365),
            )
            status = col5.selectbox("目前狀態", INTAKE_STATUSES)

            st.markdown("---")
            st.markdown("**🧴 開封後效期 (PAO) 設定**")
            cp1, cp2 = st.columns(2)
            opened_date = cp1.date_input("實際開封日期 (若狀態為已開封)", datetime.date.today())
            pao_months = cp2.number_input(
                "PAO 開封後有效月數 (例如罐子寫 12M 填 12)",
                min_value=1, max_value=60, value=12,
            )

            if st.form_submit_button("確認入庫"):
                try:
                    with get_conn() as conn:
                        conn.execute(
                            """INSERT INTO inventory_batches (
                                catalog_id, channel, is_imported, foreign_price, weight,
                                current_weight, original_price, price, discount_info,
                                unit_price, purchase_date, expiry_date, opened_date,
                                pao_months, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (int(sel_cat_row["id"]), channel,
                             1 if is_imported_chk else 0, foreign_price_input,
                             weight, weight, price, price, discount_info,
                             (price / weight) if weight > 0 else 0,
                             str(purchase_date), str(expiry_date),
                             str(opened_date) if status == STATUS_OPENED else None,
                             pao_months, status),
                        )
                    st.success(f"成功將「{selected_catalog_name}」入庫！")
                    st.rerun()
                except Exception as e:
                    st.error(f"入庫失敗: {e}")


# =====================================================================
# 功能九：菜單、烹飪與冰箱清倉推薦
# =====================================================================
elif menu == "📋 菜單、烹飪與冰箱推薦":
    st.header("📋 智慧菜單、精準烹飪扣庫存與即期清倉推薦")

    cat_df = read_df("SELECT id, name FROM food_catalog WHERE item_type = ?", (ITEM_FOOD,))
    batches_df = read_df(
        """SELECT b.*, c.name as catalog_name
           FROM inventory_batches b
           LEFT JOIN food_catalog c ON b.catalog_id = c.id
           WHERE b.status != ?""",
        (STATUS_FINISHED,),
    )

    # 即期/過期清倉提醒
    expiring_items = set()
    if not batches_df.empty:
        for _, row in batches_df.iterrows():
            status_str = check_expiry(row["expiry_date"])
            if "🔴" in status_str or "🟡" in status_str:
                if row["catalog_name"]:
                    expiring_items.add(row["catalog_name"])
    if expiring_items:
        st.warning(
            "⏰ **冰箱清倉提醒**：以下食材即將過期或已過期，建議優先烹調："
            f"**{', '.join(expiring_items)}**"
        )

    tab1, tab2 = st.tabs(["📖 現有菜單與烹飪扣庫存", "✨ 新增菜單"])

    with tab2:
        with st.form("add_recipe", clear_on_submit=True):
            rtitle = st.text_input("菜名")
            ingredient_inputs = []
            if not cat_df.empty:
                for _, row in cat_df.iterrows():
                    ca, cb = st.columns([2, 1])
                    if ca.checkbox(row["name"], key=f"rc_{row['id']}"):
                        amt = cb.number_input("g/ml", value=100.0, key=f"ra_{row['id']}")
                        ingredient_inputs.append(f"{row['name']}:{amt}")
            rinst = st.text_area("烹飪步驟")
            if st.form_submit_button("儲存菜單"):
                if not rtitle.strip():
                    st.error("請輸入菜名！")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                "INSERT INTO recipes (title, ingredients_detail, instructions) VALUES (?, ?, ?)",
                                (rtitle.strip(), ",".join(ingredient_inputs), rinst),
                            )
                        st.success("成功新增菜單！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"新增菜單失敗: {e}")

    with tab1:
        recipes_df = read_df("SELECT * FROM recipes")
        full_cat_df = read_df("SELECT id, name FROM food_catalog")
        if recipes_df.empty:
            st.info("尚無菜單。")
        else:
            for _, row in recipes_df.iterrows():
                details = str(row["ingredients_detail"] or "")
                is_recommended = any(exp in details for exp in expiring_items)
                title = (
                    f"🔥 【推薦清倉】 {row['title']}"
                    if is_recommended else f"🍳 {row['title']}"
                )
                with st.expander(title):
                    if is_recommended:
                        st.info("💡 包含冰箱中即將過期的食材，強烈建議優先製作！")
                    st.markdown(f"**步驟：**\n{row['instructions']}")
                    if st.button("🔥 開始烹飪 (扣庫存)", key=f"cook_{row['id']}"):
                        try:
                            with get_conn() as conn:
                                c = conn.cursor()
                                for item in details.split(","):
                                    if ":" in item:
                                        fname, famt_str = item.split(":")
                                        try:
                                            famt = float(famt_str)
                                        except ValueError:
                                            continue
                                        m = full_cat_df[full_cat_df["name"] == fname]
                                        if not m.empty:
                                            deduct_inventory(c, int(m["id"].values[0]), famt)
                            st.success(f"已完成烹飪「{row['title']}」並精準扣除庫存！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"烹飪扣庫存發生錯誤: {e}")


# =====================================================================
# 功能十：智能自動補貨清單
# =====================================================================
elif menu == "🛒 智能自動補貨清單 (含日用品/保養品)":
    st.header("🛒 智能自動補貨清單 (食品、日用品與保養品全包)")
    st.markdown("系統會自動偵測已用完或庫存歸零的品項，方便您直接列出採購清單！")

    # 一句 SQL 直接算出每個主檔的有效剩餘量
    shop_df = read_df(
        """SELECT c.name as 品名, c.item_type as 屬性,
                  COALESCE(c.origin_country, '') as 產地,
                  COALESCE(c.brand, '無') as 品牌,
                  COALESCE(SUM(
                      CASE WHEN b.status NOT IN (?, ?) THEN b.current_weight ELSE 0 END
                  ), 0) as 有效剩餘量
           FROM food_catalog c
           LEFT JOIN inventory_batches b ON b.catalog_id = c.id
           GROUP BY c.id
           HAVING 有效剩餘量 <= 0""",
        (STATUS_FINISHED, STATUS_DISCARDED),
    )

    if shop_df.empty:
        st.success("🎉 目前所有品項庫存充足！")
    else:
        shop_df["屬性"] = shop_df["屬性"].apply(item_type_label)
        st.warning(f"📋 系統偵測到有 **{len(shop_df)}** 項商品需要補貨：")
        st.dataframe(
            shop_df.drop(columns=["有效剩餘量"]), width="stretch"
        )
        st.markdown("---")
        if st.button("➕ 一鍵把上述補貨品項加入「想買清單」"):
            try:
                today = str(datetime.date.today())
                with get_conn() as conn:
                    c = conn.cursor()
                    added = 0
                    for _, r in shop_df.iterrows():
                        # 避免重複加入尚未購買的相同品項
                        exists = c.execute(
                            "SELECT 1 FROM wishlist WHERE item_name = ? AND is_bought = 0",
                            (r["品名"],),
                        ).fetchone()
                        if exists:
                            continue
                        c.execute(
                            """INSERT INTO wishlist
                            (item_name, category, priority, est_price, channel, note,
                             is_bought, created_date)
                            VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                            (r["品名"], r["屬性"], "🟡 普通", 0, "",
                             "由自動補貨清單加入", today),
                        )
                        added += 1
                st.success(f"已加入 {added} 項到想買清單！")
                st.rerun()
            except Exception as e:
                st.error(f"加入失敗: {e}")


# =====================================================================
# 功能十一：想買/待買清單
# =====================================================================
elif menu == "📝 想買/待買清單":
    st.header("📝 想買 / 待買清單")
    st.markdown("手動記錄想買的東西，逛街或網購時打開這頁就知道要買什麼！")

    tab_add, tab_todo, tab_done = st.tabs(
        ["➕ 新增想買品項", "🛍️ 待買清單", "✅ 已購買紀錄"]
    )

    with tab_add:
        with st.form("wishlist_add_form", clear_on_submit=True):
            wc1, wc2 = st.columns(2)
            with wc1:
                w_name = st.text_input("想買的品項 *")
                w_category = st.selectbox("分類", current_cats)
                w_priority = st.selectbox("優先度", WISH_PRIORITIES, index=1)
            with wc2:
                w_price = st.number_input("預估價格 (元，可留 0)", min_value=0.0, value=0.0)
                w_channel = st.text_input("預計購買管道 (例如：好市多、蝦皮)")
            w_note = st.text_area("備註 (規格、數量、想買原因等)")
            if st.form_submit_button("💾 加入想買清單"):
                if not w_name.strip():
                    st.error("請輸入品項名稱！")
                else:
                    try:
                        with get_conn() as conn:
                            conn.execute(
                                """INSERT INTO wishlist
                                (item_name, category, priority, est_price, channel, note,
                                 is_bought, created_date)
                                VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                                (w_name.strip(), w_category, w_priority, w_price,
                                 w_channel, w_note, str(datetime.date.today())),
                            )
                        st.success(f"已加入想買清單：{w_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"加入失敗: {e}")

    with tab_todo:
        todo_df = read_df(
            "SELECT * FROM wishlist WHERE is_bought = 0 ORDER BY priority ASC, id DESC"
        )
        if todo_df.empty:
            st.info("目前沒有待買品項，清單很乾淨！")
        else:
            total_est = todo_df["est_price"].sum()
            st.metric("待買品項數 / 預估總金額", f"{len(todo_df)} 項 / NT$ {total_est:.0f}")
            st.markdown("---")
            for _, row in todo_df.iterrows():
                with st.container():
                    cc1, cc2, cc3 = st.columns([5, 1, 1])
                    with cc1:
                        price_txt = f"約 NT$ {row['est_price']:.0f}" if row["est_price"] else "價格未定"
                        detail = f"**{row['priority']}｜{row['item_name']}**　({row['category']}｜{price_txt})"
                        st.markdown(detail)
                        sub = []
                        if row["channel"]:
                            sub.append(f"管道：{row['channel']}")
                        if row["note"]:
                            sub.append(f"備註：{row['note']}")
                        if sub:
                            st.caption("　".join(sub))
                    with cc2:
                        if st.button("✅ 已買", key=f"buy_{row['id']}"):
                            try:
                                with get_conn() as conn:
                                    conn.execute(
                                        "UPDATE wishlist SET is_bought = 1 WHERE id = ?",
                                        (int(row["id"]),),
                                    )
                                st.rerun()
                            except Exception as e:
                                st.error(f"更新失敗: {e}")
                    with cc3:
                        if st.button("🗑️ 刪除", key=f"del_{row['id']}"):
                            try:
                                with get_conn() as conn:
                                    conn.execute(
                                        "DELETE FROM wishlist WHERE id = ?",
                                        (int(row["id"]),),
                                    )
                                st.rerun()
                            except Exception as e:
                                st.error(f"刪除失敗: {e}")
                    st.markdown("---")

    with tab_done:
        done_df = read_df(
            "SELECT * FROM wishlist WHERE is_bought = 1 ORDER BY id DESC"
        )
        if done_df.empty:
            st.info("還沒有已購買的紀錄。")
        else:
            st.dataframe(
                done_df[["item_name", "category", "priority", "est_price",
                         "channel", "note", "created_date"]].rename(columns={
                    "item_name": "品項", "category": "分類", "priority": "優先度",
                    "est_price": "預估價格", "channel": "購買管道",
                    "note": "備註", "created_date": "加入日期",
                }),
                width="stretch",
            )
            if st.button("↩️ 清空已購買紀錄"):
                try:
                    with get_conn() as conn:
                        conn.execute("DELETE FROM wishlist WHERE is_bought = 1")
                    st.success("已清空已購買紀錄！")
                    st.rerun()
                except Exception as e:
                    st.error(f"清空失敗: {e}")


# =====================================================================
# 功能十二：支出分析與預算
# =====================================================================
elif menu == "🛒 支出分析、預算與比價":
    st.header("🛒 智慧購物與預算控管")
    df = read_df("SELECT * FROM inventory_batches")

    if df.empty:
        st.info("無支出資料。")
    else:
        default_budget = float(get_setting("monthly_budget", "5000"))
        b_val = st.number_input("每月預算上限 (元)", value=default_budget)
        if st.button("儲存預算"):
            set_setting("monthly_budget", b_val)
            st.success("預算儲存成功！")

        total_spent = df["price"].sum() if "price" in df else 0.0
        st.metric("累計總花費", f"NT$ {total_spent:.1f}")


# =====================================================================
# 功能十三：系統設定與資料清空
# =====================================================================
elif menu == "⚙️ 系統設定與資料清空":
    st.header("⚙️ 系統設定與資料清空")
    st.warning(
        "⚠️ 此頁面的清空操作會**永久刪除資料且無法復原**，請務必先確認。"
        "建議清空前先手動備份 `pantry.db` 檔案。"
    )

    # 各資料表的中文說明與對應清空 SQL
    CLEARABLE = {
        "每日飲食打卡紀錄 (daily_logs)": ["daily_logs"],
        "體重歷史紀錄 (weight_logs)": ["weight_logs"],
        "庫存批次 (inventory_batches)": ["inventory_batches"],
        "商品/保養品主檔 (food_catalog)": ["food_catalog"],
        "使用心得筆記 (item_reviews)": ["item_reviews"],
        "菜單 (recipes)": ["recipes"],
        "想買/待買清單 (wishlist)": ["wishlist"],
        "成員資料 (users，含其飲食/體重/心得)": [
            "users", "daily_logs", "weight_logs", "item_reviews",
        ],
    }

    # 目前各表資料筆數總覽
    st.subheader("📊 目前各資料表筆數")
    count_rows = []
    for tbl in ["users", "food_catalog", "inventory_batches", "daily_logs",
                "weight_logs", "item_reviews", "recipes", "wishlist"]:
        cnt_df = read_df(f"SELECT COUNT(*) as n FROM {tbl}")
        n = int(cnt_df["n"].iloc[0]) if not cnt_df.empty else 0
        count_rows.append({"資料表": tbl, "筆數": n})
    st.dataframe(pd.DataFrame(count_rows), width="stretch")

    st.markdown("---")

    # --- 分項清空 ---
    st.subheader("🧹 分項清空 (可選擇要清哪些資料)")
    selected_targets = st.multiselect(
        "選擇要清空的資料類別 (可複選)",
        list(CLEARABLE.keys()),
    )
    confirm_text = st.text_input(
        "請輸入 CLEAR 以確認清空所選項目", key="clear_partial_confirm"
    )
    if st.button("🧹 清空所選資料", type="primary"):
        if not selected_targets:
            st.error("請至少選擇一個要清空的類別！")
        elif confirm_text.strip() != "CLEAR":
            st.error("確認文字不符，請輸入大寫 CLEAR 才會執行。")
        else:
            try:
                # 收集所有需要清空的實體資料表 (去重)
                tables_to_clear = []
                for tgt in selected_targets:
                    for t in CLEARABLE[tgt]:
                        if t not in tables_to_clear:
                            tables_to_clear.append(t)
                with get_conn() as conn:
                    c = conn.cursor()
                    for t in tables_to_clear:
                        c.execute(f"DELETE FROM {t}")
                        # 重置自動遞增 ID (若有 sqlite_sequence)
                        try:
                            c.execute(
                                "DELETE FROM sqlite_sequence WHERE name = ?", (t,)
                            )
                        except sqlite3.OperationalError:
                            pass
                st.success(f"已清空：{', '.join(tables_to_clear)}")
                st.rerun()
            except Exception as e:
                st.error(f"清空失敗: {e}")

    st.markdown("---")

    # --- 全部清空 ---
    with st.expander("🔴 危險區域：一鍵清空所有資料 (完全歸零)"):
        st.write(
            "此操作會清空**所有**成員、商品主檔、庫存、飲食/體重紀錄、"
            "心得、菜單與想買清單，僅保留系統預設分類。"
        )
        confirm_all = st.text_input(
            "請輸入 DELETE ALL 以確認完全清空", key="clear_all_confirm"
        )
        if st.button("🔴 我了解風險，清空全部資料", type="primary"):
            if confirm_all.strip() != "DELETE ALL":
                st.error("確認文字不符，請輸入 DELETE ALL 才會執行。")
            else:
                try:
                    all_tables = [
                        "daily_logs", "weight_logs", "item_reviews",
                        "inventory_batches", "recipes", "wishlist",
                        "food_catalog", "users", "settings",
                    ]
                    with get_conn() as conn:
                        c = conn.cursor()
                        for t in all_tables:
                            c.execute(f"DELETE FROM {t}")
                            try:
                                c.execute(
                                    "DELETE FROM sqlite_sequence WHERE name = ?", (t,)
                                )
                            except sqlite3.OperationalError:
                                pass
                    st.success("✅ 已清空所有資料！系統已回到初始狀態。")
                    st.rerun()
                except Exception as e:
                    st.error(f"清空失敗: {e}")
