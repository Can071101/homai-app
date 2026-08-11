"""
好麦出货系统 - 数据库管理模块
支持：产品、出货单、调出单、调入单、剩货单、汇总计算
"""
import sqlite3
from datetime import date
from contextlib import contextmanager

DB_PATH = "homai_system.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ==================== 初始化 ====================

def init_db():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            price REAL NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS shipments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            customer TEXT NOT NULL,
            ship_date TEXT NOT NULL,
            remark TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS shipment_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(shipment_id) REFERENCES shipments(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS transfers_out(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            destination TEXT NOT NULL,
            transfer_date TEXT NOT NULL,
            remark TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS transfer_out_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(transfer_id) REFERENCES transfers_out(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS transfers_in(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            transfer_date TEXT NOT NULL,
            remark TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS transfer_in_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(transfer_id) REFERENCES transfers_in(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS inventories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_date TEXT NOT NULL,
            remark TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS inventory_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(inventory_id) REFERENCES inventories(id) ON DELETE CASCADE,
            FOREIGN KEY(product_id) REFERENCES products(id))""")

# ==================== 产品 ====================

def add_product(name: str, price: float) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO products(name,price) VALUES(?,?)", (name.strip(), float(price)))
        return True
    except sqlite3.IntegrityError:
        return False

def update_product(pid: int, name: str, price: float) -> bool:
    try:
        with get_conn() as conn:
            conn.execute("UPDATE products SET name=?,price=? WHERE id=?", (name.strip(), float(price), pid))
        return True
    except sqlite3.IntegrityError:
        return False

def delete_product(pid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))

def get_products() -> list[dict]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,name,price FROM products ORDER BY name")
        return [{"id":r[0],"name":r[1],"price":r[2]} for r in c.fetchall()]

def get_product(pid: int) -> dict | None:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,name,price FROM products WHERE id=?", (pid,))
        r = c.fetchone()
        return {"id":r[0],"name":r[1],"price":r[2]} if r else None

# ==================== 出货单 ====================

def gen_order_no(prefix="SH") -> str:
    d = date.today().strftime("%Y%m%d")
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM shipments WHERE ship_date=?", (date.today().isoformat(),))
        n = c.fetchone()[0] + 1
    return f"{prefix}{d}{n:03d}"

def create_shipment(order_no: str, customer: str, d: str, remark: str, items: list[tuple]) -> int:
    """返回新单据ID"""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO shipments(order_no,customer,ship_date,remark) VALUES(?,?,?,?)",
                  (order_no.strip(), customer.strip(), d, remark))
        sid = c.lastrowid
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO shipment_items(shipment_id,product_id,quantity) VALUES(?,?,?)",
                          (sid, pid, qty))
    return sid

def update_shipment(sid: int, order_no: str, customer: str, d: str, remark: str, items: list[tuple]):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE shipments SET order_no=?,customer=?,ship_date=?,remark=? WHERE id=?",
                  (order_no.strip(), customer.strip(), d, remark, sid))
        c.execute("DELETE FROM shipment_items WHERE shipment_id=?", (sid,))
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO shipment_items(shipment_id,product_id,quantity) VALUES(?,?,?)",
                          (sid, pid, qty))

def delete_shipment(sid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM shipments WHERE id=?", (sid,))

def get_shipment_detail(sid: int) -> tuple[dict, list[dict]]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,order_no,customer,ship_date,remark FROM shipments WHERE id=?", (sid,))
        r = c.fetchone()
        if not r: return None, []
        ship = {"id":r[0],"order_no":r[1],"customer":r[2],"ship_date":r[3],"remark":r[4] or ""}
        c.execute("""SELECT p.id,p.name,p.price,si.quantity
                     FROM shipment_items si JOIN products p ON si.product_id=p.id
                     WHERE si.shipment_id=?""", (sid,))
        items = [{"product_id":r[0],"name":r[1],"price":r[2],"qty":r[3]} for r in c.fetchall()]
    return ship, items

def query_shipments_by_date(d: str) -> list[dict]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""SELECT s.id,s.order_no,s.customer,s.ship_date,s.remark,
                            COALESCE(SUM(si.quantity*p.price),0)
                     FROM shipments s
                     LEFT JOIN shipment_items si ON si.shipment_id=s.id
                     LEFT JOIN products p ON si.product_id=p.id
                     WHERE s.ship_date=?
                     GROUP BY s.id
                     ORDER BY s.id DESC""", (d,))
        return [{"id":r[0],"order_no":r[1],"customer":r[2],"date":r[3],"remark":r[4] or "","amount":r[5]}
                for r in c.fetchall()]

# ==================== 调出单 ====================

def create_transfer_out(dest: str, d: str, remark: str, items: list[tuple]) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO transfers_out(destination,transfer_date,remark) VALUES(?,?,?)",
                  (dest.strip(), d, remark))
        tid = c.lastrowid
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO transfer_out_items(transfer_id,product_id,quantity) VALUES(?,?,?)",
                          (tid, pid, qty))
    return tid

def update_transfer_out(tid: int, dest: str, d: str, remark: str, items: list[tuple]):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE transfers_out SET destination=?,transfer_date=?,remark=? WHERE id=?",
                  (dest.strip(), d, remark, tid))
        c.execute("DELETE FROM transfer_out_items WHERE transfer_id=?", (tid,))
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO transfer_out_items(transfer_id,product_id,quantity) VALUES(?,?,?)",
                          (tid, pid, qty))

def delete_transfer_out(tid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM transfers_out WHERE id=?", (tid,))

def get_transfer_out_detail(tid: int) -> tuple[dict, list[dict]]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,destination,transfer_date,remark FROM transfers_out WHERE id=?", (tid,))
        r = c.fetchone()
        if not r: return None, []
        info = {"id":r[0],"destination":r[1],"date":r[2],"remark":r[3] or ""}
        c.execute("""SELECT p.id,p.name,p.price,ti.quantity
                     FROM transfer_out_items ti JOIN products p ON ti.product_id=p.id
                     WHERE ti.transfer_id=?""", (tid,))
        items = [{"product_id":r[0],"name":r[1],"price":r[2],"qty":r[3]} for r in c.fetchall()]
    return info, items

def query_transfers_out_by_date(d: str) -> list[dict]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,destination,transfer_date,remark FROM transfers_out WHERE transfer_date=? ORDER BY id DESC", (d,))
        return [{"id":r[0],"destination":r[1],"date":r[2],"remark":r[3] or ""} for r in c.fetchall()]

# ==================== 调入单 ====================

def create_transfer_in(src: str, d: str, remark: str, items: list[tuple]) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO transfers_in(source,transfer_date,remark) VALUES(?,?,?)",
                  (src.strip(), d, remark))
        tid = c.lastrowid
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO transfer_in_items(transfer_id,product_id,quantity) VALUES(?,?,?)",
                          (tid, pid, qty))
    return tid

def update_transfer_in(tid: int, src: str, d: str, remark: str, items: list[tuple]):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE transfers_in SET source=?,transfer_date=?,remark=? WHERE id=?",
                  (src.strip(), d, remark, tid))
        c.execute("DELETE FROM transfer_in_items WHERE transfer_id=?", (tid,))
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO transfer_in_items(transfer_id,product_id,quantity) VALUES(?,?,?)",
                          (tid, pid, qty))

def delete_transfer_in(tid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM transfers_in WHERE id=?", (tid,))

def get_transfer_in_detail(tid: int) -> tuple[dict, list[dict]]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,source,transfer_date,remark FROM transfers_in WHERE id=?", (tid,))
        r = c.fetchone()
        if not r: return None, []
        info = {"id":r[0],"source":r[1],"date":r[2],"remark":r[3] or ""}
        c.execute("""SELECT p.id,p.name,p.price,ti.quantity
                     FROM transfer_in_items ti JOIN products p ON ti.product_id=p.id
                     WHERE ti.transfer_id=?""", (tid,))
        items = [{"product_id":r[0],"name":r[1],"price":r[2],"qty":r[3]} for r in c.fetchall()]
    return info, items

def query_transfers_in_by_date(d: str) -> list[dict]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,source,transfer_date,remark FROM transfers_in WHERE transfer_date=? ORDER BY id DESC", (d,))
        return [{"id":r[0],"source":r[1],"date":r[2],"remark":r[3] or ""} for r in c.fetchall()]

# ==================== 剩货单 ====================

def create_inventory(d: str, remark: str, items: list[tuple]) -> int:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO inventories(record_date,remark) VALUES(?,?)", (d, remark))
        iid = c.lastrowid
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO inventory_items(inventory_id,product_id,quantity) VALUES(?,?,?)",
                          (iid, pid, qty))
    return iid

def update_inventory(iid: int, d: str, remark: str, items: list[tuple]):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("UPDATE inventories SET record_date=?,remark=? WHERE id=?", (d, remark, iid))
        c.execute("DELETE FROM inventory_items WHERE inventory_id=?", (iid,))
        for pid, qty in items:
            if qty > 0:
                c.execute("INSERT INTO inventory_items(inventory_id,product_id,quantity) VALUES(?,?,?)",
                          (iid, pid, qty))

def delete_inventory(iid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM inventories WHERE id=?", (iid,))

def get_inventory_detail(iid: int) -> tuple[dict, list[dict]]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,record_date,remark FROM inventories WHERE id=?", (iid,))
        r = c.fetchone()
        if not r: return None, []
        info = {"id":r[0],"date":r[1],"remark":r[2] or ""}
        c.execute("""SELECT p.id,p.name,p.price,ii.quantity
                     FROM inventory_items ii JOIN products p ON ii.product_id=p.id
                     WHERE ii.inventory_id=?""", (iid,))
        items = [{"product_id":r[0],"name":r[1],"price":r[2],"qty":r[3]} for r in c.fetchall()]
    return info, items

def query_inventories_by_date(d: str) -> list[dict]:
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id,record_date,remark FROM inventories WHERE record_date=? ORDER BY id DESC", (d,))
        return [{"id":r[0],"date":r[1],"remark":r[2] or ""} for r in c.fetchall()]

# ==================== 汇总 ====================

def get_daily_summary(d: str) -> tuple[list[dict], float, float, list[str]]:
    """
    当日销售汇总
    实际销售 = 出货 - 调出 + 调入 - 剩货
    返回: (明细行列表, 合计金额, 提成, 客户名称列表)
    """
    with get_conn() as conn:
        c = conn.cursor()

        def agg(sql, date_param=d):
            c.execute(sql, (date_param,))
            return {r[0]: r[1] for r in c.fetchall()}

        ship_qty = agg("""SELECT si.product_id,SUM(si.quantity)
                           FROM shipment_items si JOIN shipments s ON si.shipment_id=s.id
                           WHERE s.ship_date=? GROUP BY si.product_id""")
        out_qty = agg("""SELECT ti.product_id,SUM(ti.quantity)
                          FROM transfer_out_items ti JOIN transfers_out t ON ti.transfer_id=t.id
                          WHERE t.transfer_date=? GROUP BY ti.product_id""")
        in_qty = agg("""SELECT ti.product_id,SUM(ti.quantity)
                         FROM transfer_in_items ti JOIN transfers_in t ON ti.transfer_id=t.id
                         WHERE t.transfer_date=? GROUP BY ti.product_id""")
        inv_qty = agg("""SELECT ii.product_id,SUM(ii.quantity)
                          FROM inventory_items ii JOIN inventories i ON ii.inventory_id=i.id
                          WHERE i.record_date=? GROUP BY ii.product_id""")

        # 客户列表（去重保序）
        c.execute("SELECT DISTINCT customer FROM shipments WHERE ship_date=? ORDER BY id", (d,))
        customers = [r[0] for r in c.fetchall() if r[0]]

        c.execute("SELECT id,name,price FROM products ORDER BY name")
        prods = [{"id":r[0],"name":r[1],"price":r[2]} for r in c.fetchall()]

    rows = []
    total = 0.0
    for p in prods:
        pid = p["id"]
        actual = ship_qty.get(pid,0) - out_qty.get(pid,0) + in_qty.get(pid,0) - inv_qty.get(pid,0)
        if actual > 0:
            amt = round(actual * p["price"], 2)
            total += amt
            rows.append({
                "product_id": pid, "name": p["name"], "price": p["price"],
                "ship": ship_qty.get(pid,0), "out": out_qty.get(pid,0),
                "in": in_qty.get(pid,0), "inv": inv_qty.get(pid,0),
                "actual": actual, "amount": amt
            })
    commission = round(total * 0.2, 2)
    return rows, total, commission, customers

# ==================== 单据查询（通用）====================

def query_documents_by_date(d: str, doc_type: str) -> list[dict]:
    """统一查询接口，返回带 type 标记的单据列表"""
    results = []
    for s in query_shipments_by_date(d):
        results.append({"type":"shipment","id":s["id"],"summary":f"客户: {s['customer']} | 金额: ¥{s['amount']:.0f}","order_no":s["order_no"],"date":s["date"],"remark":s["remark"]})
    for t in query_transfers_out_by_date(d):
        results.append({"type":"transfer_out","id":t["id"],"summary":f"调出至: {t['destination']}","order_no":f"TO{t['id']:06d}","date":t["date"],"remark":t["remark"]})
    for t in query_transfers_in_by_date(d):
        results.append({"type":"transfer_in","id":t["id"],"summary":f"调入自: {t['source']}","order_no":f"TI{t['id']:06d}","date":t["date"],"remark":t["remark"]})
    for inv in query_inventories_by_date(d):
        results.append({"type":"inventory","id":inv["id"],"summary":f"剩货记录","order_no":f"INV{inv['id']:06d}","date":inv["date"],"remark":inv["remark"]})
    return results

# 初始化
init_db()
