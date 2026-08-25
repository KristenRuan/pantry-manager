import datetime
import sqlite3
import pandas as pd
import streamlit as st

# 頁面基本設定
st.set_page_config(
    page_title="個人與多成員居家、食品、代購與美妝保養實驗庫", page_icon="💄", layout="wide"
)


# --- 資料庫初始化 ---
def init_db():
  conn = sqlite3.connect("pantry.db")
  c = conn.cursor()

  # 1. 分類表
  c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
  default_cats = [
      "調味料",
      "冷凍肉品",
      "零食",
      "生鮮",
      "主食",
      "飲料",
      "日常消耗品",
      "衛浴清潔",
      "個人護理",
      "臉部保養",
      "彩妝香氛",
      "身體護理",
      "其他",
  ]
  for cat in default_cats:
    try:
      c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
    except sqlite3.OperationalError:
      pass

  # 2. 商品/食品/保養品主檔 (新增 barcode 條碼欄位)
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

  # 相容性升級欄位檢查
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

  conn.commit()
  conn.close()


init_db()


def get_setting(key, default_val=""):
  try:
    conn = sqlite3.connect("pantry.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default_val
  except Exception:
    return default_val


def set_setting(key, value):
  try:
    conn = sqlite3.connect("pantry.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()
  except Exception as e:
    st.error(f"儲存設定發生錯誤: {e}")


def get_categories():
  try:
    conn = sqlite3.connect("pantry.db")
    c = conn.cursor()
    c.execute("SELECT name FROM categories")
    cats = [row[0] for row in c.fetchall()]
    conn.close()
    return (
        cats
        if cats
        else [
            "調味料",
            "冷凍肉品",
            "零食",
            "生鮮",
            "主食",
            "飲料",
            "日常消耗品",
            "衛浴清潔",
            "個人護理",
            "臉部保養",
            "彩妝香氛",
            "身體護理",
            "其他",
        ]
    )
  except Exception:
    return [
        "調味料",
        "冷凍肉品",
        "零食",
        "生鮮",
        "主食",
        "飲料",
        "日常消耗品",
        "衛浴清潔",
        "個人護理",
        "臉部保養",
        "彩妝香氛",
        "身體護理",
        "其他",
    ]


def check_expiry(date_str, opened_date_str="", pao_months=12, status="未開封"):
  if status == "已開封" and opened_date_str and str(opened_date_str).strip() not in ["", "None", "NaT"]:
    try:
      opened = datetime.datetime.strptime(str(opened_date_str).split()[0], "%Y-%m-%d").date()
      pao_days = int(pao_months * 30.44)
      pao_exp = opened + datetime.timedelta(days=pao_days)
      today = datetime.date.today()
      delta_pao = (pao_exp - today).days
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
    today = datetime.date.today()
    delta = (exp - today).days
    if delta < 0:
      return "🔴 已過期"
    elif delta <= 7:
      return f"🟡 即期 ({delta}天)"
    else:
      return f"🟢 正常 ({delta}天)"
  except Exception:
    return "未知"


# --- 側邊欄全域設定 ---
st.sidebar.title("💄 居家、飲食與美妝保養庫")

try:
  conn = sqlite3.connect("pantry.db")
  users_df = pd.read_sql_query("SELECT * FROM users", conn)
  conn.close()
except Exception:
  users_df = pd.DataFrame()

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
  current_user_id = current_user_row["id"]

st.sidebar.markdown("---")
menu = st.sidebar.selectbox(
    "選擇功能",
    [
        "🔥 每日飲食打卡與減脂儀表板",
        "👥 成員管理與目標設定",
        "📦 庫存與批次總覽 (含海外代購與PAO)",
        "🧴 晨間 (AM) 與夜間 (PM) 保養 Routine 推薦",
        "🏷️ 商品與保養品主檔管理",
        "📷 條碼掃描快速入庫 / 查詢",
        "🧪 保養品/商品使用心得與實驗筆記 (含照片)",
        "📥 新增購買批次 (快速入庫)",
        "📋 菜單、烹飪與冰箱推薦",
        "🛒 智能自動補貨清單 (含日用品/保養品)",
        "🛒 支出分析、預算與比價",
    ],
)

st.sidebar.markdown("---")
st.sidebar.subheader("🏷️ 分類管理 (新增與刪除)")
current_cats = get_categories()

with st.sidebar.form("cat_manage_form", clear_on_submit=True):
  new_cat_input = st.text_input("新增自訂分類")
  sub_add_cat = st.form_submit_button("新增分類")
  if sub_add_cat:
    if new_cat_input.strip():
      try:
        conn = sqlite3.connect("pantry.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO categories (name) VALUES (?)", (new_cat_input.strip(),)
        )
        conn.commit()
        conn.close()
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
      conn = sqlite3.connect("pantry.db")
      c = conn.cursor()
      c.execute("DELETE FROM categories WHERE name = ?", (del_cat_target,))
      conn.commit()
      conn.close()
      st.sidebar.error(f"已刪除分類：「{del_cat_target}」")
      st.rerun()
    except Exception as e:
      st.sidebar.error(f"刪除失敗: {e}")


# --- 功能一：成員管理與目標設定 ---
if menu == "👥 成員管理與目標設定":
  st.header("👥 家庭成員、姓名修改與減脂目標設定")
  tab_m1, tab_m2, tab_m3 = st.tabs(
      [
          "➕ 新增成員",
          "✏️ 編輯現有成員名字與身體數據",
          "📈 記錄今日體重與個人趨勢圖",
      ]
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
          options=[1.2, 1.375, 1.55, 1.725, 1.9],
          format_func=lambda x: {
              1.2: "久坐不動（幾乎不運動）",
              1.375: "輕度活動（每周運動 1-3 天）",
              1.55: "中度活動（每周運動 3-5 天）",
              1.725: "高度活動（每周運動 6-7 天）",
              1.9: "極高度活動（勞力密集工作或每天雙練）",
          }[x],
      )
      u_deficit = st.number_input(
          "減脂熱量赤字 (大卡，建議 300 ~ 500)",
          min_value=0.0,
          max_value=1000.0,
          value=400.0,
          step=50.0,
      )

      sub_user = st.form_submit_button("新增成員")
      if sub_user:
        if not u_name.strip():
          st.error("請輸入成員姓名！")
        else:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                        INSERT INTO users (name, gender, age, height, weight, activity_level, goal_deficit)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    u_name.strip(),
                    u_gender,
                    u_age,
                    u_height,
                    u_weight,
                    u_activity,
                    u_deficit,
                ),
            )
            c.execute("SELECT last_insert_rowid()")
            new_uid = c.fetchone()[0]
            c.execute(
                "INSERT INTO weight_logs (user_id, log_date, weight) VALUES (?, ?, ?)",
                (new_uid, str(datetime.date.today()), u_weight),
            )
            conn.commit()
            conn.close()
            st.success(f"成功新增成員：「{u_name}」！")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("此成員名稱已經存在！")
          except Exception as e:
            st.error(f"發生錯誤: {e}")

  with tab_m2:
    if users_df.empty:
      st.info("目前沒有成員資料。")
    else:
      edit_u_name = st.selectbox(
          "選擇要編輯的成員", users_df["name"].tolist(), key="edit_u_select"
      )
      row_u = users_df[users_df["name"] == edit_u_name].iloc[0]

      with st.form("edit_user_form"):
        eu_name = st.text_input("修改成員姓名", value=row_u["name"])
        eu_gender = st.selectbox(
            "生理性別", ["男", "女"], index=0 if row_u["gender"] == "男" else 1
        )
        eu_age = st.number_input(
            "年齡", min_value=1, max_value=120, value=int(row_u["age"] or 25)
        )
        eu_height = st.number_input(
            "身高 (cm)",
            min_value=50.0,
            max_value=250.0,
            value=float(row_u["height"] or 170.0),
        )
        eu_weight = st.number_input(
            "體重 (kg)",
            min_value=20.0,
            max_value=300.0,
            value=float(row_u["weight"] or 65.0),
        )

        act_options = [1.2, 1.375, 1.55, 1.725, 1.9]
        default_act_idx = (
            act_options.index(row_u["activity_level"])
            if row_u["activity_level"] in act_options
            else 0
        )
        eu_activity = st.selectbox(
            "日常活動量係數", options=act_options, index=default_act_idx
        )
        eu_deficit = st.number_input(
            "減脂熱量赤字 (大卡)",
            min_value=0.0,
            max_value=1000.0,
            value=float(row_u["goal_deficit"] or 400.0),
        )

        sub_edit = st.form_submit_button("儲存修改")
        if sub_edit:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                    UPDATE users SET name = ?, gender = ?, age = ?, height = ?, weight = ?, activity_level = ?, goal_deficit = ?
                    WHERE id = ?
                """,
                (
                    eu_name.strip(),
                    eu_gender,
                    eu_age,
                    eu_height,
                    eu_weight,
                    eu_activity,
                    eu_deficit,
                    row_u["id"],
                ),
            )
            conn.commit()
            conn.close()
            st.success("成員資料與姓名更新成功！")
            st.rerun()
          except Exception as e:
            st.error(f"更新失敗: {e}")

  with tab_m3:
    if users_df.empty:
      st.info("請先新增成員。")
    else:
      st.subheader(f"📈 【{selected_user_name}】的體重變化紀錄與趨勢")
      with st.form("weight_log_form", clear_on_submit=True):
        w_date = st.date_input("記錄日期", datetime.date.today())
        new_w = st.number_input(
            "今日量測體重 (kg)",
            min_value=20.0,
            max_value=300.0,
            value=float(current_user_row["weight"] or 65.0),
        )
        sub_w_log = st.form_submit_button("儲存體重並自動更新 TDEE")
        if sub_w_log:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                "INSERT INTO weight_logs (user_id, log_date, weight) VALUES (?, ?, ?)",
                (current_user_id, str(w_date), new_w),
            )
            c.execute(
                "UPDATE users SET weight = ? WHERE id = ?",
                (new_w, current_user_id),
            )
            conn.commit()
            conn.close()
            st.success(f"成功記錄體重 {new_w} kg！")
            st.rerun()
          except Exception as e:
            st.error(f"記錄失敗: {e}")

      st.markdown("---")
      try:
        conn = sqlite3.connect("pantry.db")
        w_logs_df = pd.read_sql_query(
            "SELECT log_date, weight FROM weight_logs WHERE user_id = ? ORDER BY log_date ASC",
            conn,
            params=(current_user_id,),
        )
        conn.close()
      except Exception:
        w_logs_df = pd.DataFrame()

      if not w_logs_df.empty:
        w_logs_df["log_date"] = pd.to_datetime(w_logs_df["log_date"])
        st.line_chart(w_logs_df.set_index("log_date"), y="weight")


# --- 功能二：每日飲食打卡與減脂儀表板 ---
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

    c1, c2, c3 = st.columns(3)
    c1.metric("基礎代謝 (BMR)", f"{bmr:.0f} 大卡")
    c2.metric("每日總消耗 (TDEE)", f"{tdee:.0f} 大卡")
    c3.metric("🎯 減脂建議熱量上限", f"{target_calories:.0f} 大卡")

    st.markdown("---")
    selected_log_date = st.date_input("選擇打卡日期", datetime.date.today())
    date_str = str(selected_log_date)

    try:
      conn = sqlite3.connect("pantry.db")
      logs_df = pd.read_sql_query(
          "SELECT * FROM daily_logs WHERE user_id = ? AND log_date = ?",
          conn,
          params=(current_user_id, date_str),
      )
      recipes_df = pd.read_sql_query(
          "SELECT id, title, ingredients_detail FROM recipes", conn
      )
      cat_df = pd.read_sql_query(
          "SELECT id, name, foreign_name, calories, protein, fat, carbs FROM"
          " food_catalog WHERE item_type = '食品'",
          conn,
      )
      conn.close()
    except Exception:
      logs_df, recipes_df, cat_df = (
          pd.DataFrame(),
          pd.DataFrame(),
          pd.DataFrame(),
      )

    total_cal_consumed = (
        logs_df["calories"].sum() if not logs_df.empty and "calories" in logs_df else 0.0
    )
    st.subheader(f"📊 {date_str} 營養攝取進度")
    st.metric(
        "今日已攝取熱量",
        f"{total_cal_consumed:.1f} / {target_calories:.0f} 大卡",
    )

    st.markdown("---")
    tab_log1, tab_log2, tab_log3 = st.tabs(
        ["🍳 從智慧菜單匯入", "🥫 從現成食品主檔選取", "✍️ 自訂/外食輸入"]
    )

    with tab_log1:
      if not recipes_df.empty:
        with st.form("log_recipe_form", clear_on_submit=True):
          meal_type = st.selectbox(
              "餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_r"
          )
          selected_recipe_title = st.selectbox(
              "選擇菜單", recipes_df["title"].tolist()
          )
          if st.form_submit_button("匯入此菜單營養"):
            r_row = recipes_df[
                recipes_df["title"] == selected_recipe_title
            ].iloc[0]
            details = r_row["ingredients_detail"]
            r_cal, r_pro, r_fat, r_carbs = 0.0, 0.0, 0.0, 0.0
            if details:
              try:
                conn = sqlite3.connect("pantry.db")
                full_c_df = pd.read_sql_query("SELECT * FROM food_catalog", conn)
                conn.close()
                for item in details.split(","):
                  if ":" in item:
                    fname, famt_str = item.split(":")
                    famt = float(famt_str)
                    m = full_c_df[full_c_df["name"] == fname]
                    if not m.empty:
                      r_cal += (
                          float(m["calories"].values[0] or 0) / 100.0
                      ) * famt
                      r_pro += (
                          float(m["protein"].values[0] or 0) / 100.0
                      ) * famt
                      r_fat += (float(m["fat"].values[0] or 0) / 100.0) * famt
                      r_carbs += (
                          float(m["carbs"].values[0] or 0) / 100.0
                      ) * famt
              except Exception:
                pass
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                    INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    current_user_id,
                    date_str,
                    meal_type,
                    f"[菜單] {selected_recipe_title}",
                    0.0,
                    r_cal,
                    r_pro,
                    r_fat,
                    r_carbs,
                ),
            )
            conn.commit()
            conn.close()
            st.success("打卡成功！")
            st.rerun()

    with tab_log2:
      if not cat_df.empty:
        search_kw = st.text_input("🔍 輸入關鍵字搜尋食品", "", key="food_search_kw")
        filtered_cat_df = (
            cat_df[
                cat_df["name"].str.contains(search_kw, case=False, na=False)
                | cat_df["foreign_name"].str.contains(
                    search_kw, case=False, na=False
                )
            ]
            if search_kw
            else cat_df
        )
        if not filtered_cat_df.empty:
          with st.form("log_catalog_form", clear_on_submit=True):
            meal_type_c = st.selectbox(
                "餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_c"
            )
            selected_food_name = st.selectbox(
                "選擇食品", filtered_cat_df["name"].tolist()
            )
            consume_weight = st.number_input("食用克數/毫升", value=100.0)
            if st.form_submit_button("確認打卡並扣庫存"):
              f_row = cat_df[cat_df["name"] == selected_food_name].iloc[0]
              ratio = consume_weight / 100.0
              conn = sqlite3.connect("pantry.db")
              c = conn.cursor()
              c.execute(
                  """
                    INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                  (
                      current_user_id,
                      date_str,
                      meal_type_c,
                      f"[現成] {selected_food_name}",
                      consume_weight,
                      float(f_row["calories"] or 0) * ratio,
                      float(f_row["protein"] or 0) * ratio,
                      float(f_row["fat"] or 0) * ratio,
                      float(f_row["carbs"] or 0) * ratio,
                  ),
              )
              conn.commit()
              conn.close()
              st.success("打卡成功！")
              st.rerun()

    with tab_log3:
      with st.form("log_manual_form", clear_on_submit=True):
        meal_type_m = st.selectbox(
            "餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_m"
        )
        manual_name = st.text_input("外食名稱")
        m_cal = st.number_input("總熱量 (大卡)", value=150.0)
        m_pro = st.number_input("蛋白質 (g)", value=15.0)
        m_fat = st.number_input("脂肪 (g)", value=5.0)
        m_carbs = st.number_input("碳水 (g)", value=10.0)
        if st.form_submit_button("確認新增外食打卡"):
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute(
              """
                INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
              (
                  current_user_id,
                  date_str,
                  meal_type_m,
                  manual_name,
                  100.0,
                  m_cal,
                  m_pro,
                  m_fat,
                  m_carbs,
              ),
          )
          conn.commit()
          conn.close()
          st.success("新增成功！")
          st.rerun()


# --- 功能三：庫存與批次總覽 (含海外代購與PAO) ---
elif menu == "📦 庫存與批次總覽 (含海外代購與PAO)":
  st.header("📦 居家庫存與效期總覽 (含保養品 PAO 與海外代購)")
  try:
    conn = sqlite3.connect("pantry.db")
    query = """
        SELECT 
            b.id as batch_id,
            COALESCE(c.name, '未知商品') as name,
            COALESCE(c.barcode, '') as 條碼號碼,
            COALESCE(c.foreign_name, '') as foreign_name,
            COALESCE(c.usage_instructions, '') as 使用方法,
            COALESCE(c.routine_time, '早晚皆可') as 保養時段,
            COALESCE(c.routine_order, 1) as 順序,
            COALESCE(c.origin_country, '台灣') as origin_country,
            COALESCE(c.item_type, '食品') as 屬性,
            CASE WHEN b.is_imported = 1 THEN '✈️ 海外代購' else '🏠 本地一般' END as 採購來源,
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
    df = pd.read_sql_query(query, conn)
    conn.close()
  except Exception:
    df = pd.DataFrame()

  if df.empty:
    st.info("目前庫存無資料。")
  else:
    df["效期狀態"] = df.apply(
        lambda row: check_expiry(row["有效期限"], row["開封日期"], row["PAO月數"], row["狀態"]),
        axis=1,
    )
    st.dataframe(df, use_container_width=True)


# --- 功能四：晨間 (AM) 與夜間 (PM) 保養 Routine 推薦 ---
elif menu == "🧴 晨間 (AM) 與夜間 (PM) 保養 Routine 推薦":
  st.header("🧴 您的個人晨間 (AM) 與夜間 (PM) 保養步驟清單")
  try:
    conn = sqlite3.connect("pantry.db")
    query = """
        SELECT 
            c.name, c.foreign_name, c.brand, c.routine_time, c.routine_order, c.usage_instructions,
            b.status, b.current_weight
        FROM inventory_batches b
        JOIN food_catalog c ON b.catalog_id = c.id
        WHERE c.item_type LIKE '%保養%' AND b.status != '已用完'
        ORDER BY c.routine_order ASC
    """
    routine_df = pd.read_sql_query(query, conn)
    conn.close()
  except Exception:
    routine_df = pd.DataFrame()

  if routine_df.empty:
    st.info("目前庫存中沒有找到庫存充足的保養品！請先至「新增購買批次」入庫您的保養品。")
  else:
    tab_am, tab_pm = st.tabs(["☀️ 晨間保養清單 (AM)", "🌙 夜間保養清單 (PM)"])

    with tab_am:
      am_items = routine_df[routine_df["routine_time"].isin(["早安 AM", "早晚皆可"])]
      if am_items.empty:
        st.info("目前沒有設定晨間保養品。")
      else:
        for idx, row in am_items.iterrows():
          with st.container():
            st.markdown(f"### 步驟 {row['routine_order']}：{row['name']} ({row['brand']})")
            if row["foreign_name"]:
              st.caption(f"外文名：{row['foreign_name']}")
            st.info(f"💡 **使用方法**：{row['usage_instructions'] or '無特別說明'}")
            st.markdown("---")

    with tab_pm:
      pm_items = routine_df[routine_df["routine_time"].isin(["晚安 PM", "早晚皆可"])]
      if pm_items.empty:
        st.info("目前沒有設定夜間保養品。")
      else:
        for idx, row in pm_items.iterrows():
          with st.container():
            st.markdown(f"### 步驟 {row['routine_order']}：{row['name']} ({row['brand']})")
            if row["foreign_name"]:
              st.caption(f"外文名：{row['foreign_name']}")
            st.info(f"💡 **使用方法**：{row['usage_instructions'] or '無特別說明'}")
            st.markdown("---")


# --- 功能五：商品與保養品主檔管理 ---
elif menu == "🏷️ 商品與保養品主檔管理":
  st.header("🏷️ 商品主檔管理 (支援食品、日常用品與美妝保養品)")
  tab_add, tab_edit_del = st.tabs(["➕ 新增主檔", "✏️ 修改與刪除"])

  with tab_add:
    with st.form("catalog_form", clear_on_submit=True):
      c1, c2 = st.columns(2)
      with c1:
        name = st.text_input("中文品名 * (例如：SK-II 青春露)")
        barcode = st.text_input("商品條碼編號 (Barcode，例如：49790060... 或用手機掃描)")
        foreign_name = st.text_input("外文原名 / 日文原名")
        origin_country = st.selectbox(
            "原產國", ["台灣", "日本", "韓國", "美國", "泰國", "歐洲", "中國大陸", "其他"]
        )
        brand = st.text_input("品牌")
      with c2:
        category = st.selectbox("分類", current_cats)
        item_type = st.selectbox(
            "商品屬性類型",
            [
                "食品",
                "日常消耗品",
                "美妝保養品 (支援效期與PAO開封期)",
            ],
        )
        ingredients = st.text_area("成分 / 材質說明")

      st.markdown("---")
      st.markdown("**🧴 保養品專屬進階設定 (非保養品可忽略)**")
      c_rt1, c_rt2, c_rt3, c_rt4 = st.columns(4)
      routine_time = c_rt1.selectbox("保養時段", ["早安 AM", "晚安 PM", "早晚皆可"])
      routine_order = c_rt2.number_input("保養步驟順序", min_value=1, max_value=20, value=1)
      skin_type = c_rt3.selectbox("適用膚質", ["所有膚質", "油肌", "乾肌", "混合肌", "敏感肌"])
      season = c_rt4.selectbox("適用季節", ["全年適用", "春季", "夏季", "秋季", "冬季"])

      usage_instructions = st.text_area(
          "💡 使用方法 / 步驟說明 (例如：早晚清潔後，取適量於化妝棉輕拍全臉)"
      )

      calories, protein, fat, carbs, sugar, sodium = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
      if item_type == "食品":
        st.markdown("**營養標示 (每 100g / 100ml)**")
        c3, c4, c5, c6, c7, c8 = st.columns(6)
        calories = c3.number_input("熱量", value=0.0)
        protein = c4.number_input("蛋白質", value=0.0)
        fat = c5.number_input("脂肪", value=0.0)
        carbs = c6.number_input("碳水", value=0.0)
        sugar = c7.number_input("糖", value=0.0)
        sodium = c8.number_input("鈉", value=0.0)

      if st.form_submit_button("儲存商品主檔"):
        if not name:
          st.error("請填寫商品名稱！")
        else:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                        INSERT INTO food_catalog (
                            name, barcode, foreign_name, origin_country, brand, category, ingredients, 
                            usage_instructions, item_type, routine_time, routine_order, skin_type, season,
                            calories, protein, fat, carbs, sugar, sodium
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    name,
                    barcode.strip(),
                    foreign_name,
                    origin_country,
                    brand,
                    category,
                    ingredients,
                    usage_instructions,
                    item_type,
                    routine_time,
                    routine_order,
                    skin_type,
                    season,
                    calories,
                    protein,
                    fat,
                    carbs,
                    sugar,
                    sodium,
                ),
            )
            conn.commit()
            conn.close()
            st.success(f"成功建立主檔：「{name}」！")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("商品名稱已存在！")
          except Exception as e:
            st.error(f"發生錯誤: {e}")

  with tab_edit_del:
    try:
      conn = sqlite3.connect("pantry.db")
      cat_df = pd.read_sql_query("SELECT * FROM food_catalog", conn)
      conn.close()
    except Exception:
      cat_df = pd.DataFrame()

    if cat_df.empty:
      st.info("尚無主檔。")
    else:
      sel_id = st.selectbox(
          "選擇商品",
          cat_df["id"].tolist(),
          format_func=lambda x: cat_df[cat_df["id"] == x]["name"].values[0],
      )
      r_sel = cat_df[cat_df["id"] == sel_id].iloc[0]
      with st.form("edit_cat"):
        en = st.text_input("中文品名", value=r_sel["name"])
        ebc = st.text_input("條碼編號 (Barcode)", value=str(r_sel["barcode"]) if pd.notna(r_sel["barcode"]) else "")
        efn = st.text_input(
            "外文原名",
            value=str(r_sel["foreign_name"])
            if pd.notna(r_sel["foreign_name"])
            else "",
        )
        eb = st.text_input(
            "品牌", value=str(r_sel["brand"]) if pd.notna(r_sel["brand"]) else ""
        )
        ei = st.text_area(
            "成分",
            value=str(r_sel["ingredients"])
            if pd.notna(r_sel["ingredients"])
            else "",
        )
        eui = st.text_area(
            "使用方法 / 步驟說明",
            value=str(r_sel["usage_instructions"])
            if pd.notna(r_sel["usage_instructions"])
            else "",
        )
        if st.form_submit_button("更新主檔"):
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute(
              "UPDATE food_catalog SET name=?, barcode=?, foreign_name=?, brand=?, ingredients=?, usage_instructions=? WHERE id=?",
              (en, ebc, efn, eb, ei, eui, sel_id),
          )
          conn.commit()
          conn.close()
          st.success("更新成功！")
          st.rerun()


# --- 功能六：條碼掃描快速入庫 / 查詢 ---
elif menu == "📷 條碼掃描快速入庫 / 查詢":
  st.header("📷 商品條碼快速掃描與入庫查詢")
  st.info("💡 您可以使用手機鏡頭拍照上傳商品條碼照片，或是直接輸入條碼編號快速進行商品識別與入庫！")

  scan_tab1, scan_tab2 = st.tabs(["📸 拍照/上傳條碼快速搜尋", "⌨️ 輸入條碼代碼查詢"])

  with scan_tab1:
    barcode_img = st.file_uploader("拍下商品條碼或上傳條碼圖片", type=["jpg", "jpeg", "png"])
    if barcode_img is not None:
      st.image(barcode_img, caption="已上傳的條碼照片", width=300)
      st.success("✅ 圖片上傳成功！(模擬條碼解析中...)")
      # 這裡可以整合條碼解析，若資料庫有對應條碼則秀出
      try:
        conn = sqlite3.connect("pantry.db")
        cat_df = pd.read_sql_query("SELECT * FROM food_catalog", conn)
        conn.close()
      except Exception:
        cat_df = pd.DataFrame()

      if not cat_df.empty:
        matched_items = cat_df[cat_df["barcode"].notna() & (cat_df["barcode"] != "")]
        if not matched_items.empty:
          st.subheader("🎯 找到以下對應商品：")
          for idx, row in matched_items.iterrows():
            st.markdown(f"**品名：** {row['name']} | **品牌：** {row['brand']} | **類型：** {row['item_type']}")
        else:
          st.warning("⚠️ 目前主檔中尚無登記條碼的商品。您可以手動輸入條碼或至【商品主檔管理】補填條碼！")

  with scan_tab2:
    with st.form("manual_barcode_form"):
      input_code = st.text_input("請輸入或使用掃描器輸入條碼數字")
      sub_barcode = st.form_submit_button("搜尋條碼")
      if sub_barcode:
        if input_code.strip():
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute("SELECT * FROM food_catalog WHERE barcode = ?", (input_code.strip(),))
            res = c.fetchone()
            conn.close()
            if res:
              st.success(f"🎉 找到對應商品：【{res[1]}】(品牌: {res[4]})")
            else:
              st.error("❌ 找不到此條碼對應的商品，請先至主檔建立！")
          except Exception as e:
            st.error(f"查詢發生錯誤: {e}")


# --- 功能七：保養品/商品使用心得與實驗筆記 (含照片) ---
elif menu == "🧪 保養品/商品使用心得與實驗筆記 (含照片)":
  st.header("🧪 專屬保養品與美妝「實驗與使用心得」筆記 (含照片對比)")

  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query(
        "SELECT id, name, brand, item_type, usage_instructions FROM food_catalog",
        conn,
    )
    reviews_df = pd.read_sql_query(
        """
        SELECT r.*, c.name as product_name, u.name as user_name 
        FROM item_reviews r
        LEFT JOIN food_catalog c ON r.catalog_id = c.id
        LEFT JOIN users u ON r.user_id = u.id
    """,
        conn,
    )
    conn.close()
  except Exception:
    cat_df, reviews_df = pd.DataFrame(), pd.DataFrame()

  tab_rev_add, tab_rev_list = st.tabs(["✍️ 新增心得與膚況照片", "📖 查看所有心得與紀錄"])

  with tab_rev_add:
    if cat_df.empty:
      st.warning("請先至「商品與保養品主檔管理」建立商品！")
    else:
      with st.form("review_form", clear_on_submit=True):
        sel_prod = st.selectbox("選擇商品/保養品", cat_df["name"].tolist())

        selected_prod_row = cat_df[cat_df["name"] == sel_prod].iloc[0]
        if (
            pd.notna(selected_prod_row["usage_instructions"])
            and selected_prod_row["usage_instructions"].strip()
        ):
          st.info(
              "💡 **官方/記錄的使用方法**："
              f" {selected_prod_row['usage_instructions']}"
          )

        r_date = st.date_input("心得記錄日期", datetime.date.today())

        col_r1, col_r2 = st.columns(2)
        with col_r1:
          rating = st.slider(
              "綜合評分 (⭐ 蜜糖到 💩 毒藥)", min_value=1, max_value=5, value=4
          )
          re_buy_intent = st.selectbox(
              "回購意願", ["🔥 必回購 (蜜糖)", "🤔 觀望中", "❌ 絕不回購 (毒藥/踩雷)"]
          )
          texture_feel = st.text_input(
              "質地與吸收感受 (例如：質地清爽水潤、吸收快)"
          )
        with col_r2:
          effectiveness = st.text_input(
              "短期/長期效果 (例如：連續用7天毛孔變細)"
          )
          side_effects = st.text_input("不良反應/副作用 (例如：無過敏)")

        notes = st.text_area("詳細實驗心得筆記")
        uploaded_file = st.file_uploader("📸 上傳膚況對比照 / 使用前後照片", type=["jpg", "jpeg", "png"])

        if st.form_submit_button("儲存心得筆記"):
          p_id = selected_prod_row["id"]
          img_path_str = ""
          if uploaded_file is not None:
            img_path_str = uploaded_file.name

          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                        INSERT INTO item_reviews (
                            catalog_id, user_id, review_date, rating, texture_feel, 
                            effectiveness, side_effects, re_buy_intent, notes, image_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (
                    p_id,
                    current_user_id,
                    str(r_date),
                    rating,
                    texture_feel,
                    effectiveness,
                    side_effects,
                    re_buy_intent,
                    notes,
                    img_path_str,
                ),
            )
            conn.commit()
            conn.close()
            st.success(f"成功儲存「{sel_prod}」的使用心得筆記！")
            st.rerun()
          except Exception as e:
            st.error(f"儲存失敗: {e}")

  with tab_rev_list:
    if reviews_df.empty:
      st.info("目前還沒有任何使用心得筆記。")
    else:
      for idx, row in reviews_df.iterrows():
        with st.expander(f"⭐ {row['rating']}分 | {row['product_name']} ({row['user_name']} - {row['review_date']})"):
          st.markdown(f"**回購意願：** {row['re_buy_intent']}")
          st.markdown(f"**質地感受：** {row['texture_feel']}")
          st.markdown(f"**使用效果：** {row['effectiveness']}")
          st.markdown(f"**不良反應：** {row['side_effects']}")
          st.markdown(f"**詳細筆記：**\n{row['notes']}")
          if row["image_path"]:
            st.info(f"📸 附加照片檔名紀錄：{row['image_path']}")


# --- 功能八：新增購買批次 (快速入庫) ---
elif menu == "📥 新增購買批次 (快速入庫)":
  st.header("📥 記錄新進貨 / 購買批次 (支援海外代購與 PAO 開封設定)")
  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query(
        "SELECT id, name, origin_country, usage_instructions FROM food_catalog",
        conn,
    )
    conn.close()
  except Exception:
    cat_df = pd.DataFrame()

  if cat_df.empty:
    st.warning("⚠️ 找不到商品主檔！")
  else:
    with st.form("batch_form", clear_on_submit=True):
      selected_catalog_name = st.selectbox("選擇商品", cat_df["name"].tolist())
      sel_cat_row = cat_df[cat_df["name"] == selected_catalog_name].iloc[0]

      if (
          pd.notna(sel_cat_row["usage_instructions"])
          and sel_cat_row["usage_instructions"].strip()
      ):
        st.info(f"📖 **使用方法提示**：{sel_cat_row['usage_instructions']}")

      col_imp1, col_imp2 = st.columns(2)
      with col_imp1:
        is_imported_chk = st.checkbox("✈️ 海外代購 / 國外購入", value=False)
      with col_imp2:
        foreign_price_input = st.text_input("外幣價格備註 (例如：￥4,500)", value="")

      col1, col2 = st.columns(2)
      with col1:
        channel = st.text_input("購買管道 (例如：日本藥妝店、專櫃)")
        weight = st.number_input("總容量/數量 (g, ml 或 件)", value=1.0)
      with col2:
        price = st.number_input("台幣結帳金額 (NT$，不記得可填 0)", min_value=0.0)
        discount_info = st.text_input("優惠備註")

      col3, col4, col5 = st.columns(3)
      purchase_date = col3.date_input("購買日期", datetime.date.today())
      expiry_date = col4.date_input(
          "有效期限 (瓶身印的總效期)",
          datetime.date.today() + datetime.timedelta(days=365),
      )
      status = col5.selectbox("目前狀態", ["未開封", "已開封", "已用完"])

      st.markdown("---")
      st.markdown("**🧴 開封後效期 (PAO) 設定**")
      c_pao1, c_pao2 = st.columns(2)
      opened_date = c_pao1.date_input("實際開封日期 (若狀態為已開封)", datetime.date.today())
      pao_months = c_pao2.number_input("PAO 開封後有效月數 (例如罐子寫 12M 填 12)", min_value=1, max_value=60, value=12)

      if st.form_submit_button("確認入庫"):
        try:
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute(
              """
                INSERT INTO inventory_batches (
                    catalog_id, channel, is_imported, foreign_price, weight, current_weight, 
                    original_price, price, discount_info, unit_price, purchase_date, expiry_date, 
                    opened_date, pao_months, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
              (
                  sel_cat_row["id"],
                  channel,
                  1 if is_imported_chk else 0,
                  foreign_price_input,
                  weight,
                  weight,
                  price,
                  price,
                  discount_info,
                  (price / weight) if weight > 0 else 0,
                  str(purchase_date),
                  str(expiry_date),
                  str(opened_date) if status == "已開封" else "",
                  pao_months,
                  status,
              ),
          )
          conn.commit()
          conn.close()
          st.success("入庫成功！")
        except Exception as e:
          st.error(f"入庫失敗: {e}")


# --- 功能九：菜單、烹飪與冰箱清倉推薦 ---
elif menu == "📋 菜單、烹飪與冰箱推薦":
  st.header("📋 智慧菜單與烹飪扣庫存")
  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query(
        "SELECT id, name FROM food_catalog WHERE item_type = '食品'", conn
    )
    recipes_df = pd.read_sql_query("SELECT * FROM recipes", conn)
    conn.close()
  except Exception:
    cat_df, recipes_df = pd.DataFrame(), pd.DataFrame()

  tab1, tab2 = st.tabs(["📖 現有菜單", "✨ 新增菜單"])
  with tab2:
    with st.form("add_recipe", clear_on_submit=True):
      rtitle = st.text_input("菜名")
      ingredient_inputs = []
      if not cat_df.empty:
        for idx, row in cat_df.iterrows():
          ca, cb = st.columns([2, 1])
          if ca.checkbox(row["name"], key=f"rc_{row['id']}"):
            amt = cb.number_input("g/ml", value=100.0, key=f"ra_{row['id']}")
            ingredient_inputs.append(f"{row['name']}:{amt}")
      rinst = st.text_area("烹飪步驟")
      if st.form_submit_button("儲存菜單"):
        conn = sqlite3.connect("pantry.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO recipes (title, ingredients_detail, instructions) VALUES (?, ?, ?)",
            (rtitle, ",".join(ingredient_inputs), rinst),
        )
        conn.commit()
        conn.close()
        st.success("新增成功！")
        st.rerun()

  with tab1:
    if recipes_df.empty:
      st.info("尚無菜單。")
    else:
      for index, row in recipes_df.iterrows():
        with st.expander(f"🍳 {row['title']}"):
          st.markdown(f"**步驟：**\n{row['instructions']}")


# --- 功能十：智能自動補貨清單 ---
elif menu == "🛒 智能自動補貨清單 (含日用品/保養品)":
  st.header("🛒 智能自動補貨清單 (食品、日用品與保養品全包)")
  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query("SELECT * FROM food_catalog", conn)
    batches_df = pd.read_sql_query("SELECT * FROM inventory_batches", conn)
    conn.close()
  except Exception:
    cat_df, batches_df = pd.DataFrame(), pd.DataFrame()

  if not cat_df.empty:
    shopping_list = []
    for idx, c_row in cat_df.iterrows():
      b_subset = (
          batches_df[batches_df["catalog_id"] == c_row["id"]]
          if not batches_df.empty
          else pd.DataFrame()
      )
      active_batches = (
          b_subset[b_subset["status"] != "已用完"]
          if not b_subset.empty
          else pd.DataFrame()
      )
      if active_batches.empty or active_batches["current_weight"].sum() <= 0:
        shopping_list.append({
            "品名": c_row["name"],
            "屬性": c_row["item_type"],
            "產地": c_row["origin_country"],
            "品牌": c_row["brand"] or "無",
        })
    if shopping_list:
      st.warning(f"📋 系統偵測到有 **{len(shopping_list)}** 項商品需要補貨：")
      st.dataframe(pd.DataFrame(shopping_list), use_container_width=True)
    else:
      st.success("🎉 目前所有品項庫存充足！")


# --- 功能十一：支出分析與預算 ---
elif menu == "🛒 支出分析、預算與比價":
  st.header("🛒 智慧購物與預算控管")
  try:
    conn = sqlite3.connect("pantry.db")
    df = pd.read_sql_query("SELECT * FROM inventory_batches", conn)
    conn.close()
  except Exception:
    df = pd.DataFrame()

  if not df.empty:
    default_budget = float(get_setting("monthly_budget", "5000"))
    b_val = st.number_input("每月預算上限 (元)", value=default_budget)
    if st.button("儲存預算"):
      set_setting("monthly_budget", b_val)
      st.success("預算儲存成功！")
    st.metric("累計總花費", f"NT$ {df['price'].sum():.1f}")