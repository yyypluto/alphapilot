import notifications


def test_send_feishu_alert_no_webhook(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK", raising=False)
    assert notifications.send_feishu_alert("t", "c") is False


def test_send_feishu_alert_success(monkeypatch):
    class _Resp:
        status_code = 200

    def _fake_post(url, json=None, timeout=None):
        assert url == "https://example.com/webhook"
        assert json["msg_type"] == "text"
        assert "AlphaPilot" in json["content"]["text"]
        return _Resp()

    monkeypatch.setenv("FEISHU_WEBHOOK", "https://example.com/webhook")
    monkeypatch.setattr(notifications.requests, "post", _fake_post)

    assert notifications.send_feishu_alert("hello", "world") is True
