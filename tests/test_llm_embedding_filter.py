"""埋め込み専用モデルがチャット完了候補から除外されることを検証する。

F2 修正: post_ollama のフォールバックが bge-m3 / nomic-embed-text を試して 400 を
連発し、1回の verify に20分かかっていた問題への防御テスト。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm_insights_api as llm


class TestIsEmbeddingModel:
    """名前パターンによる埋め込みモデル判定"""

    def test_bge_family_detected(self):
        assert llm._is_embedding_model("bge-m3:latest")
        assert llm._is_embedding_model("bge-large:latest")
        assert llm._is_embedding_model("bge-small:latest")

    def test_nomic_embed_detected(self):
        assert llm._is_embedding_model("nomic-embed-text:latest")

    def test_generic_embed_keyword_detected(self):
        assert llm._is_embedding_model("some-embed:latest")
        assert llm._is_embedding_model("text-embedding-3-small")
        assert llm._is_embedding_model("e5-mistral:latest")
        assert llm._is_embedding_model("gte-large:latest")

    def test_chat_models_not_detected(self):
        assert not llm._is_embedding_model("gpt-oss:20b")
        assert not llm._is_embedding_model("qwen3:30b-a3b")
        assert not llm._is_embedding_model("llama3:8b")
        assert not llm._is_embedding_model("second_constantine/gpt-oss-u:20b")

    def test_empty_input_not_detected(self):
        assert not llm._is_embedding_model("")
        assert not llm._is_embedding_model(None)


class TestPickModelCandidatesFiltersEmbeddings:
    """_pick_model_candidates が埋め込みモデルを自動候補から除外することを検証"""

    def setup_method(self):
        # グローバル状態リセット
        llm._SELECTED_MODEL = None
        llm._FAILED_MODELS = set()

    def test_embeddings_excluded_from_auto_candidates(self, monkeypatch):
        # Ollama に並ぶモデル全種を返す
        monkeypatch.setattr(llm, "_available_models", lambda timeout=4.0: [
            "bge-m3:latest",
            "nomic-embed-text:latest",
            "gpt-oss:20b",
            "qwen3:30b-a3b",
        ])
        monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:20b")
        monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
        candidates = llm._pick_model_candidates()
        # 埋め込みモデルは候補から外れる
        assert "bge-m3:latest" not in candidates
        assert "nomic-embed-text:latest" not in candidates
        # チャットモデルは候補に残る
        assert "gpt-oss:20b" in candidates
        assert "qwen3:30b-a3b" in candidates
        # primary が先頭
        assert candidates[0] == "gpt-oss:20b"

    def test_pinned_model_respected_even_if_looks_like_embed(self, monkeypatch):
        # ユーザーが明示的に bge-m3 を primary 指定した場合は弾かない
        # （仕様: pinned はユーザー意図を尊重）
        monkeypatch.setattr(llm, "_available_models", lambda timeout=4.0: [
            "bge-m3:latest",
            "gpt-oss:20b",
        ])
        monkeypatch.setenv("OLLAMA_MODEL", "bge-m3:latest")
        monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
        candidates = llm._pick_model_candidates()
        assert "bge-m3:latest" in candidates
        assert candidates[0] == "bge-m3:latest"

    def test_empty_model_list_returns_requested(self, monkeypatch):
        # Ollama API 不通でもプライマリは返す
        monkeypatch.setattr(llm, "_available_models",
                             lambda timeout=4.0: (_ for _ in ()).throw(RuntimeError("api down")))
        monkeypatch.setenv("OLLAMA_MODEL", "gpt-oss:20b")
        monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
        candidates = llm._pick_model_candidates()
        assert "gpt-oss:20b" in candidates
