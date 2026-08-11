from app import object_storage


def test_object_storage_defaults_to_database(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setenv("VPROF_ARTIFACT_STORAGE_BACKEND", "auto")
    object_storage._client.cache_clear()
    assert object_storage.configured() is False
    assert object_storage.backend_name() == "database"
    assert object_storage.put("job", "file.bin", b"data") is False


def test_database_backend_overrides_bucket(monkeypatch):
    monkeypatch.setenv("S3_BUCKET", "review-files")
    monkeypatch.setenv("VPROF_ARTIFACT_STORAGE_BACKEND", "db")
    object_storage._client.cache_clear()
    assert object_storage.configured() is False


def test_object_keys_are_namespaced_and_sanitised(monkeypatch):
    monkeypatch.setenv("S3_PREFIX", "V Professor")
    assert object_storage._object_key("job:123", "checkpoints/a b.json") == (
        "V-Professor/job-123/checkpoints/a-b.json"
    )
