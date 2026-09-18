from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.integrations.vision import VisionGateway


def _gateway(settings, tmp_path, handler):
    configured = replace(settings, vision_api_base="https://vision.example/v1", vision_api_key="secret", vision_model="vision-model")
    image = tmp_path / "leaf.png"
    image.write_bytes(b"bounded-image")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return VisionGateway(configured, client), image, client


def test_vision_gateway_returns_observation_without_diagnosis(settings, tmp_path):
    def handler(request):
        assert "data:image/png;base64," in request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"crop":"水稻","plantParts":["叶片"],"symptoms":["梭形病斑"],"qualityWarnings":[]}'}}]})

    gateway, image, client = _gateway(settings, tmp_path, handler)
    try:
        result = gateway.analyze(image, "水稻")
        assert result.crop == "水稻"
        assert result.symptoms == ["梭形病斑"]
    finally:
        client.close()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_vision_gateway_surfaces_provider_errors(settings, tmp_path, status):
    gateway, image, client = _gateway(settings, tmp_path, lambda _: httpx.Response(status))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            gateway.analyze(image)
    finally:
        client.close()
