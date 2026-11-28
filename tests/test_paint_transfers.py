"""Exercise the pinned studio runner's adapters without allocating CUDA tensors."""
import ast
import hashlib
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "workflows/texture/hunyuan3d21/run_hy3d21_studio.py"


def runner_function(name):
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = dict(hashlib=hashlib, inspect=inspect, textwrap=textwrap)
    exec(compile(ast.Module([fn], []), str(RUNNER), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("grouped,round_trips", [(False, 3), (True, 1)])
def test_encodes_preserve_order_and_restore_before_denoising(grouped, round_trips):
    moves, calls = [], []
    def encode(value):
        assert moves[-1] == "cpu"
        calls.append(value)
        return value

    def denoise():
        assert moves[-1] == "cuda"
        return tuple(calls)

    pipeline = SimpleNamespace(unet=SimpleNamespace(to=moves.append), encode_images=encode, denoise=denoise)
    empty_cache = Mock()
    restore = runner_function("offload_for_encodes")(pipeline, "cuda", empty_cache, grouped)
    for value in ["reference", "normal", "position"]:
        assert pipeline.encode_images(value) == value
    assert pipeline.denoise() == ("reference", "normal", "position")
    restore()
    assert moves == ["cpu", "cuda"] * round_trips
    assert empty_cache.call_count == round_trips


def test_failed_group_can_restore_and_start_another_job():
    moves = []
    encoder = Mock(side_effect=[ValueError("bad reference"), "encoded"])
    pipeline = SimpleNamespace(unet=SimpleNamespace(to=moves.append), encode_images=encoder,
                               denoise=Mock())
    restore = runner_function("offload_for_encodes")(pipeline, "cuda", Mock(), True)
    with pytest.raises(ValueError):
        try:
            pipeline.encode_images("bad reference")
        finally:
            restore()
    assert moves == ["cpu", "cuda"]
    assert pipeline.encode_images("next reference") == "encoded"
    pipeline.denoise()
    assert moves == ["cpu", "cuda"] * 2


def test_atlas_patch_refuses_an_unknown_projector():
    with pytest.raises(RuntimeError, match="Unsupported back_project"):
        runner_function("without_unused_atlases")(test_atlas_patch_refuses_an_unknown_projector)


def test_grouped_learned_prompt_tokens_follow_the_weights_to_the_device():
    denoise = Mock()
    pipeline = SimpleNamespace(unet=Mock(), encode_images=Mock(), denoise=denoise)
    runner_function("offload_for_encodes")(pipeline, "cuda", Mock(), True)
    pipeline.encode_images("reference")
    positive, negative = Mock(), Mock()
    pipeline.denoise(prompt_embeds=positive, negative_prompt_embeds=negative)
    positive.to.assert_called_once_with("cuda")
    negative.to.assert_called_once_with("cuda")
    denoise.assert_called_once_with(prompt_embeds=positive.to.return_value, negative_prompt_embeds=negative.to.return_value)
