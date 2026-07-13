"""
Watchdog サービス  - Daily Tech Trend パイプラインの監視・自動修復・Ollama分析

タスクスケジューラから30分間隔で起動し、以下を行う:
  1. 状態チェック (ルールベース)
  2. 自動修復 (ルールベース)
  3. 原因分析レポート (Ollama)
"""

import datetime
import glob
import json
import os
import subprocess
import sys
import textwrap

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
WATCHDOG_LOG_DIR = os.path.join(LOG_DIR, "watchdog")
TASK_NAME = "Daily Tech Trend"

# ハング判定の閾値（秒） - デフォルト2時間
HANG_THRESHOLD_SEC = int(os.getenv("WATCHDOG_HANG_SEC", "7200"))
# ログファイルの mtime がこの秒数更新されていなければハングと判定 - デフォルト30分
LOG_IDLE_THRESHOLD_SEC = int(os.getenv("WATCHDOG_LOG_IDLE_SEC", "1800"))
# 最終コミットからの経過時間閾値（秒） - デフォルト6時間
COMMIT_STALE_SEC = int(os.getenv("WATCHDOG_COMMIT_STALE_SEC", "21600"))
# 1回の実行で修復を試みる最大回数
MAX_REPAIR_PER_RUN = 2

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")

# ---------------------------------------------------------------------------
# ログ
# ---------------------------------------------------------------------------
os.makedirs(WATCHDOG_LOG_DIR, exist_ok=True)
_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
_log_path = os.path.join(WATCHDOG_LOG_DIR, f"watchdog_{_ts}.log")


def _log(level: str, msg: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{now} [{level}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("utf-8", errors="replace").decode("ascii", errors="replace"))
    with open(_log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_info(msg: str):
    _log("INFO", msg)


def log_warn(msg: str):
    _log("WARN", msg)


def log_error(msg: str):
    _log("ERROR", msg)


# ---------------------------------------------------------------------------
# 1. 状態チェック
# ---------------------------------------------------------------------------
class Issue:
    """検知した問題を表すデータクラス"""
    def __init__(self, kind: str, detail: str, severity: str = "warning"):
        self.kind = kind        # hung / failed / stale_commit / git_lock
        self.detail = detail
        self.severity = severity  # warning / critical

    def __repr__(self):
        return f"Issue({self.kind}: {self.detail})"


def _latest_log_idle_seconds() -> float | None:
    """最新の run_*.log の最終更新からの経過秒数を返す。ログが無ければ None。"""
    pattern = os.path.join(LOG_DIR, "run_*.log")
    logs = sorted(glob.glob(pattern), reverse=True)
    if not logs:
        return None
    try:
        mtime = os.path.getmtime(logs[0])
        return max(0.0, datetime.datetime.now().timestamp() - mtime)
    except OSError:
        return None


def _powershell(cmd: str, timeout: int = 30) -> str:
    """PowerShellコマンドを実行して stdout を返す"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def check_task_state() -> list[Issue]:
    """タスクスケジューラの状態をチェック"""
    issues = []
    try:
        state = _powershell(
            f"(Get-ScheduledTask -TaskName '{TASK_NAME}').State"
        )
        log_info(f"タスク状態: {state}")

        if state == "Running":
            # 実行開始からの経過を確認
            last_run = _powershell(
                f"(Get-ScheduledTask -TaskName '{TASK_NAME}' "
                f"| Get-ScheduledTaskInfo).LastRunTime"
            )
            log_info(f"最終実行開始: {last_run}")
            if last_run:
                try:
                    # "2026/04/04 18:00:01" 形式をパース
                    dt = datetime.datetime.strptime(last_run, "%Y/%m/%d %H:%M:%S")
                    elapsed = (datetime.datetime.now() - dt).total_seconds()
                    if elapsed > HANG_THRESHOLD_SEC:
                        issues.append(Issue(
                            "hung",
                            f"タスクが {elapsed/3600:.1f} 時間 Running のままハング中 "
                            f"(閾値: {HANG_THRESHOLD_SEC/3600:.1f}h)",
                            "critical",
                        ))
                    else:
                        # ログ更新が一定時間止まっていればハング兆候として扱う
                        idle = _latest_log_idle_seconds()
                        if idle is not None and idle > LOG_IDLE_THRESHOLD_SEC:
                            issues.append(Issue(
                                "log_idle",
                                f"最新ログが {idle/60:.0f} 分間更新されていない "
                                f"(閾値: {LOG_IDLE_THRESHOLD_SEC/60:.0f}分) - ハング兆候",
                                "warning",
                            ))
                except ValueError:
                    log_warn(f"LastRunTime パース失敗: {last_run}")

        elif state == "Ready":
            # 前回の結果コードを確認
            result_code = _powershell(
                f"(Get-ScheduledTask -TaskName '{TASK_NAME}' "
                f"| Get-ScheduledTaskInfo).LastTaskResult"
            )
            if result_code and result_code != "0":
                issues.append(Issue(
                    "failed",
                    f"前回の実行が失敗 (結果コード: {result_code})",
                    "warning",
                ))
    except subprocess.TimeoutExpired:
        log_error("タスク状態取得がタイムアウト")
    except Exception as e:
        log_error(f"タスク状態取得エラー: {e}")

    return issues


def check_latest_log() -> list[Issue]:
    """最新のパイプラインログを確認"""
    issues = []
    pattern = os.path.join(LOG_DIR, "run_*.log")
    logs = sorted(glob.glob(pattern), reverse=True)
    if not logs:
        issues.append(Issue("no_log", "パイプラインログが存在しない", "warning"))
        return issues

    latest = logs[0]
    log_info(f"最新ログ: {os.path.basename(latest)}")

    try:
        with open(latest, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = content.strip().splitlines()

        if not lines:
            issues.append(Issue("empty_log", f"ログが空: {os.path.basename(latest)}", "warning"))
            return issues

        last_line = lines[-1]

        if "FAILED_FROM_BAT" in last_line:
            # 失敗ステップを抽出
            issues.append(Issue(
                "failed",
                f"パイプライン失敗: {last_line.strip()}",
                "critical",
            ))
        elif "SUCCESS_FROM_BAT" not in last_line and len(lines) < 20:
            # ログが短すぎて終了マーカーもない → 途中で死んだ可能性
            issues.append(Issue(
                "incomplete_log",
                f"ログが不完全 ({len(lines)}行, 終了マーカーなし): {os.path.basename(latest)}",
                "warning",
            ))

        # ログ内容を後続分析用にリストに属性として付与
        class IssueList(list):
            pass
        result = IssueList(issues)
        result._log_content = content  # type: ignore[attr-defined]
        return result
    except Exception as e:
        log_error(f"ログ読み取りエラー: {e}")

    return issues


def check_commit_freshness() -> list[Issue]:
    """最終コミットの鮮度を確認"""
    issues = []
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=10,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            ts = int(result.stdout.strip())
            elapsed = datetime.datetime.now().timestamp() - ts
            log_info(f"最終コミットからの経過: {elapsed/3600:.1f}h")
            if elapsed > COMMIT_STALE_SEC:
                issues.append(Issue(
                    "stale_commit",
                    f"最終コミットから {elapsed/3600:.1f} 時間経過 "
                    f"(閾値: {COMMIT_STALE_SEC/3600:.1f}h)",
                    "warning",
                ))
    except Exception as e:
        log_error(f"git log エラー: {e}")
    return issues


def check_git_lock() -> list[Issue]:
    """git lockファイルの残存を確認"""
    issues = []
    lock_path = os.path.join(PROJECT_ROOT, ".git", "index.lock")
    if os.path.exists(lock_path):
        try:
            mtime = os.path.getmtime(lock_path)
            age = datetime.datetime.now().timestamp() - mtime
            if age > 300:  # 5分以上前のlockは異常
                issues.append(Issue(
                    "git_lock",
                    f"index.lock が {age/60:.0f}分間残存",
                    "critical",
                ))
        except Exception as e:
            log_error(f"lock確認エラー: {e}")
    return issues


def run_checks() -> tuple[list[Issue], str | None]:
    """全チェックを実行。(issues, log_content) を返す"""
    all_issues: list[Issue] = []
    log_content = None

    for check_fn in [check_task_state, check_latest_log, check_commit_freshness, check_git_lock]:
        result = check_fn()
        # ログ内容を退避
        if hasattr(result, "_log_content"):
            log_content = result._log_content  # type: ignore[attr-defined]
        all_issues.extend(result)

    return all_issues, log_content


# ---------------------------------------------------------------------------
# 2. 自動修復
# ---------------------------------------------------------------------------
def repair_hung_task() -> bool:
    """ハングしたタスクを停止→再起動"""
    log_info("修復: ハングしたタスクを停止します")
    try:
        _powershell(f"Stop-ScheduledTask -TaskName '{TASK_NAME}'")
        state = _powershell(f"(Get-ScheduledTask -TaskName '{TASK_NAME}').State")
        log_info(f"停止後の状態: {state}")
        if state == "Ready":
            log_info("修復: タスクを再起動します")
            _powershell(f"Start-ScheduledTask -TaskName '{TASK_NAME}'")
            log_info("修復: タスク再起動完了")
            return True
    except Exception as e:
        log_error(f"タスク修復失敗: {e}")
    return False


def repair_git_lock() -> bool:
    """残存する git lock を削除（git プロセス実行中は正当なロックとみなし削除しない）"""
    lock_path = os.path.join(PROJECT_ROOT, ".git", "index.lock")
    if not os.path.exists(lock_path):
        return False
    try:
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq git.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
        )
        if "git.exe" in (r.stdout or ""):
            log_info("修復スキップ: git プロセス実行中のため index.lock を保持")
            return False
    except Exception as e:
        log_error(f"gitプロセス確認エラー: {e}")
    try:
        # チェック時点から時間が経っている可能性があるため、削除直前にも鮮度ガードを適用
        age = datetime.datetime.now().timestamp() - os.path.getmtime(lock_path)
        if age <= 300:
            log_info("修復スキップ: index.lock が5分以内に更新されたため保持")
            return False
        log_info("修復: index.lock を削除します")
        os.remove(lock_path)
        log_info("修復: index.lock 削除完了")
        return True
    except FileNotFoundError:
        return False
    except Exception as e:
        log_error(f"lock削除失敗: {e}")
    return False


def repair_ollama() -> bool:
    """Ollamaプロセスが死んでいれば再起動"""
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/v1/models", timeout=3)
        if r.status_code < 500:
            return False  # 正常動作中 → 修復不要
    except Exception:
        pass

    log_info("修復: Ollama を起動します")
    autostart_cmd = os.getenv("OLLAMA_AUTOSTART_CMD", "ollama serve")
    try:
        subprocess.Popen(
            autostart_cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time
        wait_sec = int(os.getenv("OLLAMA_AUTOSTART_WAIT_SEC", "15"))
        time.sleep(wait_sec)
        log_info("修復: Ollama 起動完了")
        return True
    except Exception as e:
        log_error(f"Ollama起動失敗: {e}")
    return False


def run_repairs(issues: list[Issue]) -> list[str]:
    """検知した問題に対して修復を実行。実行した修復のリストを返す"""
    repairs = []
    count = 0

    for issue in issues:
        if count >= MAX_REPAIR_PER_RUN:
            log_warn("修復回数上限に達したため残りをスキップ")
            break

        if issue.kind == "hung":
            if repair_hung_task():
                repairs.append(f"ハングしたタスクを停止・再起動 ({issue.detail})")
                count += 1

        elif issue.kind == "git_lock":
            if repair_git_lock():
                repairs.append(f"index.lock を削除 ({issue.detail})")
                count += 1

    # Ollamaの生存確認は常に行う（問題種別に関わらず）
    if repair_ollama():
        repairs.append("Ollama を再起動")

    return repairs


# ---------------------------------------------------------------------------
# 3. Ollama による原因分析
# ---------------------------------------------------------------------------
def _ollama_available() -> bool:
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/v1/models", timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def analyze_with_ollama(issues: list[Issue], repairs: list[str],
                        log_content: str | None) -> str | None:
    """Ollamaでログと問題を分析し、レポートを生成"""
    if not issues:
        return None

    if not _ollama_available():
        log_warn("Ollama が利用不可のため分析をスキップ")
        return None

    # ログは末尾200行に制限（トークン節約）
    log_tail = ""
    if log_content:
        lines = log_content.strip().splitlines()
        log_tail = "\n".join(lines[-200:])

    issues_text = "\n".join(f"- [{i.severity}] {i.kind}: {i.detail}" for i in issues)
    repairs_text = "\n".join(f"- {r}" for r in repairs) if repairs else "なし"

    prompt = textwrap.dedent(f"""\
        あなたはシステム監視の専門家です。以下の情報を分析し、日本語で簡潔なレポートを作成してください。

        ## 検知した問題
        {issues_text}

        ## 実行した自動修復
        {repairs_text}

        ## パイプラインログ（末尾）
        ```
        {log_tail[:4000]}
        ```

        以下の形式で回答してください:
        1. **障害概要**: 何が起きたか（1-2文）
        2. **推定原因**: なぜ起きたか（1-2文）
        3. **影響範囲**: 何に影響があるか
        4. **自動修復の結果**: 修復が成功したか
        5. **推奨アクション**: 手動で対応すべきことがあれば
    """)

    try:
        import requests
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else None
        else:
            log_warn(f"Ollama API エラー: HTTP {resp.status_code}")
    except Exception as e:
        log_warn(f"Ollama 分析失敗: {e}")

    return None


def save_report(issues: list[Issue], repairs: list[str], analysis: str | None):
    """レポートをMarkdownファイルに保存"""
    now = datetime.datetime.now()
    report_path = os.path.join(
        WATCHDOG_LOG_DIR, f"report_{now.strftime('%Y-%m-%d_%H%M%S')}.md"
    )

    lines = [
        f"# Watchdog レポート  - {now.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 検知した問題",
    ]
    if issues:
        for i in issues:
            lines.append(f"- **[{i.severity}]** `{i.kind}`: {i.detail}")
    else:
        lines.append("- 問題なし")

    lines += ["", "## 実行した修復"]
    if repairs:
        for r in repairs:
            lines.append(f"- {r}")
    else:
        lines.append("- なし")

    if analysis:
        lines += ["", "## Ollama 分析", "", analysis]

    lines.append("")
    content = "\n".join(lines)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    log_info(f"レポート保存: {report_path}")
    return report_path


# ---------------------------------------------------------------------------
# ログのクリーンアップ（7日以上前のwatchdogログを削除）
# ---------------------------------------------------------------------------
def cleanup_old_logs():
    cutoff = datetime.datetime.now().timestamp() - 7 * 86400
    for pattern in ["watchdog_*.log", "report_*.md"]:
        for path in glob.glob(os.path.join(WATCHDOG_LOG_DIR, pattern)):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def main():
    log_info("=" * 50)
    log_info("Watchdog 開始")
    log_info("=" * 50)

    # 1. 状態チェック
    log_info("--- 状態チェック ---")
    issues, log_content = run_checks()

    if not issues:
        log_info("問題なし - 正常稼働中")
        cleanup_old_logs()
        log_info("Watchdog 終了 (正常)")
        return 0

    for issue in issues:
        log_warn(f"検知: {issue}")

    # 2. 自動修復
    log_info("--- 自動修復 ---")
    repairs = run_repairs(issues)
    if repairs:
        for r in repairs:
            log_info(f"修復完了: {r}")
    else:
        log_info("自動修復の対象なし")

    # 3. Ollama 分析
    log_info("--- Ollama 分析 ---")
    analysis = analyze_with_ollama(issues, repairs, log_content)
    if analysis:
        log_info("Ollama 分析完了")
    else:
        log_info("Ollama 分析スキップ")

    # 4. レポート保存
    report_path = save_report(issues, repairs, analysis)

    cleanup_old_logs()

    log_info("Watchdog 終了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
