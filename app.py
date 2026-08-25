import datetime
import sqlite3
import pandas as pd
import streamlit as st

# 頁面基本設定
st.set_page_config(
    page_title="個人食品與智慧菜單管理庫", page_icon="🍎", layout="wide"
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
  default_cats = ["調味料", "冷凍肉品", "零食", "生鮮", "主食", "飲料", "其他"]
  for cat in default_cats:
    c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

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

  # 💡 自動補上可能缺少的欄位（防呆機制，避免舊資料庫報錯）
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

  # 5. 系統設定表（儲存預算等）
  c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

  conn.commit()
  conn.close()


init_db()


def get_setting(key, default_val=""):
  conn = sqlite3.connect("pantry.db")
  c = conn.cursor()
  c.execute("SELECT value FROM settings WHERE key = ?", (key,))
  row = c.fetchone()
  conn.close()
  return row[0] if row else default_val


def set_setting(key, value):
  conn = sqlite3.connect("pantry.db")
  c = conn.cursor()
  c.execute(
      "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
      (key, str(value)),
  )
  conn.commit()
  conn.close()


def get_categories():
  conn = sqlite3.connect("pantry.db")
  c = conn.cursor()
  c.execute("SELECT name FROM categories")
  cats = [row[0] for row in c.fetchall()]
  conn.close()
  return cats


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


# --- 側邊欄導覽 ---
st.sidebar.title("🍎 糧倉筆記選單")
menu = st.sidebar.selectbox(
    "選擇功能",
    [
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
  else:
    st.sidebar.error("請輸入名稱。")

current_cats = get_categories()
st.sidebar.markdown(f"**現有分類：** {', '.join(current_cats)}")


# --- 功能一：食品主檔管理 (支援新增、修改與刪除) ---
if menu == "🏷️ 食品主檔管理":
  st.header("🏷️ 食品主檔資料庫與維護")
  st.markdown("這裡記錄食品的**營養標示與成分**，並支援新增、修改與刪除。")

  tab_add, tab_edit_del = st.tabs(["➕ 新增食品主檔", "✏️ 修改與刪除主檔"])

  with tab_add:
    st.subheader("新增食品基本資料")
    with st.form("catalog_form", clear_on_submit=True):
      col1, col2 = st.columns(2)
      with col1:
        name = st.text_input("食品名稱 * (例如：義美鮮奶 946ml)")
        brand = st.text_input("品牌 (例如：義美)")
        category = st.selectbox("分類", current_cats)
      with col2:
        ingredients = st.text_area("成分清單 (例如：100%生乳)")

      st.markdown("**營養標示 (請填寫每 100g / 100ml 的數值)**")
      c3, c4, c5, c6, c7, c8 = st.columns(6)
      with c3:
        calories = st.number_input("熱量 (大卡)", min_value=0.0, value=0.0)
      with c4:
        protein = st.number_input("蛋白質 (g)", min_value=0.0, value=0.0)
      with c5:
        fat = st.number_input("脂肪 (g)", min_value=0.0, value=0.0)
      with c6:
        carbs = st.number_input("碳水 (g)", min_value=0.0, value=0.0)
      with c7:
        sugar = st.number_input("糖 (g)", min_value=0.0, value=0.0)
      with c8:
        sodium = st.number_input("鈉 (mg)", min_value=0.0, value=0.0)

      submitted = st.form_submit_button("儲存食品主檔")
      if submitted:
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
                (
                    name,
                    brand,
                    category,
                    ingredients,
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
            st.error("這個食品名稱已經存在主檔中囉！")

  with tab_edit_del:
    st.subheader("修改或刪除現有食品主檔")
    conn = sqlite3.connect("pantry.db")
    cat_df = pd.read_sql_query("SELECT * FROM food_catalog", conn)
    conn.close()

    if cat_df.empty:
      st.info("目前尚無主檔資料。")
    else:
      selected_id = st.selectbox(
          "選擇要編輯或刪除的食品主檔",
          options=cat_df["id"].tolist(),
          format_func=lambda x: f"ID: {x} - {cat_df[cat_df['id'] == x]['name'].values[0]} ({cat_df[cat_df['id'] == x]['brand'].values[0]})",
      )

      selected_row = cat_df[cat_df["id"] == selected_id].iloc[0]

      with st.form("edit_catalog_form"):
        st.markdown(f"**正在編輯：{selected_row['name']} (ID: {selected_id})**")
        col1, col2 = st.columns(2)
        with col1:
          edit_name = st.text_input("食品名稱 *", value=selected_row["name"])
          edit_brand = st.text_input("品牌", value=str(selected_row["brand"]) if pd.notna(selected_row["brand"]) else "")
          
          cat_list = current_cats
          default_cat_idx = cat_list.index(selected_row["category"]) if selected_row["category"] in cat_list else 0
          edit_category = st.selectbox("分類", cat_list, index=default_cat_idx)
          
        with col2:
          edit_ingredients = st.text_area("成分清單", value=str(selected_row["ingredients"]) if pd.notna(selected_row["ingredients"]) else "")

        st.markdown("**營養標示修改 (每 100g / 100ml)**")
        c3, c4, c5, c6, c7, c8 = st.columns(6)
        with c3:
          edit_calories = st.number_input("熱量 (大卡)", min_value=0.0, value=float(selected_row["calories"] or 0.0))
        with c4:
          edit_protein = st.number_input("蛋白質 (g)", min_value=0.0, value=float(selected_row["protein"] or 0.0))
        with c5:
          edit_fat = st.number_input("脂肪 (g)", min_value=0.0, value=float(selected_row["fat"] or 0.0))
        with c6:
          edit_carbs = st.number_input("碳水 (g)", min_value=0.0, value=float(selected_row["carbs"] or 0.0))
        with c7:
          edit_sugar = st.number_input("糖 (g)", min_value=0.0, value=float(selected_row["sugar"] or 0.0))
        with c8:
          edit_sodium = st.number_input("鈉 (mg)", min_value=0.0, value=float(selected_row["sodium"] or 0.0))

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
          update_submitted = st.form_submit_button("💾 儲存修改")
        with col_btn2:
          delete_submitted = st.form_submit_button("🗑️ 刪除此主檔", type="primary")

        if update_submitted:
          if not edit_name:
            st.error("食品名稱不可為空白！")
          else:
            try:
              conn = sqlite3.connect("pantry.db")
              c = conn.cursor()
              c.execute(
                  """
                            UPDATE food_catalog 
                            SET name = ?, brand = ?, category = ?, ingredients = ?, 
                                calories = ?, protein = ?, fat = ?, carbs = ?, sugar = ?, sodium = ?
                            WHERE id = ?
                        """,
                  (
                      edit_name,
                      edit_brand,
                      edit_category,
                      edit_ingredients,
                      edit_calories,
                      edit_protein,
                      edit_fat,
                      edit_carbs,
                      edit_sugar,
                      edit_sodium,
                      selected_id,
                  ),
              )
              conn.commit()
              conn.close()
              st.success(f"成功更新主檔：「{edit_name}」！")
              st.rerun()
            except sqlite3.IntegrityError:
              st.error("更新失敗：這個食品名稱可能已經存在囉！")

        if delete_submitted:
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute("SELECT COUNT(*) FROM inventory_batches WHERE catalog_id = ?", (selected_id,))
          batch_count = c.fetchone()[0]
          
          if batch_count > 0:
            st.error(f"無法刪除！目前還有 {batch_count} 筆「庫存批次」正在使用此主檔，請先至庫存區刪除相關批次才能刪除主檔。")
          else:
            c.execute("DELETE FROM food_catalog WHERE id = ?", (selected_id,))
            conn.commit()
            st.success("已成功刪除該食品主檔！")
            st.rerun()
          conn.close()

  st.markdown("---")
  st.subheader("📚 現有食品主檔總覽")
  conn = sqlite3.connect("pantry.db")
  cat_df_view = pd.read_sql_query("SELECT * FROM food_catalog", conn)
  conn.close()
  if cat_df_view.empty:
    st.info("目前尚無主檔資料。")
  else:
    st.dataframe(cat_df_view, use_container_width=True)


# --- 功能二：新增購買批次 (快速入庫) ---
elif menu == "📥 新增購買批次 (快速入庫)":
  st.header("📥 記錄新進貨 / 購買批次")

  conn = sqlite3.connect("pantry.db")
  cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
  conn.close()

  if cat_df.empty:
    st.warning("⚠️ 找不到任何食品主檔！請先至左側選單建立商品基本資料。")
  else:
    with st.form("batch_form", clear_on_submit=True):
      selected_catalog_name = st.selectbox(
          "選擇已存在的食品主檔", options=cat_df["name"].tolist()
      )

      col1, col2 = st.columns(2)
      with col1:
        channel = st.text_input("購買管道 (例如：好市多、全聯)")
        weight = st.number_input(
            "總重量 / 容量 (g 或 ml)", min_value=1.0, step=10.0, value=946.0
        )
      with col2:
        original_price = st.number_input(
            "標示原價 (元)", min_value=0.0, step=1.0
        )
        price = st.number_input(
            "實際結帳金額 (元，若有特價填特價)", min_value=0.0, step=1.0
        )
        discount_info = st.text_input(
            "優惠備註 (例如：買一送一、全聯會員特價)"
        )

      col3, col4, col5 = st.columns(3)
      with col3:
        purchase_date = st.date_input("購買日期", datetime.date.today())
      with col4:
        expiry_date = st.date_input(
            "有效期限", datetime.date.today() + datetime.timedelta(days=30)
        )
      with col5:
        status = st.selectbox("目前狀態", ["未開封", "已開封", "已用完"])

      submitted = st.form_submit_button("確認入庫")

      if submitted:
        cat_id = cat_df[cat_df["name"] == selected_catalog_name]["id"].values[0]
        use_price = price if price > 0 else original_price
        unit_price = round((use_price / weight) * 100, 2) if weight > 0 else 0.0

        conn = sqlite3.connect("pantry.db")
        c = conn.cursor()
        c.execute(
            """
                    INSERT INTO inventory_batches (
                        catalog_id, channel, weight, current_weight, original_price, price, discount_info, unit_price, purchase_date, expiry_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                cat_id,
                channel,
                weight,
                weight,  # 初始剩餘重量等於總重量
                original_price,
                use_price,
                discount_info,
                unit_price,
                str(purchase_date),
                str(expiry_date),
                status,
            ),
        )
        conn.commit()
        conn.close()
        st.success(f"成功將「{selected_catalog_name}」入庫！實付 NT${use_price}")


# --- 功能三：庫存與批次總覽 ---
elif menu == "📦 庫存與批次總覽":
  st.header("📦 個人食品庫存與效期總覽")

  conn = sqlite3.connect("pantry.db")
  query = """
        SELECT 
            b.id as batch_id,
            COALESCE(c.name, '未知商品') as name,
            COALESCE(c.brand, '') as brand,
            COALESCE(c.category, '其他') as category,
            b.channel as channel,
            b.price as price,
            b.discount_info as discount_info,
            b.weight as weight,
            b.current_weight as current_weight,
            b.unit_price as unit_price,
            b.purchase_date as purchase_date,
            COALESCE(c.sugar, 0) as sugar,
            COALESCE(c.calories, 0) as calories,
            b.expiry_date as expiry_date,
            b.status as status
        FROM inventory_batches b
        LEFT JOIN food_catalog c ON b.catalog_id = c.id
    """
  df = pd.read_sql_query(query, conn)
  conn.close()

  if df.empty:
    st.info("目前庫存沒有任何批次資料！")
  else:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 篩選條件")
    all_cats_in_db = df["category"].unique()
    selected_category = st.sidebar.multiselect(
        "依分類篩選", all_cats_in_db, default=all_cats_in_db
    )
    selected_status = st.sidebar.multiselect(
        "依狀態篩選", df["status"].unique(), default=df["status"].unique()
    )

    filtered_df = df[
        df["category"].isin(selected_category)
        & df["status"].isin(selected_status)
    ]

    if not filtered_df.empty:
      filtered_df["效期狀態"] = filtered_df["expiry_date"].apply(check_expiry)

      st.dataframe(
          filtered_df[[
              "name",
              "brand",
              "category",
              "channel",
              "price",
              "discount_info",
              "weight",
              "current_weight",
              "unit_price",
              "purchase_date",
              "expiry_date",
              "效期狀態",
              "status",
          ]],
          use_container_width=True,
          column_config={
              "name": "食品名稱",
              "brand": "品牌",
              "category": "分類",
              "channel": "購買管道",
              "price": "實付金額",
              "discount_info": "優惠備註",
              "weight": "總量",
              "current_weight": "剩餘重量",
              "unit_price": "每100g實價",
              "purchase_date": "購買日期",
              "expiry_date": "效期",
              "效期狀態": "效期預警",
              "status": "狀態",
          },
      )

      st.markdown("---")
      st.subheader("🗑️ 管理與刪除批次庫存")
      del_id = st.selectbox(
          "選擇要刪除的批次 ID",
          options=filtered_df["batch_id"],
          format_func=lambda x: f"批次 ID: {x} - {filtered_df[filtered_df['batch_id'] == x]['name'].values[0]} ({filtered_df[filtered_df['batch_id'] == x]['purchase_date'].values[0]})",
      )
      if st.button("刪除選定批次"):
        conn = sqlite3.connect("pantry.db")
        c = conn.cursor()
        c.execute("DELETE FROM inventory_batches WHERE id = ?", (del_id,))
        conn.commit()
        conn.close()
        st.success("已成功刪除該批次紀錄！")
        st.rerun()
    else:
      st.warning("沒有符合篩選條件的庫存。")


# --- 功能四：菜單管理、精準烹飪扣庫存與冰箱推薦 ---
elif menu == "📋 菜單、烹飪與冰箱推薦":
  st.header("📋 智慧菜單、精準烹飪扣庫存與冰箱推薦")

  conn = sqlite3.connect("pantry.db")
  cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
  inv_query = """
        SELECT DISTINCT c.name 
        FROM inventory_batches b 
        JOIN food_catalog c ON b.catalog_id = c.id 
        WHERE b.status != '已用完'
    """
  available_inv = pd.read_sql_query(inv_query, conn)["name"].tolist()
  conn.close()

  tab1, tab2, tab3 = st.tabs([
      "📖 現有菜單與精準烹飪扣庫存",
      "✨ 新增菜單與份量設定",
      "🍳 冰箱食材智能推薦",
  ])

  with tab2:
    st.subheader("建立新菜單（勾選主檔食材並設定使用份量）")
    with st.form("add_recipe_form", clear_on_submit=True):
      recipe_title = st.text_input("菜名 (例如：蒜香清炒義大利麵)")
      st.markdown("---")
      st.markdown("**選擇食材並輸入本次烹飪使用的份量 (g 或 ml)：**")

      ingredient_inputs = []
      if cat_df.empty:
        st.info("目前主檔沒有可用食材！")
      else:
        for idx, row in cat_df.iterrows():
          col_a, col_b = st.columns([2, 1])
          with col_a:
            use_it = st.checkbox(
                f"{row['name']} (熱量: {row['calories']}大卡/100g)",
                key=f"chk_cat_{row['id']}",
            )
          with col_b:
            amt = st.number_input(
                "使用量(g/ml)",
                min_value=0.0,
                step=10.0,
                value=100.0,
                key=f"amt_cat_{row['id']}",
            )

          if use_it:
            ingredient_inputs.append(f"{row['name']}:{amt}")

      recipe_instructions = st.text_area("烹飪步驟")
      recipe_submitted = st.form_submit_button("儲存菜單")

      if recipe_submitted:
        if not recipe_title:
          st.error("請填寫菜名！")
        else:
          linked_str = ",".join(ingredient_inputs) if ingredient_inputs else ""
          conn = sqlite3.connect("pantry.db")
          c = conn.cursor()
          c.execute(
              """
                        INSERT INTO recipes (title, ingredients_detail, instructions)
                        VALUES (?, ?, ?)
                    """,
              (recipe_title, linked_str, recipe_instructions),
          )
          conn.commit()
          conn.close()
          st.success(f"成功新增菜單：「{recipe_title}」！")
          st.rerun()

  with tab1:
    conn = sqlite3.connect("pantry.db")
    recipes_df = pd.read_sql_query("SELECT * FROM recipes", conn)
    full_cat_df = pd.read_sql_query("SELECT id, name, calories FROM food_catalog", conn)
    conn.close()

    if recipes_df.empty:
      st.info("目前還沒有建立任何菜單！")
    else:
      for index, row in recipes_df.iterrows():
        with st.expander(f"🍳 {row['title']} (編號: {row['id']})"):
          ingredients_detail = row["ingredients_detail"]
          total_recipe_calories = 0.0
          recipe_items_parsed = []

          if ingredients_detail:
            st.markdown("**🛒 食材明細與熱量計算：**")
            items = ingredients_detail.split(",")
            for item in items:
              if ":" in item:
                fname, famt_str = item.split(":")
                famt = float(famt_str)
                
                match = full_cat_df[full_cat_df["name"] == fname]
                if not match.empty:
                  cid = match["id"].values[0]
                  cal_per_100 = match["calories"].values[0]
                  item_cal = (cal_per_100 / 100.0) * famt
                  total_recipe_calories += item_cal
                  recipe_items_parsed.append((fname, famt, cid))
                  st.markdown(f"- **{fname}**: 使用 {famt}g/ml → 熱量 **{item_cal:.1f} 大卡**")
                else:
                  st.markdown(f"- {fname}: {famt}g/ml (主檔無此資料)")

            st.info(f"🔥 **這道菜的總熱量估算：** `{total_recipe_calories:.1f} 大卡`")
          else:
            st.markdown("**🛒 食材：** 未設定明細與份量")

          st.markdown(f"**烹飪步驟：**\n{row['instructions']}")

          col_btn1, col_btn2 = st.columns(2)
          with col_btn1:
            if st.button("🔥 開始烹飪 (依克數精準扣除庫存)", key=f"cook_{row['id']}"):
              conn = sqlite3.connect("pantry.db")
              c = conn.cursor()
              
              success_msgs = []
              for fname, need_amt, cid in recipe_items_parsed:
                remaining_to_deduct = need_amt
                
                c.execute("""
                    SELECT id, current_weight FROM inventory_batches 
                    WHERE catalog_id = ? AND status != '已用完' 
                    ORDER BY expiry_date ASC
                """, (cid,))
                batches = c.fetchall()
                
                for b_id, cur_w in batches:
                  if remaining_to_deduct <= 0:
                    break
                  if cur_w is None:
                    cur_w = 0.0
                    
                  if cur_w > remaining_to_deduct:
                    new_w = cur_w - remaining_to_deduct
                    c.execute("""
                        UPDATE inventory_batches 
                        SET current_weight = ?, status = '已開封' 
                        WHERE id = ?
                    """, (new_w, b_id))
                    remaining_to_deduct = 0.0
                  else:
                    remaining_to_deduct -= cur_w
                    c.execute("""
                        UPDATE inventory_batches 
                        SET current_weight = 0.0, status = '已用完' 
                        WHERE id = ?
                    """, (b_id,))
                
                if remaining_to_deduct > 0:
                  success_msgs.append(f"⚠️ {fname} 庫存不足，尚缺 {remaining_to_deduct}g/ml")
                else:
                  success_msgs.append(f"✅ {fname} 已扣除 {need_amt}g/ml")

              conn.commit()
              conn.close()
              
              st.success(f"已完成烹飪「{row['title']}」！\n" + "\n".join(success_msgs))
              st.rerun()

          with col_btn2:
            if st.button("刪除此菜單", key=f"del_recipe_{row['id']}"):
              conn = sqlite3.connect("pantry.db")
              c = conn.cursor()
              c.execute("DELETE FROM recipes WHERE id = ?", (row["id"],))
              conn.commit()
              conn.close()
              st.success(f"已刪除菜單：{row['title']}")
              st.rerun()

  with tab3:
    st.subheader("🍳 冰箱食材智能推薦")
    st.markdown("系統會自動檢查你目前冰箱裡**有哪些庫存**，並比對菜單，告訴你今天可以煮什麼！")

    conn = sqlite3.connect("pantry.db")
    recipes_df = pd.read_sql_query("SELECT * FROM recipes", conn)
    conn.close()

    if recipes_df.empty:
      st.info("請先建立菜單！")
    else:
      recommended_count = 0
      for idx, row in recipes_df.iterrows():
        ingredients_detail = row["ingredients_detail"]
        if ingredients_detail:
          items = ingredients_detail.split(",")
          recipe_ings = []
          for item in items:
            if ":" in item:
              recipe_ings.append(item.split(":")[0])

          have_all = all(ing in available_inv for ing in recipe_ings)
          have_partial = any(ing in available_inv for ing in recipe_ings)

          if have_all and recipe_ings:
            recommended_count += 1
            st.success(
                f"🟢 **【完美符合】{row['title']}** -> 冰箱食材全部齊全！趕快動手做吧！"
            )
            st.markdown(f"所需食材：{', '.join(recipe_ings)}")
            st.markdown("---")
          elif have_partial and recipe_ings:
            st.info(
                f"🟡 **【部分符合】{row['title']}** -> 冰箱擁有部分食材（缺少部分）。"
            )
            st.markdown(f"所需食材：{', '.join(recipe_ings)}")
            st.markdown("---")

      if recommended_count == 0:
        st.warning("目前冰箱現有庫存對應不到完整可以做的菜單，建議補貨！")


# --- 功能五：支出分析、預算與比價 ---
elif menu == "🛒 支出分析、預算與比價":
  st.header("🛒 智慧購物、預算控管與跨通路比價")

  conn = sqlite3.connect("pantry.db")
  query = """
        SELECT 
            b.id as batch_id,
            COALESCE(c.name, '未知商品') as name,
            COALESCE(c.category, '其他') as category,
            b.channel as channel,
            b.price as price,
            b.unit_price as unit_price,
            b.purchase_date as purchase_date,
            b.expiry_date as expiry_date,
            b.status as status
        FROM inventory_batches b
        LEFT JOIN food_catalog c ON b.catalog_id = c.id
    """
  df = pd.read_sql_query(query, conn)
  conn.close()

  if df.empty:
    st.info("目前沒有資料。")
  else:
    st.subheader("🎯 每月伙食/食品預算設定")
    current_month_str = datetime.date.today().strftime("%Y-%m")
    default_budget = float(get_setting("monthly_budget", "5000"))

    col_b1, col_b2 = st.columns(2)
    with col_b1:
      user_budget = st.number_input(
          "設定每月食品支出預算 (元)",
          min_value=0.0,
          step=500.0,
          value=default_budget,
      )
      if st.button("儲存預算設定"):
        set_setting("monthly_budget", user_budget)
        st.success(f"成功將每月預算設定為 NT$ {user_budget}")
        st.rerun()

    df["purchase_date_dt"] = pd.to_datetime(df["purchase_date"], errors="coerce")
    df["月份"] = df["purchase_date_dt"].dt.strftime("%Y-%m")

    current_month_df = df[df["月份"] == current_month_str]
    month_spent = current_month_df["price"].sum()

    with col_b2:
      st.markdown(f"**本月 ({current_month_str}) 預算狀況：**")
      if user_budget > 0:
        pct = month_spent / user_budget
        st.progress(min(pct, 1.0))
        if pct > 1.0:
          st.error(
              f"🔴 本月已超支！花費 NT$ {month_spent:.1f} / 預算 NT$ {user_budget}"
          )
        elif pct >= 0.8:
          st.warning(
              f"🟡 本月即將接近預算上限！花費 NT$ {month_spent:.1f}"
          )
        else:
          st.success(
              f"🟢 預算控制良好！花費 NT$ {month_spent:.1f} (佔 {pct*100:.1f}%)"
          )
      else:
        st.info("尚未設定預算金額。")

    st.markdown("---")
    st.subheader("📊 採購支出與月度分析")
    col_stat1, col_stat2 = st.columns(2)
    total_spent = df["price"].sum()
    with col_stat1:
      st.metric(label="累計食品總支出", value=f"NT$ {total_spent:.1f}")
    with col_stat2:
      channel_spend = df.groupby("channel")["price"].sum()
      st.markdown("**各購買管道花費：**")
      st.dataframe(channel_spend, use_container_width=True)

    st.markdown("---")
    st.subheader("📅 每月支出統計")
    if not df["月份"].dropna().empty:
      monthly_spend = df.groupby("月份")["price"].sum().reset_index()
      monthly_spend.columns = ["月份", "總花費 (元)"]
      st.dataframe(monthly_spend, use_container_width=True)

    st.markdown("---")
    st.subheader("💡 跨通路歷史比價分析 (哪裡買最便宜？)")
    conn = sqlite3.connect("pantry.db")
    comp_query = """
        SELECT c.name as 商品名稱, b.channel as 購買管道, AVG(b.unit_price) as 平均每100g實價
        FROM inventory_batches b
        JOIN food_catalog c ON b.catalog_id = c.id
        GROUP BY c.name, b.channel
    """
    comp_df = pd.read_sql_query(comp_query, conn)
    conn.close()

    if not comp_df.empty:
      st.dataframe(comp_df, use_container_width=True)
    else:
      st.info("尚無足夠的歷史比價資料。")

    st.markdown("---")
    st.subheader("📥 資料備份與匯出")
    csv_data = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 下載完整庫存與支出資料 (CSV 備份)",
        data=csv_data,
        file_name=f"pantry_backup_{datetime.date.today()}.csv",
        mime="text/csv",
    )