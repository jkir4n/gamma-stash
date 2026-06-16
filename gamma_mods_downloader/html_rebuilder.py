"""
HTML tracking page builder for the Gamma Mods Downloader.

Generates a human-friendly HTML page showing all mods, their download status,
and MD5 verification results. Groups entries by category (from mods.txt headers).
"""

import os
from datetime import datetime
from typing import Dict, List, Optional


def rebuild_html(
    entries: List[Dict[str, str]],
    categories: Optional[List[str]] = None,
    entries_by_category: Optional[List[List[Dict[str, str]]]] = None,
    output_dir: str = ".",
    title: str = "G.A.M.M.A. Mods — Download Tracker",
) -> str:
    """
    Generate an HTML tracking page from mod entries.
    
    If categories and entries_by_category are provided, the HTML groups
    entries under their category headers. Otherwise all entries are listed flat.
    """
    output_path = os.path.join(output_dir, "gamma_mods_status.html")

    total = len(entries)
    downloaded = sum(1 for e in entries if e["status"] == "DOWNLOADED")
    pending = total - downloaded
    moddb_count = sum(1 for e in entries if e.get("source") == "MODDB")
    github_count = sum(1 for e in entries if e.get("source") == "GITHUB")
    with_md5 = sum(1 for e in entries if e.get("expected_md5"))
    without_md5 = total - with_md5

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 24px; }}
  h1 {{ font-size: 24px; margin-bottom: 12px; color: #f0f6fc; }}
  .stats {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
  .stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px;
           padding: 12px 20px; }}
  .stat .num {{ font-size: 24px; font-weight: 600; }}
  .stat .label {{ font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }}
  .top-stat {{ color: #58a6ff; }}
  .dl-stat {{ color: #3fb950; }}
  .pd-stat {{ color: #d29922; }}
  .warning {{ color: #da3633; }}

  .category {{ margin-top: 20px; }}
  .category h2 {{ font-size: 16px; color: #f0f6fc; background: #161b22;
                padding: 8px 12px; border-radius: 6px 6px 0 0;
                border: 1px solid #30363d; border-bottom: none; }}
  .category h2 span {{ float: right; font-weight: 400; color: #8b949e;
                     font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse;
           border: 1px solid #30363d; border-radius: 0 0 6px 6px;
           overflow: hidden; }}
  th {{ background: #161b22; padding: 8px 12px; text-align: left;
       font-size: 12px; color: #8b949e; text-transform: uppercase;
       letter-spacing: 0.5px; border-bottom: 1px solid #30363d; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #21262d;
       font-size: 13px; vertical-align: top; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1c2128; }}
  .status-dl {{ color: #3fb950; }}
  .status-pd {{ color: #d29922; }}
  .src {{ font-size: 11px; color: #8b949e; }}
  .desc {{ color: #8b949e; font-size: 12px; }}
  .author {{ color: #484f58; font-size: 11px; }}
  .md5 {{ font-family: 'SF Mono', 'Cascadia Code', monospace; font-size: 11px; color: #484f58; }}
  .no-md5 {{ color: #da3633; font-size: 11px; }}
  .footer {{ margin-top: 24px; font-size: 12px; color: #484f58; text-align: center; }}
</style>
</head>
<body>

<h1>{title}</h1>
<p style="color: #8b949e; margin-bottom: 16px;">Generated: {now}</p>

<div class="stats">
  <div class="stat"><div class="num top-stat">{total}</div><div class="label">Total Mods</div></div>
  <div class="stat"><div class="num dl-stat">{downloaded}</div><div class="label">Downloaded</div></div>
  <div class="stat"><div class="num pd-stat">{pending}</div><div class="label">Pending</div></div>
  <div class="stat"><div class="num top-stat">{moddb_count}</div><div class="label">ModDB</div></div>
  <div class="stat"><div class="num top-stat">{github_count}</div><div class="label">GitHub</div></div>
  <div class="stat"><div class="num {'top-stat' if without_md5 == 0 else 'warning'}">{with_md5}</div><div class="label">With MD5</div></div>
  <div class="stat"><div class="num {'warning' if without_md5 > 0 else 'top-stat'}">{without_md5}</div><div class="label">Without MD5</div></div>
</div>
"""
    # Render entries
    if categories and entries_by_category and len(categories) == len(entries_by_category):
        for cat_idx, cat_name in enumerate(categories):
            cat_entries = entries_by_category[cat_idx]
            dl = sum(1 for e in cat_entries if e["status"] == "DOWNLOADED")
            html += _render_table(cat_name, cat_entries, dl)
    else:
        html += _render_table("All Mods", entries, downloaded)

    html += f"""
<div class="footer">
  Generated by Gamma Mods Downloader — {now}<br>
  Source: G.A.M.M.A. mods.txt ({total} entries, {with_md5} with MD5, {without_md5} without)
</div>

</body>
</html>
"""
    with open(output_path, "w") as f:
        f.write(html)
    return output_path


def _render_table(category: str, entries: List[Dict[str, str]],
                  downloaded: int) -> str:
    """Render an HTML table section for a category of entries."""
    html = f"""<div class="category">
  <h2>{category} <span>{downloaded}/{len(entries)}</span></h2>
  <table>
    <thead>
      <tr>
        <th style="width: 40px;">Status</th>
        <th style="width: 50px;">Src</th>
        <th>Filename</th>
        <th>Description</th>
        <th style="width: 110px;">MD5</th>
        <th>Author</th>
      </tr>
    </thead>
    <tbody>
"""
    for e in entries:
        status_cls = "status-dl" if e["status"] == "DOWNLOADED" else "status-pd"
        status_icon = "✅" if e["status"] == "DOWNLOADED" else "⏳"
        src_icon = "🐙" if e.get("source") == "GITHUB" else "🌐"

        desc = e.get("description", "")
        author = e.get("author", "")

        if e.get("expected_md5"):
            md5_display = e["expected_md5"][:8] + "…"
            md5_cls = "md5"
        else:
            md5_display = "—"
            md5_cls = "no-md5"

        html += f"""      <tr>
        <td><span class="{status_cls}">{status_icon}</span></td>
        <td><span class="src">{src_icon}</span></td>
        <td>{e['filename']}</td>
        <td><span class="desc">{desc}</span></td>
        <td><span class="{md5_cls}">{md5_display}</span></td>
        <td><span class="author">{author}</span></td>
      </tr>
"""
    html += """    </tbody>
  </table>
</div>
"""
    return html
