"""
打印工具 - 生成 HTML 打印页面
电脑端用浏览器打开，手机端可调用系统分享/打印
"""
import webbrowser, tempfile, os, platform
from datetime import datetime

def _open(path: str):
    """跨平台打开文件"""
    if platform.system() == "Android":
        # Flet 在 Android 上可用 flet.open_in_browser 或启动 Intent
        try:
            import flet as ft
            ft.open_in_browser("file://" + path)
            return
        except:
            pass
    webbrowser.open("file://" + path)

def print_shipment(ship: dict, items: list[dict]):
    """打印出货单"""
    rows = "".join(
        f"<tr><td>{it['name']}</td><td>{it['qty']}</td><td>¥{it['price']:.2f}</td><td>¥{it['qty']*it['price']:.2f}</td></tr>"
        for it in items
    )
    total = sum(it['qty']*it['price'] for it in items)
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>出货单 {ship['order_no']}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;padding:40px;max-width:800px;margin:0 auto}}
h2{{text-align:center;margin-bottom:5px}}
.info{{display:flex;justify-content:space-between;margin:20px 0}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{border:1px solid #333;padding:8px;text-align:center}}
th{{background:#f0f0f0}}
.total{{text-align:right;margin-top:20px;font-size:16px;font-weight:bold}}
@media print{{
  body{{padding:10mm}}
  .no-print{{display:none}}
}}
</style></head><body>
<h2>好麦出货系统 · 出货单</h2>
<div class="info"><span>单号: {ship['order_no']}</span><span>日期: {ship['ship_date']}</span></div>
<div class="info"><span>客户: {ship['customer']}</span><span>备注: {ship.get('remark','')}</span></div>
<table><tr><th>产品名称</th><th>数量</th><th>单价</th><th>小计</th></tr>{rows}
<tr><td colspan="3" style="text-align:right;font-weight:bold">合计</td><td style="font-weight:bold">¥{total:.2f}</td></tr></table>
<p style="text-align:right;margin-top:30px;color:#999">打印时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<button class="no-print" onclick="window.print()" style="position:fixed;top:10px;right:10px;padding:10px 20px;font-size:16px;cursor:pointer">🖨️ 打印</button>
</body></html>"""
    _write_and_open(html, f"出货单_{ship['order_no']}")

def print_summary(d: str, rows: list[dict], total: float, commission: float, customers: list[str]):
    """打印销售汇总表"""
    cust_str = "、".join(customers) if customers else "—"
    body = "".join(
        f"<tr><td>{r['name']}</td><td>{r['ship']}</td><td>{r['out']}</td><td>{r['in']}</td>"
        f"<td>{r['inv']}</td><td>{r['actual']}</td><td>¥{r['price']:.2f}</td><td>¥{r['amount']:.2f}</td></tr>"
        for r in rows
    )
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>销售汇总 {d}</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;padding:40px;max-width:900px;margin:0 auto}}
h2{{text-align:center;margin-bottom:5px}}
.sub{{text-align:center;color:#666;margin-bottom:20px}}
.customer{{margin:10px 0;font-size:14px;color:#333}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{border:1px solid #333;padding:6px;text-align:center}}
th{{background:#f0f0f0}}
.footer{{margin-top:20px;text-align:right;font-size:16px}}
.commission{{color:red;font-weight:bold}}
@media print{{body{{padding:10mm}}.no-print{{display:none}}}}
</style></head><body>
<h2>好麦出货系统 · 销售汇总表</h2>
<div class="sub">汇总日期: {d}</div>
<div class="customer">客户名称: {cust_str}</div>
<table><tr><th>产品名称</th><th>出货</th><th>调出</th><th>调入</th><th>剩货</th><th>实际销售</th><th>单价</th><th>销售金额</th></tr>{body}</table>
<div class="footer">
<div>合计销售金额: ¥{total:.2f}</div>
<div class="commission">提成 (20%): ¥{commission:.2f}</div>
</div>
<p style="text-align:right;margin-top:30px;color:#999">打印时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<button class="no-print" onclick="window.print()" style="position:fixed;top:10px;right:10px;padding:10px 20px;font-size:16px;cursor:pointer">🖨️ 打印</button>
</body></html>"""
    _write_and_open(html, f"汇总_{d}")

def _write_and_open(html: str, prefix: str):
    f = tempfile.NamedTemporaryFile('w', delete=False, suffix='.html', prefix=prefix+'_', encoding='utf-8')
    f.write(html); f.close()
    _open(f.name)
