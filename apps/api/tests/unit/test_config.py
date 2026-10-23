from docmind.core.config import DEV_SECRET, Settings


def test_development_defaults_are_refused_in_production() -> None:
    problems = Settings(app_env="production").production_problems()
    joined = " ".join(problems)
    for expected in ("SESSION_SECRET", "API_KEY_PEPPER", "COOKIE_SECURE", "STORAGE_BACKEND", "QUEUE_BACKEND"):
        assert expected in joined


def test_a_real_production_configuration_passes() -> None:
    settings = Settings(
        app_env="production",
        session_secret="s" * 48,
        api_key_pepper="p" * 48,
        cookie_secure=True,
        cors_origins="https://docmind.example.com",
        storage_backend="s3",
        s3_bucket="docmind-documents",
        queue_backend="sqs",
        sqs_queue_url="https://sqs.us-east-1.amazonaws.com/000000000000/docmind-ingest",
    )
    assert settings.production_problems() == []
    assert settings.cors_origins == ["https://docmind.example.com"]


def test_secrets_must_differ_and_hash_embeddings_are_test_only() -> None:
    settings = Settings(session_secret="x" * 40, api_key_pepper="x" * 40, embeddings_provider="hash")
    problems = " ".join(settings.production_problems())
    assert "must differ" in problems
    assert "tests only" in problems
    assert Settings().session_secret.get_secret_value() == DEV_SECRET


def test_generation_label() -> None:
    assert Settings().generation_label == "extractive"
    assert Settings(llm_provider="ollama", llm_model="qwen3:4b").generation_label == "ollama:qwen3:4b"
