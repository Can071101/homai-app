"""
好麦出货系统 v3.0 (Flet 版)
功能：产品管理、出货/调出/调入/剩货单、拼音搜索、单据查询编辑、汇总提成、打印
支持：Windows / macOS / Linux / Android (flet build apk)
"""
import flet as ft
import db_manager as db
from pinyin_util import match_product
from print_utils import print_shipment, print_summary
from datetime import date, datetime

# ==================== 全局状态 ====================
STATE = {
    "products": [],          # 产品列表
    "selected_product": None, # 当前选中的产品 dict
    "edit_mode": None,       # 'shipment'/'transfer_out'/'transfer_in'/'inventory'
    "edit_id": None,         # 编辑中的单据ID
}

# ==================== 工具函数 ====================

def today_str():
    return date.today().isoformat()

def show_snack(page, msg, color=ft.Colors.GREEN):
    page.snack_bar = ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color)
    page.snack_bar.open = True
    page.update()

def get_product_by_id(pid):
    return next((p for p in STATE["products"] if p["id"] == pid), None)

def refresh_products():
    STATE["products"] = db.get_products()

# ==================== 产品搜索控件 ====================

def build_product_selector(page, on_select=None) -> tuple[ft.Column, ft.TextField, ft.ListView]:
    """构建一个产品搜索+选择控件组"""
    search_input = ft.TextField(
        label="🔍 输入拼音首字母或产品名搜索",
        expand=True,
        on_change=lambda e: _filter_products(e, search_input, product_list),
        hint_text="如: qm=全麦, hz=黑芝麻, ds=德式",
    )
    product_list = ft.ListView(height=180, spacing=2, divider=True)

    def _on_click(p):
        STATE["selected_product"] = p
        search_input.value = f"✅ {p['name']} ¥{p['price']:.0f}"
        page.update()
        if on_select: on_select(p)

    def _populate():
        product_list.controls.clear()
        q = (search_input.value or "").replace("✅ ","").strip()
        for p in STATE["products"]:
            if match_product(q, p["name"]):
                is_sel = STATE["selected_product"] and STATE["selected_product"]["id"] == p["id"]
                product_list.controls.append(
                    ft.ListTile(
                        title=ft.Text(p["name"]),
                        subtitle=ft.Text(f"¥{p['price']:.2f}"),
                        trailing=ft.Text("✓", color=ft.Colors.GREEN) if is_sel else None,
                        bgcolor=ft.Colors.BLUE_50 if is_sel else None,
                        on_click=lambda e, p=p: _on_click(p),
                    )
                )
        page.update()

    search_input.on_change = lambda e: _populate()
    # 初始填充
    def _init():
        _populate
        pass

    container = ft.Column([search_input, ft.Text("点击选择产品:", size=12, color=ft.Colors.GREY), product_list])
    return container, search_input, product_list

def _filter_products(e, search_input, product_list):
    q = search_input.value.strip() if search_input.value else ""
    product_list.controls.clear()
    for p in STATE["products"]:
        if match_product(q, p["name"]):
            product_list.controls.append(
                ft.ListTile(
                    title=ft.Text(p["name"]),
                    subtitle=ft.Text(f"¥{p['price']:.2f}"),
                    on_click=lambda e, p=p: _select_and_refresh(p, search_input, product_list),
                )
            )
    e.page.update()

def _select_and_refresh(p, search_input, product_list):
    STATE["selected_product"] = p
    search_input.value = f"✅ {p['name']} ¥{p['price']:.0f}"
    product_list.controls.clear()
    product_list.controls.append(
        ft.ListTile(title=ft.Text(p["name"], weight="bold"), subtitle=ft.Text(f"¥{p['price']:.2f}"), bgcolor=ft.Colors.BLUE_50)
    )
    for ctrl in (search_input.page or []):
        pass
    # 找到 page 并 update
    # search_input 在 page 的控件树中
    if hasattr(search_input, 'page') and search_input.page:
        search_input.page.update()
    elif hasattr(product_list, 'page') and product_list.page:
        product_list.page.update()

# ==================== 明细表格 ====================

def make_items_table() -> ft.DataTable:
    return ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("产品名称", weight="bold")),
            ft.DataColumn(ft.Text("数量", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("单价", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("小计", weight="bold"), numeric=True),
        ],
        rows=[],
    )

def refresh_items_table(table: ft.DataTable, items: list[dict], page: ft.Page):
    table.rows.clear()
    for i, it in enumerate(items):
        table.rows.append(ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(it["name"])),
                ft.DataCell(ft.Text(str(it["qty"]))),
                ft.DataCell(ft.Text(f"¥{it['price']:.2f}")),
                ft.DataCell(ft.Text(f"¥{it['qty']*it['price']:.2f}", weight="bold")),
            ],
            on_select_changed=lambda e, idx=i: _on_row_select(e, idx, page),
        ))
    table.show_checkbox_column = True
    page.update()

_selected_row_index = {"val": None}

def _on_row_select(e, idx, page):
    _selected_row_index["val"] = idx
    page.update()

def get_selected_item(items: list) -> dict | None:
    idx = _selected_row_index.get("val")
    if idx is not None and 0 <= idx < len(items):
        return items[idx]
    return None

# ==================== 通用：添加明细 ====================

def build_add_row(page, items: list, table: ft.DataTable, qty_input: ft.TextField):
    """返回一个 Row 控件，包含搜索+数量+添加按钮"""
    search_input = ft.TextField(label="🔍 搜索产品（拼音/名称）", expand=True, on_change=lambda e: _filter_and_select(e, search_input, product_list, page))
    product_list = ft.ListView(height=150, spacing=2)
    qty_input = qty_input or ft.TextField(label="数量", value="1", width=80)

    def add_clicked(e):
        p = STATE["selected_product"]
        if not p:
            show_snack(page, "请先选择产品", ft.Colors.ORANGE)
            return
        try:
            q = int(qty_input.value or 0)
        except:
            show_snack(page, "数量必须是整数", ft.Colors.RED)
            return
        if q <= 0:
            show_snack(page, "数量必须大于0", ft.Colors.RED)
            return
        # 如果已存在则合并数量
        for it in items:
            if it["product_id"] == p["id"]:
                it["qty"] += q
                refresh_items_table(table, items, page)
                show_snack(page, f"已更新 {p['name']} 数量 +{q}")
                return
        items.append({"product_id": p["id"], "name": p["name"], "price": p["price"], "qty": q})
        refresh_items_table(table, items, page)
        show_snack(page, f"已添加 {p['name']} × {q}")
        # 重置选择
        STATE["selected_product"] = None
        search_input.value = ""
        qty_input.value = "1"
        product_list.controls.clear()
        page.update()

    def _filter_and_select(e, si, pl, pg):
        q = si.value.strip() if si.value else ""
        pl.controls.clear()
        for p in STATE["products"]:
            if match_product(q, p["name"]):
                pl.controls.append(
                    ft.ListTile(
                        title=ft.Text(p["name"]),
                        subtitle=ft.Text(f"¥{p['price']:.2f}"),
                        on_click=lambda ev, p=p: _pick_product(p, si, pl, pg),
                    )
                )
        pg.update()

    def _pick_product(p, si, pl, pg):
        STATE["selected_product"] = p
        si.value = f"✅ {p['name']}"
        pl.controls.clear()
        pl.controls.append(ft.ListTile(title=ft.Text(p["name"], weight="bold"), subtitle=ft.Text(f"¥{p['price']:.2f}"), bgcolor=ft.Colors.BLUE_50))
        pg.update()

    return ft.Column([
        ft.Text("➕ 添加明细", size=14, weight="bold"),
        ft.Row([search_input, qty_input, ft.ElevatedButton("添加到明细", on_click=add_clicked, icon=ft.Icons.ADD)]),
        pl_ref(product_list),
    ])

def pl_ref(pl):
    return ft.Container(content=pl, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5, padding=5)

# ==================== 页面：产品管理 ====================

def page_products(page: ft.Page) -> ft.View:
    refresh_products()
    name_in = ft.TextField(label="产品名称", expand=True)
    price_in = ft.TextField(label="单价 (¥)", width=120)
    list_view = ft.ListView(height=300, spacing=2, divider=True)

    def reload():
        list_view.controls.clear()
        for p in STATE["products"]:
            list_view.controls.append(ft.ListTile(
                title=ft.Text(p["name"]),
                trailing=ft.Text(f"¥{p['price']:.2f}", weight="bold"),
                leading=ft.Icon(ft.Icons.BAKERY_DINING, color=ft.Colors.AMBER),
            ))
        page.update()

    def add_prod(e):
        n = name_in.value.strip()
        try: p = float(price_in.value or 0)
        except: show_snack(page, "价格必须是数字", ft.Colors.RED); return
        if not n or p <= 0: show_snack(page, "请填写有效名称和价格", ft.Colors.ORANGE); return
        if db.add_product(n, p):
            show_snack(page, f"✅ 已添加: {n}")
            name_in.value = ""; price_in.value = ""
            refresh_products(); reload()
        else:
            show_snack(page, f"❌ 产品「{n}」已存在", ft.Colors.RED)

    reload()
    return ft.View(
        route="/products",
        appbar=ft.AppBar(title=ft.Text("📦 产品管理"), bgcolor=ft.Colors.BLUE_700, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=15, content=ft.Column([
                ft.Text("新增产品", size=16, weight="bold"),
                ft.Row([name_in, price_in, ft.ElevatedButton("➕ 添加", on_click=add_prod, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)]),
            ]))),
            ft.Divider(),
            ft.Text(f"已有产品 ({len(STATE['products'])} 个)", size=14, weight="bold"),
            list_view,
        ],
        floating_action_button=ft.FloatingActionButton(icon=ft.Icons.REFRESH, tooltip="刷新", on_click=lambda e: [refresh_products(), reload()]),
    )

# ==================== 页面：出货单 ====================

def page_shipment(page: ft.Page) -> ft.View:
    refresh_products()
    items: list[dict] = []
    STATE["edit_mode"] = None
    STATE["edit_id"] = None
    _selected_row_index["val"] = None

    # 表单
    order_no = ft.TextField(label="单号", value=db.gen_order_no(), width=200)
    customer = ft.TextField(label="客户 *", expand=True, hint_text="必填")
    date_in = ft.TextField(label="日期", value=today_str(), width=150)
    remark = ft.TextField(label="备注", expand=True)

    table = make_items_table()
    qty_in = ft.TextField(label="数量", value="1", width=80)

    def _build_selector():
        return build_add_row(page, items, table, qty_in)

    add_row_ctrl = _build_selector()

    def _rebuild_add_row():
        nonlocal add_row_ctrl
        add_row_ctrl = _build_selector()
        return add_row_ctrl

    def edit_qty(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请先选中要修改的行", ft.Colors.ORANGE); return
        dlg_qty = ft.TextField(label="新数量", value=str(it["qty"]), width=100)
        def ok(e):
            try: q = int(dlg_qty.value or 0)
            except: show_snack(page, "必须是整数", ft.Colors.RED); return
            if q <= 0: show_snack(page, "数量>0", ft.Colors.RED); return
            it["qty"] = q
            refresh_items_table(table, items, page)
            dlg.open = False; page.update()
            show_snack(page, "✅ 数量已更新")
        page.dialog = ft.AlertDialog(title=ft.Text(f"修改数量 - {it['name']}"), content=dlg_qty, actions=[ft.TextButton("取消", on_click=lambda e: setattr(dlg,'open',False) or page.update()), ft.TextButton("确定", on_click=ok)])
        page.dialog.open = True; page.update()

    def del_row(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请先选中要删除的行", ft.Colors.ORANGE); return
        items.remove(it)
        _selected_row_index["val"] = None
        refresh_items_table(table, items, page)
        show_snack(page, f"🗑️ 已删除: {it['name']}")

    def clear_all(e):
        items.clear()
        _selected_row_index["val"] = None
        refresh_items_table(table, items, page)

    def save(e):
        cust = customer.value.strip()
        if not cust: show_snack(page, "❌ 客户不能为空", ft.Colors.RED); return
        if not items: show_snack(page, "❌ 请至少添加一项明细", ft.Colors.RED); return
        item_tuples = [(it["product_id"], it["qty"]) for it in items]
        if STATE["edit_mode"] == "shipment":
            db.update_shipment(STATE["edit_id"], order_no.value, cust, date_in.value, remark.value, item_tuples)
            show_snack(page, "✅ 出货单修改成功")
        else:
            sid = db.create_shipment(order_no.value, cust, date_in.value, remark.value, item_tuples)
            show_snack(page, f"✅ 出货单保存成功 (ID:{sid})")
        # 重置
        items.clear()
        order_no.value = db.gen_order_no()
        customer.value = ""; remark.value = ""
        STATE["edit_mode"] = None; STATE["edit_id"] = None
        refresh_items_table(table, items, page)
        page.update()

    def print_doc(e):
        if not items: show_snack(page, "没有可打印的内容", ft.Colors.ORANGE); return
        ship = {"order_no": order_no.value, "customer": customer.value, "ship_date": date_in.value, "remark": remark.value}
        print_shipment(ship, items)
        show_snack(page, "🖨️ 已生成打印页")

    # 组装
    return ft.View(
        route="/shipment",
        appbar=ft.AppBar(title=ft.Text("📋 出货单"), bgcolor=ft.Colors.INDIGO, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("出货单信息", size=16, weight="bold"),
                ft.Row([order_no, customer]),
                ft.Row([date_in, remark]),
            ]))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                add_row_ctrl,
            ]))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("出货明细 (点击行选中后，可修改/删除)", size=14, weight="bold"),
                ft.Container(content=table, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5),
                ft.Row([
                    ft.ElevatedButton("✏️ 修改数量", on_click=edit_qty, bgcolor=ft.Colors.AMBER),
                    ft.ElevatedButton("🗑️ 删除选中", on_click=del_row, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
                    ft.ElevatedButton("🧹 清空全部", on_click=clear_all),
                ]),
            ]))),
            ft.Row([
                ft.ElevatedButton("💾 保存出货单", on_click=save, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, icon=ft.Icons.SAVE),
                ft.ElevatedButton("🖨️ 打印", on_click=print_doc, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
            ]),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 页面：调出单 ====================

def page_transfer_out(page: ft.Page) -> ft.View:
    refresh_products()
    items: list[dict] = []
    STATE["edit_mode"] = None; STATE["edit_id"] = None
    _selected_row_index["val"] = None

    dest = ft.TextField(label="调出至 (目的地) *", expand=True, hint_text="必填")
    date_in = ft.TextField(label="日期", value=today_str(), width=150)
    remark = ft.TextField(label="备注", expand=True)
    table = make_items_table()
    qty_in = ft.TextField(label="数量", value="1", width=80)

    def save(e):
        d = dest.value.strip()
        if not d: show_snack(page, "❌ 目的地不能为空", ft.Colors.RED); return
        if not items: show_snack(page, "❌ 请添加明细", ft.Colors.RED); return
        item_tuples = [(it["product_id"], it["qty"]) for it in items]
        if STATE["edit_mode"] == "transfer_out":
            db.update_transfer_out(STATE["edit_id"], d, date_in.value, remark.value, item_tuples)
            show_snack(page, "✅ 调出单修改成功")
        else:
            tid = db.create_transfer_out(d, date_in.value, remark.value, item_tuples)
            show_snack(page, f"✅ 调出单保存成功 (ID:{tid})")
        items.clear(); dest.value=""; remark.value=""
        STATE["edit_mode"]=None; STATE["edit_id"]=None
        refresh_items_table(table, items, page); page.update()

    def edit_qty(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        dlg = ft.TextField(label="新数量", value=str(it["qty"]))
        def ok(e):
            it["qty"] = int(dlg.value or 0)
            refresh_items_table(table, items, page)
            page.dialog.open = False; page.update()
        page.dialog = ft.AlertDialog(title=ft.Text(f"修改 - {it['name']}"), content=dlg, actions=[ft.TextButton("确定", on_click=ok)])
        page.dialog.open = True; page.update()

    def del_row(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        items.remove(it); _selected_row_index["val"]=None
        refresh_items_table(table, items, page)

    return ft.View(
        route="/transfer_out",
        appbar=ft.AppBar(title=ft.Text("🚚 调出单"), bgcolor=ft.Colors.ORANGE, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("调出单信息", size=16, weight="bold"),
                ft.Row([dest, date_in]),
                ft.Row([remark]),
            ]))),
            ft.Card(content=ft.Container(padding=12, content=build_add_row(page, items, table, qty_in))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("调出明细", size=14, weight="bold"),
                ft.Container(content=table, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5),
                ft.Row([
                    ft.ElevatedButton("✏️ 修改", on_click=edit_qty, bgcolor=ft.Colors.AMBER),
                    ft.ElevatedButton("🗑️ 删除", on_click=del_row, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
                ]),
            ]))),
            ft.ElevatedButton("💾 保存调出单", on_click=save, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, icon=ft.Icons.SAVE),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 页面：调入单 ====================

def page_transfer_in(page: ft.Page) -> ft.View:
    refresh_products()
    items: list[dict] = []
    STATE["edit_mode"] = None; STATE["edit_id"] = None
    _selected_row_index["val"] = None

    src = ft.TextField(label="调入自 (来源) *", expand=True, hint_text="必填")
    date_in = ft.TextField(label="日期", value=today_str(), width=150)
    remark = ft.TextField(label="备注", expand=True)
    table = make_items_table()
    qty_in = ft.TextField(label="数量", value="1", width=80)

    def save(e):
        s = src.value.strip()
        if not s: show_snack(page, "❌ 来源不能为空", ft.Colors.RED); return
        if not items: show_snack(page, "❌ 请添加明细", ft.Colors.RED); return
        item_tuples = [(it["product_id"], it["qty"]) for it in items]
        if STATE["edit_mode"] == "transfer_in":
            db.update_transfer_in(STATE["edit_id"], s, date_in.value, remark.value, item_tuples)
            show_snack(page, "✅ 调入单修改成功")
        else:
            tid = db.create_transfer_in(s, date_in.value, remark.value, item_tuples)
            show_snack(page, f"✅ 调入单保存成功 (ID:{tid})")
        items.clear(); src.value=""; remark.value=""
        STATE["edit_mode"]=None; STATE["edit_id"]=None
        refresh_items_table(table, items, page); page.update()

    def edit_qty(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        dlg = ft.TextField(label="新数量", value=str(it["qty"]))
        def ok(e):
            it["qty"] = int(dlg.value or 0)
            refresh_items_table(table, items, page)
            page.dialog.open = False; page.update()
        page.dialog = ft.AlertDialog(title=ft.Text(f"修改 - {it['name']}"), content=dlg, actions=[ft.TextButton("确定", on_click=ok)])
        page.dialog.open = True; page.update()

    def del_row(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        items.remove(it); _selected_row_index["val"]=None
        refresh_items_table(table, items, page)

    return ft.View(
        route="/transfer_in",
        appbar=ft.AppBar(title=ft.Text("📥 调入单"), bgcolor=ft.Colors.TEAL, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("调入单信息", size=16, weight="bold"),
                ft.Row([src, date_in]),
                ft.Row([remark]),
            ]))),
            ft.Card(content=ft.Container(padding=12, content=build_add_row(page, items, table, qty_in))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("调入明细", size=14, weight="bold"),
                ft.Container(content=table, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5),
                ft.Row([
                    ft.ElevatedButton("✏️ 修改", on_click=edit_qty, bgcolor=ft.Colors.AMBER),
                    ft.ElevatedButton("🗑️ 删除", on_click=del_row, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
                ]),
            ]))),
            ft.ElevatedButton("💾 保存调入单", on_click=save, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, icon=ft.Icons.SAVE),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 页面：剩货单 ====================

def page_inventory(page: ft.Page) -> ft.View:
    refresh_products()
    items: list[dict] = []
    STATE["edit_mode"] = None; STATE["edit_id"] = None
    _selected_row_index["val"] = None

    date_in = ft.TextField(label="日期", value=today_str(), width=150)
    remark = ft.TextField(label="备注", expand=True)
    table = make_items_table()
    qty_in = ft.TextField(label="数量", value="1", width=80)

    def save(e):
        if not items: show_snack(page, "❌ 请添加明细", ft.Colors.RED); return
        item_tuples = [(it["product_id"], it["qty"]) for it in items]
        if STATE["edit_mode"] == "inventory":
            db.update_inventory(STATE["edit_id"], date_in.value, remark.value, item_tuples)
            show_snack(page, "✅ 剩货单修改成功")
        else:
            iid = db.create_inventory(date_in.value, remark.value, item_tuples)
            show_snack(page, f"✅ 剩货单保存成功 (ID:{iid})")
        items.clear(); remark.value=""
        STATE["edit_mode"]=None; STATE["edit_id"]=None
        refresh_items_table(table, items, page); page.update()

    def edit_qty(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        dlg = ft.TextField(label="新数量", value=str(it["qty"]))
        def ok(e):
            it["qty"] = int(dlg.value or 0)
            refresh_items_table(table, items, page)
            page.dialog.open = False; page.update()
        page.dialog = ft.AlertDialog(title=ft.Text(f"修改 - {it['name']}"), content=dlg, actions=[ft.TextButton("确定", on_click=ok)])
        page.dialog.open = True; page.update()

    def del_row(e):
        it = get_selected_item(items)
        if not it: show_snack(page, "请选中行", ft.Colors.ORANGE); return
        items.remove(it); _selected_row_index["val"]=None
        refresh_items_table(table, items, page)

    return ft.View(
        route="/inventory",
        appbar=ft.AppBar(title=ft.Text("📦 剩货单"), bgcolor=ft.Colors.BROWN, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("剩货记录", size=16, weight="bold"),
                ft.Row([date_in, remark]),
                ft.Text("💡 剩货只做盘点参考，不参与销售金额计算", size=12, color=ft.Colors.GREY),
            ]))),
            ft.Card(content=ft.Container(padding=12, content=build_add_row(page, items, table, qty_in))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("剩货明细", size=14, weight="bold"),
                ft.Container(content=table, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5),
                ft.Row([
                    ft.ElevatedButton("✏️ 修改", on_click=edit_qty, bgcolor=ft.Colors.AMBER),
                    ft.ElevatedButton("🗑️ 删除", on_click=del_row, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
                ]),
            ]))),
            ft.ElevatedButton("💾 保存剩货单", on_click=save, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, icon=ft.Icons.SAVE),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 页面：当日销售汇总 ====================

def page_summary(page: ft.Page) -> ft.View:
    date_in = ft.TextField(label="汇总日期", value=today_str(), width=150)
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("产品名称", weight="bold")),
            ft.DataColumn(ft.Text("出货", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("调出", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("调入", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("剩货", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("实际销售", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("单价", weight="bold"), numeric=True),
            ft.DataColumn(ft.Text("销售金额", weight="bold"), numeric=True),
        ],
        rows=[],
    )
    total_text = ft.Text("", size=18, weight="bold")
    comm_text = ft.Text("", size=16, color=ft.Colors.RED, weight="bold")
    cust_text = ft.Text("", size=13, color=ft.Colors.BLUE_GREY)
    current_data = {"rows":[], "total":0.0, "comm":0.0, "cust":[]}

    def query(e):
        rows, total, comm, customers = db.get_daily_summary(date_in.value)
        table.rows.clear()
        for r in rows:
            table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(r["name"])),
                ft.DataCell(ft.Text(str(r["ship"]))),
                ft.DataCell(ft.Text(str(r["out"]))),
                ft.DataCell(ft.Text(str(r["in"]))),
                ft.DataCell(ft.Text(str(r["inv"]))),
                ft.DataCell(ft.Text(str(r["actual"]), weight="bold")),
                ft.DataCell(ft.Text(f"¥{r['price']:.2f}")),
                ft.DataCell(ft.Text(f"¥{r['amount']:.2f}", weight="bold")),
            ]))
        total_text.value = f"合计销售金额: ¥{total:.2f}"
        comm_text.value = f"提成 (20%): ¥{comm:.2f}"
        cust_text.value = f"客户: {'、'.join(customers)}" if customers else "客户: —"
        current_data["rows"] = rows; current_data["total"] = total
        current_data["comm"] = comm; current_data["cust"] = customers
        page.update()

    def print_sum(e):
        if not current_data["rows"]:
            show_snack(page, "请先查询汇总", ft.Colors.ORANGE); return
        print_summary(date_in.value, current_data["rows"], current_data["total"], current_data["comm"], current_data["cust"])
        show_snack(page, "🖨️ 已生成打印页")

    return ft.View(
        route="/summary",
        appbar=ft.AppBar(title=ft.Text("📊 当日销售汇总"), bgcolor=ft.Colors.PURPLE, center_title=True),
        controls=[
            ft.Row([date_in, ft.ElevatedButton("查询汇总", on_click=query, icon=ft.Icons.SEARCH, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)]),
            ft.Container(content=table, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5, padding=5),
            cust_text,
            total_text,
            comm_text,
            ft.ElevatedButton("🖨️ 打印汇总表", on_click=print_sum, bgcolor=ft.Colors.ORANGE, color=ft.Colors.WHITE),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 页面：单据查询 ====================

def page_query(page: ft.Page) -> ft.View:
    date_in = ft.TextField(label="日期", value=today_str(), width=150)
    type_dd = ft.Dropdown(
        label="单据类型", width=150,
        value="shipment",
        options=[
            ft.dropdown.Option("shipment", "出货单"),
            ft.dropdown.Option("transfer_out", "调出单"),
            ft.dropdown.Option("transfer_in", "调入单"),
            ft.dropdown.Option("inventory", "剩货单"),
        ]
    )
    result_list = ft.ListView(height=350, spacing=3, divider=True)
    selected_doc = {"type": None, "id": None}

    def do_query(e):
        result_list.controls.clear()
        selected_doc["type"] = None; selected_doc["id"] = None
        # 直接查数据库
        d = date_in.value
        results = []
        if type_dd.value == "shipment" or type_dd.value is None:
            for s in db.query_shipments_by_date(d):
                results.append(("shipment", s["id"], f"📋 {s['order_no']} | 客户:{s['customer']} | ¥{s['amount']:.0f}"))
        if type_dd.value == "transfer_out" or type_dd.value is None:
            for t in db.query_transfers_out_by_date(d):
                results.append(("transfer_out", t["id"], f"🚚 TO{t['id']:06d} | 至:{t['destination']}"))
        if type_dd.value == "transfer_in" or type_dd.value is None:
            for t in db.query_transfers_in_by_date(d):
                results.append(("transfer_in", t["id"], f"📥 TI{t['id']:06d} | 自:{t['source']}"))
        if type_dd.value == "inventory" or type_dd.value is None:
            for inv in db.query_inventories_by_date(d):
                results.append(("inventory", inv["id"], f"📦 INV{inv['id']:06d}"))
        if not results:
            result_list.controls.append(ft.ListTile(title=ft.Text("无数据", color=ft.Colors.GREY)))
        for dtype, did, label in results:
            result_list.controls.append(ft.ListTile(
                title=ft.Text(label),
                on_click=lambda e, t=dtype, i=did: _select_doc(t, i, e),
                trailing=ft.Icon(ft.Icons.EDIT, color=ft.Colors.BLUE),
            ))
        page.update()

    def _select_doc(t, i, e):
        selected_doc["type"] = t; selected_doc["id"] = i
        show_snack(page, f"已选中: {t} ID={i}")

    def open_edit(e):
        t, i = selected_doc["type"], selected_doc["id"]
        if not t or not i: show_snack(page, "请先选择一条单据", ft.Colors.ORANGE); return
        if t == "shipment":
            ship, items = db.get_shipment_detail(i)
            if not ship: show_snack(page, "❌ 找不到单据", ft.Colors.RED); return
            STATE["edit_mode"] = "shipment"; STATE["edit_id"] = i
            # 跳转到出货单页面并预填数据
            page.go("/shipment")
            # 用 page.views 的最后一个 view 操作
            # 简单方案：直接把数据存入 STATE，由页面读取
            STATE["_prefill"] = {
                "order_no": ship["order_no"], "customer": ship["customer"],
                "date": ship["ship_date"], "remark": ship.get("remark",""),
                "items": [{"product_id":it["product_id"],"name":it["name"],"price":it["price"],"qty":it["qty"]} for it in items]
            }
            show_snack(page, f"✅ 已加载出货单 {ship['order_no']}，可修改后保存")
            # 触发刷新
            page.update()
        elif t == "transfer_out":
            info, items = db.get_transfer_out_detail(i)
            STATE["edit_mode"] = "transfer_out"; STATE["edit_id"] = i
            STATE["_prefill"] = {"dest": info["destination"], "date": info["date"], "remark": info.get("remark",""),
                                 "items": [{"product_id":it["product_id"],"name":it["name"],"price":it["price"],"qty":it["qty"]} for it in items]}
            page.go("/transfer_out")
            show_snack(page, f"✅ 已加载调出单，可修改后保存")
        elif t == "transfer_in":
            info, items = db.get_transfer_in_detail(i)
            STATE["edit_mode"] = "transfer_in"; STATE["edit_id"] = i
            STATE["_prefill"] = {"src": info["source"], "date": info["date"], "remark": info.get("remark",""),
                                 "items": [{"product_id":it["product_id"],"name":it["name"],"price":it["price"],"qty":it["qty"]} for it in items]}
            page.go("/transfer_in")
            show_snack(page, f"✅ 已加载调入单，可修改后保存")
        elif t == "inventory":
            info, items = db.get_inventory_detail(i)
            STATE["edit_mode"] = "inventory"; STATE["edit_id"] = i
            STATE["_prefill"] = {"date": info["date"], "remark": info.get("remark",""),
                                 "items": [{"product_id":it["product_id"],"name":it["name"],"price":it["price"],"qty":it["qty"]} for it in items]}
            page.go("/inventory")
            show_snack(page, f"✅ 已加载剩货单，可修改后保存")

    def delete_doc(e):
        t, i = selected_doc["type"], selected_doc["id"]
        if not t or not i: show_snack(page, "请先选择一条单据", ft.Colors.ORANGE); return
        if t == "shipment": db.delete_shipment(i)
        elif t == "transfer_out": db.delete_transfer_out(i)
        elif t == "transfer_in": db.delete_transfer_in(i)
        elif t == "inventory": db.delete_inventory(i)
        show_snack(page, f"🗑️ 已删除 {t} ID={i}", ft.Colors.RED)
        do_query(None)

    return ft.View(
        route="/query",
        appbar=ft.AppBar(title=ft.Text("🔍 单据查询"), bgcolor=ft.Colors.CYAN_700, center_title=True),
        controls=[
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("查询条件", size=16, weight="bold"),
                ft.Row([date_in, type_dd, ft.ElevatedButton("🔍 查询", on_click=do_query, bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE)]),
                ft.Text("提示: 选中列表中的单据 → 点下方按钮编辑或删除", size=12, color=ft.Colors.GREY),
            ]))),
            ft.Card(content=ft.Container(padding=12, content=ft.Column([
                ft.Text("查询结果", size=14, weight="bold"),
                result_list,
            ]))),
            ft.Row([
                ft.ElevatedButton("✏️ 打开编辑", on_click=open_edit, bgcolor=ft.Colors.INDIGO, color=ft.Colors.WHITE),
                ft.ElevatedButton("🗑️ 删除", on_click=delete_doc, bgcolor=ft.Colors.RED, color=ft.Colors.WHITE),
            ]),
        ],
        scroll=ft.ScrollMode.AUTO,
    )

# ==================== 主入口 ====================

def main(page: ft.Page):
    page.title = "好麦出货系统"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 420
    page.window_height = 750
    page.window_min_width = 360
    page.window_min_height = 600

    # 导航栏
    def on_nav(e):
        idx = e.control.selected_index
        routes = ["/shipment", "/transfer_out", "/transfer_in", "/inventory", "/summary", "/query", "/products"]
        page.go(routes[idx] if idx < len(routes) else "/shipment")

    page.navigation_bar = ft.NavigationBar(
        selected_index=0,
        on_change=on_nav,
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.DESCRIPTION, label="出货"),
            ft.NavigationBarDestination(icon=ft.Icons.OUTPUT, label="调出"),
            ft.NavigationBarDestination(icon=ft.Icons.INPUT, label="调入"),
            ft.NavigationBarDestination(icon=ft.Icons.INVENTORY_2, label="剩货"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="汇总"),
            ft.NavigationBarDestination(icon=ft.Icons.SEARCH, label="查询"),
            ft.NavigationBarDestination(icon=ft.Icons.BAKERY_DINING, label="产品"),
        ],
    )

    def route_change(e):
        page.views.clear()
        r = page.route or "/shipment"
        if r == "/products": page.views.append(page_products(page))
        elif r == "/shipment": page.views.append(page_shipment(page))
        elif r == "/transfer_out": page.views.append(page_transfer_out(page))
        elif r == "/transfer_in": page.views.append(page_transfer_in(page))
        elif r == "/inventory": page.views.append(page_inventory(page))
        elif r == "/summary": page.views.append(page_summary(page))
        elif r == "/query": page.views.append(page_query(page))
        else: page.views.append(page_shipment(page))
        page.update()

    page.on_route_change = route_change
    page.go("/shipment")

# ==================== 启动 ====================
if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER)  # 开发时用浏览器模式，方便调试
