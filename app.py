"""
好色指数测试 Web 应用
- 页面浏览 / 点击 / 测试完成 全链路追踪
- SQLite 本地数据存储
- 统计数据 API
"""
import os
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, g

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "analytics.db")


# ─── 数据库 ──────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        _init_db(g.db)
    return g.db

def _init_db(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS page_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            referrer TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            element_id TEXT,
            element_text TEXT,
            screen TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS test_completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            total_score INTEGER,
            result_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ─── 页面路由 ──────────────────────────────────────────────
@app.route("/")
def index():
    session_id = request.args.get("sid", str(uuid.uuid4()))
    db = get_db()
    db.execute(
        "INSERT INTO page_views (session_id, referrer, user_agent) VALUES (?, ?, ?)",
        (session_id, request.referrer or "", request.user_agent.string or "")
    )
    db.commit()
    resp = make_response(render_template("index.html"))
    resp.set_cookie("sid", session_id, max_age=60*60*24*30)
    return resp


# ─── 追踪 API ──────────────────────────────────────────────
@app.route("/api/track", methods=["POST"])
def track():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "no data"}), 400

        event_type = data.get("type")
        session_id = request.cookies.get("sid", "unknown")

        db = get_db()

        if event_type == "click":
            db.execute(
                "INSERT INTO clicks (session_id, element_id, element_text, screen) VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    data.get("elementId", ""),
                    data.get("elementText", ""),
                    data.get("screen", "")
                )
            )

        elif event_type == "test_complete":
            db.execute(
                "INSERT INTO test_completions (session_id, total_score, result_type) VALUES (?, ?, ?)",
                (
                    session_id,
                    data.get("score", 0),
                    data.get("resultType", "")
                )
            )

        elif event_type == "page_view":
            db.execute(
                "INSERT INTO page_views (session_id, referrer, user_agent) VALUES (?, ?, ?)",
                (session_id, data.get("referrer", ""), data.get("userAgent", ""))
            )

        db.commit()
        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── 统计 API ──────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def stats():
    db = get_db()

    # 总浏览量
    total_views = db.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]

    # 今日浏览量
    today = datetime.now().strftime("%Y-%m-%d")
    today_views = db.execute(
        "SELECT COUNT(*) FROM page_views WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]

    # 总测试完成数
    total_completions = db.execute("SELECT COUNT(*) FROM test_completions").fetchone()[0]

    # 今日测试完成数
    today_completions = db.execute(
        "SELECT COUNT(*) FROM test_completions WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]

    # 各类型分布
    type_dist = db.execute("""
        SELECT result_type, COUNT(*) as cnt
        FROM test_completions
        GROUP BY result_type
        ORDER BY cnt DESC
    """).fetchall()

    # 近7天每日数据
    week_data = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        views = db.execute(
            "SELECT COUNT(*) FROM page_views WHERE date(created_at) = ?", (day,)
        ).fetchone()[0]
        comps = db.execute(
            "SELECT COUNT(*) FROM test_completions WHERE date(created_at) = ?", (day,)
        ).fetchone()[0]
        week_data.append({"date": day, "views": views, "completions": comps})

    # 平均分
    avg_score_row = db.execute("SELECT AVG(total_score) FROM test_completions").fetchone()
    avg_score = round(float(avg_score_row[0]), 1) if avg_score_row[0] else 0

    # 参与类型分布
    type_labels = []
    type_counts = []
    type_total = sum([r["cnt"] for r in type_dist]) or 1
    for r in type_dist:
        type_labels.append(r["result_type"])
        type_counts.append(r["cnt"])

    # 总点击数
    total_clicks = db.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]

    # 完成率
    completion_rate = round(total_completions / total_views * 100, 1) if total_views > 0 else 0

    return jsonify({
        "total_views": total_views,
        "today_views": today_views,
        "total_completions": total_completions,
        "today_completions": today_completions,
        "total_clicks": total_clicks,
        "avg_score": avg_score,
        "completion_rate": completion_rate,
        "type_labels": type_labels,
        "type_counts": type_counts,
        "week_data": week_data,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# ─── 数据报告（纯文本，用于推送） ──────────────────────────────
@app.route("/api/report", methods=["GET"])
def report():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    total_views = db.execute("SELECT COUNT(*) FROM page_views").fetchone()[0]
    today_views = db.execute(
        "SELECT COUNT(*) FROM page_views WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]
    total_completions = db.execute("SELECT COUNT(*) FROM test_completions").fetchone()[0]
    today_completions = db.execute(
        "SELECT COUNT(*) FROM test_completions WHERE date(created_at) = ?", (today,)
    ).fetchone()[0]
    total_clicks = db.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]

    avg_row = db.execute("SELECT AVG(total_score) FROM test_completions").fetchone()
    avg_score = round(float(avg_row[0]), 1) if avg_row[0] else 0

    completion_rate = round(total_completions / total_views * 100, 1) if total_views > 0 else 0

    type_dist = db.execute("""
        SELECT result_type, COUNT(*) as cnt
        FROM test_completions
        GROUP BY result_type
        ORDER BY cnt DESC
    """).fetchall()

    week_data = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%m-%d")
        views = db.execute(
            "SELECT COUNT(*) FROM page_views WHERE date(created_at) = date('now', ?)",
            (f"-{i} days",)
        ).fetchone()[0]
        comps = db.execute(
            "SELECT COUNT(*) FROM test_completions WHERE date(created_at) = date('now', ?)",
            (f"-{i} days",)
        ).fetchone()[0]
        week_data.append(f"{day}: {views}浏览 / {comps}完成")

    lines = [
        f"📊 好色指数测试 - 数据报告",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"【总体数据】",
        f"  总浏览量：{total_views}",
        f"  今日浏览：{today_views}",
        f"  总测试完成：{total_completions}",
        f"  今日完成：{today_completions}",
        f"  总点击次数：{total_clicks}",
        f"  完成率：{completion_rate}%",
        f"  平均得分：{avg_score}分",
        "",
        f"【类型分布】",
    ]
    if type_dist:
        for r in type_dist:
            pct = round(r["cnt"] / total_completions * 100, 1) if total_completions else 0
            lines.append(f"  {r['result_type']}：{r['cnt']}人 ({pct}%)")
    else:
        lines.append("  暂无数据")

    lines += ["", "【近7天趋势】"] + week_data

    return jsonify({"text": "\n".join(lines)})


# ─── 管理面板 ──────────────────────────────────────────────
@app.route("/admin")
def admin():
    return render_template("admin.html")


from flask import make_response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
