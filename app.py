import datetime
import sqlite3
import pandas as pd
import streamlit as st

# 頁面基本設定
st.set_page_config(
    page_title="個人與多成員食品與智慧減脂管理庫", page_icon="🍎", layout="wide"
)


# --- 資料庫初始化 (含強健防呆與自動補償機制) ---
def init_db():
  conn = sqlite3.connect("pantry.db")
  c = conn.cursor()

  # 1. 分類表 (確保 name 欄位有 UNIQUE 約束)
  c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

  default_cats = ["調味料", "冷凍肉品", "零食", "生鮮", "主食", "飲料", "其他"]
  for cat in default_cats:
    try:
      c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
    except sqlite3.OperationalError:
      pass

  # 2. 食品主檔
  c.execute("""
        CREATE TABLE IF NOT EXISTS food_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            brand TEXT,
            category TEXT,
            ingredients TEXT,
            calories REAL,
            protein REAL,
            fat REAL,
            carbs REAL,
            sugar REAL,
            sodium REAL
        )
    """)

  # 3. 批次庫存 (含 current_weight)
  c.execute("""
        CREATE TABLE IF NOT EXISTS inventory_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog_id INTEGER,
            channel TEXT,
            weight REAL,
            current_weight REAL,
            original_price REAL,
            price REAL,
            discount_info TEXT,
            unit_price REAL,
            purchase_date TEXT,
            expiry_date TEXT,
            status TEXT,
            FOREIGN KEY (catalog_id) REFERENCES food_catalog (id)
        )
    """)

  # 防呆：自動補上可能缺少的欄位
  try:
    c.execute("ALTER TABLE inventory_batches ADD COLUMN purchase_date TEXT DEFAULT ''")
  except sqlite3.OperationalError:
    pass

  try:
    c.execute("ALTER TABLE inventory_batches ADD COLUMN current_weight REAL DEFAULT 0.0")
  except sqlite3.OperationalError:
    pass

  # 4. 菜單資料表
  c.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            ingredients_detail TEXT,
            instructions TEXT
        )
    """)

  # 5. 系統設定表
  c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

  # 6. 使用者資料表 (多人支援)
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

  # 7. 每日飲食紀錄表 (減脂打卡)
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

  # 預設建立一個預設成員（如果完全沒有人）
  c.execute("SELECT COUNT(*) FROM users")
  if c.fetchone()[0] == 0:
    c.execute(
        """
            INSERT INTO users (name, gender, age, height, weight, activity_level, goal_deficit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("預設成員", "男", 30, 175.0, 70.0, 1.2, 400.0),
    )

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
    return cats if cats else ["調味料", "冷凍肉品", "零食", "生鮮", "主食", "飲料", "其他"]
  except Exception:
    return ["調味料", "冷凍肉品", "零食", "生鮮", "主食", "飲料", "其他"]


# --- 日期防呆解析函式 ---
def check_expiry(date_str):
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


# --- 側邊欄全域設定：選擇目前操作的使用者 ---
st.sidebar.title("🍎 糧倉與減脂筆記")

try:
  conn = sqlite3.connect("pantry.db")
  users_df = pd.read_sql_query("SELECT * FROM users", conn)
  conn.close()
except Exception:
  users_df = pd.DataFrame()

if not users_df.empty:
  user_names = users_df["name"].tolist()
  selected_user_name = st.sidebar.selectbox("👤 目前操作成員", user_names)
  current_user_row = users_df[users_df["name"] == selected_user_name].iloc[0]
  current_user_id = current_user_row["id"]
else:
  current_user_id = 1
  selected_user_name = "預設成員"
  current_user_row = pd.Series({
      "gender": "男",
      "age": 30,
      "height": 175.0,
      "weight": 70.0,
      "activity_level": 1.2,
      "goal_deficit": 400.0,
  })

st.sidebar.markdown("---")
menu = st.sidebar.selectbox(
    "選擇功能",
    [
        "🔥 每日飲食打卡與減脂儀表板",
        "👥 成員管理與目標設定",
        "📦 庫存與批次總覽",
        "🏷️ 食品主檔管理",
        "📥 新增購買批次 (快速入庫)",
        "📋 菜單、烹飪與冰箱推薦",
        "🛒 支出分析、預算與比價",
    ],
)

# 側邊欄：管理自訂分類
st.sidebar.markdown("---")
st.sidebar.subheader("🏷️ 分類管理")
new_cat_input = st.sidebar.text_input("新增自訂分類")
if st.sidebar.button("新增分類"):
  if new_cat_input.strip():
    try:
      conn = sqlite3.connect("pantry.db")
      c = conn.cursor()
      c.execute("INSERT INTO categories (name) VALUES (?)", (new_cat_input.strip(),))
      conn.commit()
      conn.close()
      st.sidebar.success(f"成功新增分類：「{new_cat_input.strip()}」")
      st.rerun()
    except sqlite3.IntegrityError:
      st.sidebar.warning("這個分類名稱已經存在囉！")
    except Exception as e:
      st.sidebar.error(f"發生錯誤: {e}")
  else:
    st.sidebar.error("請輸入名稱。")

current_cats = get_categories()


# --- 功能一：成員管理與目標設定 ---
if menu == "👥 成員管理與目標設定":
  st.header("👥 家庭成員與減脂目標設定")
  st.markdown("在此新增成員或調整每個人的身體數據，系統會自動計算減脂建議熱量！")

  tab_m1, tab_m2 = st.tabs(["➕ 新增成員", "✏️ 編輯現有成員身體數據"])

  with tab_m1:
    with st.form("add_user_form", clear_on_submit=True):
      u_name = st.text_input("成員姓名 (例如：小明)")
      u_gender = st.selectbox("生理性別", ["男", "女"])
      u_age = st.number_input("年齡", min_value=1, max_value=120, value=25)
      u_height = st.number_input("身高 (cm)", min_value=50.0, max_value=250.0, value=170.0)
      u_weight = st.number_input("體重 (kg)", min_value=20.0, max_value=300.0, value=65.0)
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
          "減脂熱量赤字 (大卡，建議 300 ~ 500)", min_value=0.0, max_value=1000.0, value=400.0, step=50.0
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
                (u_name.strip(), u_gender, u_age, u_height, u_weight, u_activity, u_deficit),
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
      edit_u_name = st.selectbox("選擇要編輯的成員", users_df["name"].tolist(), key="edit_u_select")
      row_u = users_df[users_df["name"] == edit_u_name].iloc[0]

      with st.form("edit_user_form"):
        eu_gender = st.selectbox("生理性別", ["男", "女"], index=0 if row_u["gender"] == "男" else 1)
        eu_age = st.number_input("年齡", min_value=1, max_value=120, value=int(row_u["age"] or 25))
        eu_height = st.number_input("身高 (cm)", min_value=50.0, max_value=250.0, value=float(row_u["height"] or 170.0))
        eu_weight = st.number_input("體重 (kg)", min_value=20.0, max_value=300.0, value=float(row_u["weight"] or 65.0))
        
        act_options = [1.2, 1.375, 1.55, 1.725, 1.9]
        default_act_idx = act_options.index(row_u["activity_level"]) if row_u["activity_level"] in act_options else 0
        eu_activity = st.selectbox("日常活動量係數", options=act_options, index=default_act_idx)
        eu_deficit = st.number_input("減脂熱量赤字 (大卡)", min_value=0.0, max_value=1000.0, value=float(row_u["goal_deficit"] or 400.0))

        sub_edit = st.form_submit_button("儲存修改")
        if sub_edit:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                    UPDATE users SET gender = ?, age = ?, height = ?, weight = ?, activity_level = ?, goal_deficit = ?
                    WHERE id = ?
                """,
                (eu_gender, eu_age, eu_height, eu_weight, eu_activity, eu_deficit, row_u["id"]),
            )
            conn.commit()
            conn.close()
            st.success("成員資料更新成功！")
            st.rerun()
          except Exception as e:
            st.error(f"更新失敗: {e}")


# --- 功能二：每日飲食打卡與減脂儀表板 ---
elif menu == "🔥 每日飲食打卡與減脂儀表板":
  st.header(f"🔥 【{selected_user_name}】的每日飲食打卡與減脂儀表板")

  gender = current_user_row["gender"]
  weight = float(current_user_row["weight"])
  height = float(current_user_row["height"])
  age = int(current_user_row["age"])
  activity = float(current_user_row["activity_level"])
  deficit = float(current_user_row["goal_deficit"])

  # 基礎代謝率 (Mifflin-St Jeor 公式)
  if gender == "男":
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
  else:
    bmr = (10 * weight) + (6.25 * height) - (5 * age) - 161

  tdee = bmr * activity
  target_calories = max(tdee - deficit, 1200)
  target_protein = weight * 1.8

  col_sum1, col_sum2, col_sum3, col_sum4 = st.columns(4)
  col_sum1.metric("基礎代謝 (BMR)", f"{bmr:.0f} 大卡")
  col_sum2.metric("每日總消耗 (TDEE)", f"{tdee:.0f} 大卡")
  col_sum3.metric("🎯 減脂建議熱量上限", f"{target_calories:.0f} 大卡")
  col_sum4.metric("🎯 建議蛋白質目標", f"{target_protein:.1f} g")

  st.markdown("---")

  selected_log_date = st.date_input("選擇打卡日期", datetime.date.today())
  date_str = str(selected_log_date)

  try:
    conn = sqlite3.connect("pantry.db")
    logs_df = pd.read_sql_query(
        "SELECT * FROM daily_logs WHERE user_id = ? AND log_date = ?", conn, params=(current_user_id, date_str)
    )
    recipes_df = pd.read_sql_query("SELECT id, title, ingredients_detail FROM recipes", conn)
    cat_df = pd.read_sql_query("SELECT id, name, calories, protein, fat, carbs FROM food_catalog", conn)
    conn.close()
  except Exception:
    logs_df = pd.DataFrame()
    recipes_df = pd.DataFrame()
    cat_df = pd.DataFrame()

  total_cal_consumed = logs_df["calories"].sum() if not logs_df.empty and "calories" in logs_df else 0.0
  total_pro_consumed = logs_df["protein"].sum() if not logs_df.empty and "protein" in logs_df else 0.0
  total_fat_consumed = logs_df["fat"].sum() if not logs_df.empty and "fat" in logs_df else 0.0
  total_carbs_consumed = logs_df["carbs"].sum() if not logs_df.empty and "carbs" in logs_df else 0.0

  st.subheader(f"📊 {date_str} 營養攝取進度")
  c_p1, c_p2 = st.columns(2)
  with c_p1:
    st.markdown(f"**熱量攝取：{total_cal_consumed:.1f} / {target_calories:.0f} 大卡**")
    cal_pct = total_cal_consumed / target_calories if target_calories > 0 else 0
    st.progress(min(cal_pct, 1.0))
    if total_cal_consumed > target_calories:
      st.warning("⚠️ 今日熱量已超過減脂目標上限！")
    else:
      st.success(f"🟢 距離減脂熱量上限還有：{target_calories - total_cal_consumed:.1f} 大卡")

  with c_p2:
    st.markdown(f"**蛋白質攝取：{total_pro_consumed:.1f} / {target_protein:.1f} g**")
    pro_pct = total_pro_consumed / target_protein if target_protein > 0 else 0
    st.progress(min(pro_pct, 1.0))
    st.info(f"💪 碳水: {total_carbs_consumed:.1f}g | 脂肪: {total_fat_consumed:.1f}g")

  st.markdown("---")
  st.subheader("➕ 新增今日飲食打卡")

  tab_log1, tab_log2, tab_log3 = st.tabs(["🍳 從智慧菜單匯入", "🥫 從現成食品主檔直接選取 (自動扣庫存)", "✍️ 自訂/外食手動輸入"])

  with tab_log1:
    if recipes_df.empty:
      st.info("目前還沒有建立任何菜單！")
    else:
      with st.form("log_recipe_form", clear_on_submit=True):
        meal_type = st.selectbox("餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_r")
        selected_recipe_title = st.selectbox("選擇菜單", recipes_df["title"].tolist())
        
        sub_log_recipe = st.form_submit_button("匯入此菜單營養至今日打卡")
        if sub_log_recipe:
          r_row = recipes_df[recipes_df["title"] == selected_recipe_title].iloc[0]
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
                    r_cal += (float(m["calories"].values[0] or 0) / 100.0) * famt
                    r_pro += (float(m["protein"].values[0] or 0) / 100.0) * famt
                    r_fat += (float(m["fat"].values[0] or 0) / 100.0) * famt
                    r_carbs += (float(m["carbs"].values[0] or 0) / 100.0) * famt
            except Exception:
              pass

          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                    INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (current_user_id, date_str, meal_type, f"[菜單] {selected_recipe_title}", 0.0, r_cal, r_pro, r_fat, r_carbs),
            )
            conn.commit()
            conn.close()
            st.success(f"成功將「{selected_recipe_title}」加入打卡！")
            st.rerun()
          except Exception as e:
            st.error(f"寫入打卡失敗: {e}")

  with tab_log2:
    if cat_df.empty:
      st.info("目前沒有任何食品主檔資料，請先至「食品主檔管理」新增！")
    else:
      with st.form("log_catalog_form", clear_on_submit=True):
        meal_type_c = st.selectbox("餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_c")
        selected_food_name = st.selectbox("選擇現成食品 (來自食品主檔)", cat_df["name"].tolist())
        consume_weight = st.number_input("食用克數或毫升數 (g / ml)", min_value=1.0, value=100.0)

        sub_log_cat = st.form_submit_button("確認以此現成食品打卡並自動扣庫存")
        if sub_log_cat:
          f_row = cat_df[cat_df["name"] == selected_food_name].iloc[0]
          cid = f_row["id"]
          ratio = consume_weight / 100.0
          c_cal = float(f_row["calories"] or 0) * ratio
          c_pro = float(f_row["protein"] or 0) * ratio
          c_fat = float(f_row["fat"] or 0) * ratio
          c_carbs = float(f_row["carbs"] or 0) * ratio

          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            
            # 1. 寫入每日飲食打卡
            c.execute(
                """
                    INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (current_user_id, date_str, meal_type_c, f"[現成] {selected_food_name}", consume_weight, c_cal, c_pro, c_fat, c_carbs),
            )
            
            # 2. 自動執行 FIFO 扣除對應批次庫存
            c.execute("SELECT id, current_weight FROM inventory_batches WHERE catalog_id = ? AND status != '已用完' ORDER BY expiry_date ASC", (cid,))
            batches = c.fetchall()
            rem = consume_weight
            for b_id, cur_w in batches:
              if rem <= 0:
                break
              cur_w = float(cur_w or 0.0)
              if cur_w > rem:
                c.execute("UPDATE inventory_batches SET current_weight = ?, status = '已開封' WHERE id = ?", (cur_w - rem, b_id))
                rem = 0.0
              else:
                rem -= cur_w
                c.execute("UPDATE inventory_batches SET current_weight = 0.0, status = '已用完' WHERE id = ?", (b_id,))

            conn.commit()
            conn.close()
            st.success(f"成功打卡「{selected_food_name} ({consume_weight}g)」並已同步自動扣除冰箱庫存！")
            st.rerun()
          except Exception as e:
            st.error(f"打卡或扣庫存發生錯誤: {e}")

  with tab_log3:
    with st.form("log_manual_form", clear_on_submit=True):
      meal_type_m = st.selectbox("餐別", ["早餐", "午餐", "晚餐", "點心"], key="meal_m")
      manual_name = st.text_input("外食 / 食物名稱 (例如：便利商店雞胸肉、公司附近排骨便當)")
      manual_amt = st.number_input("食用重量/份量 (g 或 ml)", min_value=1.0, value=100.0)
      m_cal = st.number_input("總熱量 (大卡)", min_value=0.0, value=150.0)
      m_pro = st.number_input("蛋白質 (g)", min_value=0.0, value=15.0)
      m_fat = st.number_input("脂肪 (g)", min_value=0.0, value=5.0)
      m_carbs = st.number_input("碳水 (g)", min_value=0.0, value=10.0)

      sub_log_m = st.form_submit_button("確認新增外食/自訂打卡")
      if sub_log_m:
        if not manual_name.strip():
          st.error("請輸入食物名稱！")
        else:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                    INSERT INTO daily_logs (user_id, log_date, meal_type, food_name, weight, calories, protein, fat, carbs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (current_user_id, date_str, meal_type_m, manual_name.strip(), manual_amt, m_cal, m_pro, m_fat, m_carbs),
            )
            conn.commit()
            conn.close()
            st.success(f"成功新增打卡：{manual_name}")
            st.rerun()
          except Exception as e:
            st.error(f"寫入失敗: {e}")

  st.markdown("---")
  st.subheader(f"📋 {date_str} 飲食紀錄明細與刪除")
  if logs_df.empty:
    st.info("今天還沒有任何飲食打卡紀錄！")
  else:
    st.dataframe(
        logs_df[["meal_type", "food_name", "weight", "calories", "protein", "fat", "carbs"]],
        use_container_width=True,
        column_config={
            "meal_type": "餐別",
            "food_name": "食物名稱",
            "weight": "份量(g/ml)",
            "calories": "熱量(大卡)",
            "protein": "蛋白質(g)",
            "fat": "脂肪(g)",
            "carbs": "碳水(g)",
        },
    )

    del_log_id = st.selectbox(
        "選擇要刪除的打卡紀錄 ID",
        options=logs_df["id"],
        format_func=lambda x: f"紀錄 ID: {x} - {logs_df[logs_df['id'] == x]['meal_type'].values[0]}: {logs_df[logs_df['id'] == x]['food_name'].values[0]}",
    )
    if st.button("刪除選定打卡紀錄"):
      try:
        conn = sqlite3.connect("pantry.db")
        c = conn.cursor()
        c.execute("DELETE FROM daily_logs WHERE id = ?", (del_log_id,))
        conn.commit()
        conn.close()
        st.success("已成功刪除該筆打卡！")
        st.rerun()
      except Exception as e:
        st.error(f"刪除失敗: {e}")


# --- 功能三：食品主檔管理 ---
elif menu == "🏷️ 食品主檔管理":
  st.header("🏷️ 食品主檔資料庫與維護")
  tab_add, tab_edit_del = st.tabs(["➕ 新增食品主檔", "✏️ 修改與刪除主檔"])

  with tab_add:
    with st.form("catalog_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        name = st.text_input("食品名稱 * (例如：義美鮮奶 946ml)")
        brand = st.text_input("品牌 (例如：義美)")
        category = st.selectbox("分類", current_cats)
      with col2:
        ingredients = st.text_area("成分清單")

      st.markdown("**營養標示 (每 100g / 100ml)**")
      c3, c4, c5, c6, c7, c8 = st.columns(6)
      calories = c3.number_input("熱量", min_value=0.0, value=0.0)
      protein = c4.number_input("蛋白質", min_value=0.0, value=0.0)
      fat = c5.number_input("脂肪", min_value=0.0, value=0.0)
      carbs = c6.number_input("碳水", min_value=0.0, value=0.0)
      sugar = c7.number_input("糖", min_value=0.0, value=0.0)
      sodium = c8.number_input("鈉", min_value=0.0, value=0.0)

      if st.form_submit_button("儲存食品主檔"):
        if not name:
          st.error("請填寫食品名稱！")
        else:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute(
                """
                        INSERT INTO food_catalog (name, brand, category, ingredients, calories, protein, fat, carbs, sugar, sodium)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                (name, brand, category, ingredients, calories, protein, fat, carbs, sugar, sodium),
            )
            conn.commit()
            conn.close()
            st.success(f"成功建立主檔：「{name}」！")
            st.rerun()
          except sqlite3.IntegrityError:
            st.error("這個食品名稱已經存在主檔中囉！")
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
      st.info("目前尚無主檔。")
    else:
      sel_id = st.selectbox("選擇要編輯的食品主檔", options=cat_df["id"].tolist(), format_func=lambda x: cat_df[cat_df['id'] == x]['name'].values[0])
      r_sel = cat_df[cat_df["id"] == sel_id].iloc[0]
      with st.form("edit_cat"):
        en = st.text_input("名稱", value=r_sel["name"])
        eb = st.text_input("品牌", value=str(r_sel["brand"]) if pd.notna(r_sel["brand"]) else "")
        ec = st.selectbox("分類", current_cats, index=current_cats.index(r_sel["category"]) if r_sel["category"] in current_cats else 0)
        ei = st.text_area("成分", value=str(r_sel["ingredients"]) if pd.notna(r_sel["ingredients"]) else "")
        
        c3, c4, c5, c6, c7, c8 = st.columns(6)
        ecal = c3.number_input("熱量", value=float(r_sel["calories"] or 0))
        epro = c4.number_input("蛋白質", value=float(r_sel["protein"] or 0))
        efat = c5.number_input("脂肪", value=float(r_sel["fat"] or 0))
        ecarb = c6.number_input("碳水", value=float(r_sel["carbs"] or 0))
        esug = c7.number_input("糖", value=float(r_sel["sugar"] or 0))
        esod = c8.number_input("鈉", value=float(r_sel["sodium"] or 0))

        if st.form_submit_button("儲存修改"):
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute("""
                UPDATE food_catalog SET name=?, brand=?, category=?, ingredients=?, calories=?, protein=?, fat=?, carbs=?, sugar=?, sodium=?
                WHERE id=?
            """, (en, eb, ec, ei, ecal, epro, efat, ecarb, esug, esod, sel_id))
            conn.commit()
            conn.close()
            st.success("更新成功！")
            st.rerun()
          except Exception as e:
            st.error(f"更新失敗: {e}")


# --- 功能四：新增購買批次 (快速入庫) ---
elif menu == "📥 新增購買批次 (快速入庫)":
  st.header("📥 記錄新進貨 / 購買批次")
  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
    conn.close()
  except Exception:
    cat_df = pd.DataFrame()

  if cat_df.empty:
    st.warning("⚠️ 找不到任何食品主檔！請先至食品主檔管理建立商品。")
  else:
    with st.form("batch_form", clear_on_submit=True):
      selected_catalog_name = st.selectbox("選擇已存在的食品主檔", options=cat_df["name"].tolist())
      col1, col2 = st.columns(2)
      with col1:
        channel = st.text_input("購買管道 (例如：好市多、全聯)")
        weight = st.number_input("總重量 / 容量 (g 或 ml)", min_value=1.0, value=946.0)
      with col2:
        original_price = st.number_input("標示原價 (元)", min_value=0.0)
        price = st.number_input("實際結帳金額 (元)", min_value=0.0)
        discount_info = st.text_input("優惠備註")

      col3, col4, col5 = st.columns(3)
      purchase_date = col3.date_input("購買日期", datetime.date.today())
      expiry_date = col4.date_input("有效期限", datetime.date.today() + datetime.timedelta(days=30))
      status = col5.selectbox("目前狀態", ["未開封", "已開封", "已用完"])

      if st.form_submit_button("確認入庫"):
        cat_id = cat_df[cat_df["name"] == selected_catalog_name]["id"].values[0]
        use_price = price if price > 0 else original_price
        unit_price = round((use_price / weight) * 100, 2) if weight > 0 else 0.0

        try:
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute(
              """
                INSERT INTO inventory_batches (
                    catalog_id, channel, weight, current_weight, original_price, price, discount_info, unit_price, purchase_date, expiry_date, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
              (cat_id, channel, weight, weight, original_price, use_price, discount_info, unit_price, str(purchase_date), str(expiry_date), status),
          )
          conn.commit()
          conn.close()
          st.success(f"成功將「{selected_catalog_name}」入庫！")
        except Exception as e:
          st.error(f"入庫失敗: {e}")


# --- 功能五：庫存與批次總覽 ---
elif menu == "📦 庫存與批次總覽":
  st.header("📦 個人食品庫存與效期總覽")
  try:
    conn = sqlite3.connect("pantry.db")
    query = """
        SELECT 
            b.id as batch_id,
            COALESCE(c.name, '未知商品') as name,
            COALESCE(c.brand, '') as brand,
            COALESCE(c.category, '其他') as category,
            b.channel as channel,
            b.price as price,
            b.weight as weight,
            b.current_weight as current_weight,
            b.unit_price as unit_price,
            b.purchase_date as purchase_date,
            b.expiry_date as expiry_date,
            b.status as status
        FROM inventory_batches b
        LEFT JOIN food_catalog c ON b.catalog_id = c.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
  except Exception:
    df = pd.DataFrame()

  if df.empty:
    st.info("目前庫存沒有任何批次資料！")
  else:
    df["效期狀態"] = df["expiry_date"].apply(check_expiry)
    st.dataframe(df, use_container_width=True)


# --- 功能六：菜單、烹飪與冰箱推薦 ---
elif menu == "📋 菜單、烹飪與冰箱推薦":
  st.header("📋 智慧菜單與精準烹飪扣庫存")
  try:
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
    conn.close()
  except Exception:
    cat_df = pd.DataFrame()

  tab1, tab2 = st.tabs(["📖 現有菜單與烹飪扣庫存", "✨ 新增菜單"])
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
        if not rtitle.strip():
          st.error("請輸入菜名！")
        else:
          try:
            conn = sqlite3.connect("pantry.db")
            c = conn.cursor()
            c.execute("INSERT INTO recipes (title, ingredients_detail, instructions) VALUES (?, ?, ?)", (rtitle, ",".join(ingredient_inputs), rinst))
            conn.commit()
            conn.close()
            st.success("成功新增菜單！")
            st.rerun()
          except Exception as e:
            st.error(f"新增菜單失敗: {e}")

  with tab1:
    try:
      conn = sqlite3.connect("pantry.db")
      recipes_df = pd.read_sql_query("SELECT * FROM recipes", conn)
      full_cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
      conn.close()
    except Exception:
      recipes_df = pd.DataFrame()
      full_cat_df = pd.DataFrame()

    if recipes_df.empty:
      st.info("尚無菜單。")
    else:
      for index, row in recipes_df.iterrows():
        with st.expander(f"🍳 {row['title']}"):
          st.markdown(f"**步驟：**\n{row['instructions']}")
          if st.button("🔥 開始烹飪 (扣庫存)", key=f"cook_{row['id']}"):
            try:
              conn = sqlite3.connect("pantry.db")
              c = conn.cursor()
              for item in str(row["ingredients_detail"]).split(","):
                if ":" in item:
                  fname, famt_str = item.split(":")
                  famt = float(famt_str)
                  m = full_cat_df[full_cat_df["name"] == fname]
                  if not m.empty:
                    cid = m["id"].values[0]
                    c.execute("SELECT id, current_weight FROM inventory_batches WHERE catalog_id = ? AND status != '已用完' ORDER BY expiry_date ASC", (cid,))
                    batches = c.fetchall()
                    rem = famt
                    for b_id, cur_w in batches:
                      if rem <= 0:
                        break
                      cur_w = float(cur_w or 0.0)
                      if cur_w > rem:
                        c.execute("UPDATE inventory_batches SET current_weight = ?, status = '已開封' WHERE id = ?", (cur_w - rem, b_id))
                        rem = 0.0
                      else:
                        rem -= cur_w
                        c.execute("UPDATE inventory_batches SET current_weight = 0.0, status = '已用完' WHERE id = ?", (b_id,))
              conn.commit()
              conn.close()
              st.success(f"已完成烹飪「{row['title']}」並精準扣除庫存！")
              st.rerun()
            except Exception as e:
              st.error(f"烹飪扣庫存發生錯誤: {e}")


# --- 功能七：支出分析與預算 ---
elif menu == "🛒 支出分析、預算與比價":
  st.header("🛒 智慧購物與預算控管")
  try:
    conn = sqlite3.connect("pantry.db")
    df = pd.read_sql_query("SELECT * FROM inventory_batches", conn)
    conn.close()
  except Exception:
    df = pd.DataFrame()

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