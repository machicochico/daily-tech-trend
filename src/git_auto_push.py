"""
git add / commit / push を自動実行し、push失敗時にリカバリする。

リカバリ対象:
  - non-fast-forward (リモートが先行) → git pull --rebase → 再push
  - rebase中のコンフリクト → docs/ はローカル優先、ソースコードは安全のため中止

対象は docs/ のみ（data/state.sqlite は .gitignore 準拠で git 管理外）。

使い方:
  python src/git_auto_push.py [--message "commit msg"] [--max-retry 2]
"""

import argparse
import io
import os
import subprocess
import sys

# Windows環境での文字化け防止
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess:
    """git コマンドを実行して結果を返す（shell 非経由・引数はリスト渡し）。"""
    r = subprocess.run(cmd, shell=False, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd={cmd!r} rc={r.returncode}\n{r.stderr.strip()}")
    return r


def has_staged_changes() -> bool:
    return run(["git", "diff", "--cached", "--quiet"]).returncode == 1


def git_add_and_commit(message: str) -> bool:
    """docs/ を add して commit する。変更なしなら False。"""
    run(["git", "add", "docs"], check=True)
    if not has_staged_changes():
        print("[git_auto_push] 変更なし。コミットをスキップ。")
        return False
    run(["git", "commit", "-m", message], check=True)
    print("[git_auto_push] コミット完了。")
    return True


def resolve_rebase_conflicts() -> bool:
    """rebase中のコンフリクトを自動解決する。解決できなければ False。"""
    r = run(["git", "diff", "--name-only", "--diff-filter=U"])
    conflicted = [f.strip() for f in r.stdout.splitlines() if f.strip()]
    if not conflicted:
        return True

    print(f"[git_auto_push] コンフリクト検出: {conflicted}")

    for path in conflicted:
        if path.startswith("docs/"):
            # 生成ファイル → ローカル(自分のコミット)側を採用
            # rebase中は theirs = 自分のコミット
            run(["git", "checkout", "--theirs", "--", path], check=True)
            run(["git", "add", "--", path], check=True)
            print(f"[git_auto_push] コンフリクト解決 (ローカル優先): {path}")
        else:
            # src/ 等のソースコード → 安全のため abort
            print(f"[git_auto_push] ソースコードのコンフリクトは自動解決不可: {path}")
            return False

    return True


def do_rebase_continue() -> bool:
    """rebase --continue を繰り返し、全ステップのコンフリクトを解決する。"""
    max_steps = 50  # 無限ループ防止
    for _ in range(max_steps):
        r = run(["git", "rebase", "--continue"])
        if r.returncode == 0:
            print("[git_auto_push] rebase 完了。")
            return True
        # まだコンフリクトがあるか確認
        if not resolve_rebase_conflicts():
            run(["git", "rebase", "--abort"])
            print("[git_auto_push] rebase を中止しました。")
            return False
    run(["git", "rebase", "--abort"])
    print("[git_auto_push] rebase ステップ上限到達。中止しました。")
    return False


def pull_rebase() -> bool:
    """git pull --rebase を実行し、コンフリクトがあれば自動解決を試みる。"""
    print("[git_auto_push] git pull --rebase を実行中...")
    r = run(["git", "pull", "--rebase", "origin", "main"])
    if r.returncode == 0:
        print("[git_auto_push] pull --rebase 成功。")
        return True

    # コンフリクト発生 → 自動解決を試行
    if "CONFLICT" in r.stdout or "CONFLICT" in r.stderr:
        print("[git_auto_push] rebase 中にコンフリクト発生。自動解決を試行...")
        if not resolve_rebase_conflicts():
            return False
        return do_rebase_continue()

    # その他のエラー
    print(f"[git_auto_push] pull --rebase 失敗:\n{r.stderr.strip()}")
    return False


def push_with_retry(max_retry: int = 2) -> bool:
    """push を試行し、non-fast-forward なら pull --rebase して再試行する。"""
    for attempt in range(1, max_retry + 2):
        print(f"[git_auto_push] push 試行 {attempt}...")
        r = run(["git", "push", "origin", "main"])
        if r.returncode == 0:
            print("[git_auto_push] push 成功。")
            return True

        # non-fast-forward 以外のエラーはリトライしない
        if "non-fast-forward" not in r.stderr and "fetch first" not in r.stderr:
            print(f"[git_auto_push] push 失敗 (リカバリ不可):\n{r.stderr.strip()}")
            return False

        if attempt > max_retry:
            print("[git_auto_push] リトライ上限到達。push 失敗。")
            return False

        print("[git_auto_push] non-fast-forward 検出。リカバリ開始...")
        if not pull_rebase():
            return False

    return False


def main():
    parser = argparse.ArgumentParser(description="git auto push with recovery")
    parser.add_argument(
        "--message", "-m",
        default="daily update (local LLM)",
        help="コミットメッセージ",
    )
    parser.add_argument(
        "--max-retry",
        type=int,
        default=2,
        help="push失敗時の最大リトライ回数 (default: 2)",
    )
    args = parser.parse_args()

    # add & commit
    committed = git_add_and_commit(args.message)
    if not committed:
        return 0

    # push (リトライ付き)
    if push_with_retry(max_retry=args.max_retry):
        return 0

    print("[git_auto_push] 最終的にpushに失敗しました。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
