"""
核心基础模块单元测试 — ScalabilityProfile
覆盖: 各规模配置/边界文件数/检测逻辑
"""
import pytest
import os
import tempfile
from pathlib import Path

from app.core.scalability_profile import ScalabilityProfile


def _create_repo(tmp_path, num_files, lines_per_file=10):
    for i in range(num_files):
        f = tmp_path / f"file_{i}.py"
        f.write_text("\n".join(["x = 1"] * lines_per_file))
    return str(tmp_path)


class TestScalabilityProfileDetect:
    def test_small_project(self, tmp_path):
        _create_repo(tmp_path, 5)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_profile") == "SMALL"

    def test_medium_project(self, tmp_path):
        _create_repo(tmp_path, 50)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_profile") == "MEDIUM"

    def test_large_project(self, tmp_path):
        _create_repo(tmp_path, 500)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_profile") == "LARGE"

    def test_xlarge_project(self, tmp_path):
        _create_repo(tmp_path, 2500)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_profile") == "XLARGE"

    def test_empty_project(self, tmp_path):
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_profile") is not None


class TestScalabilityProfileLLMConfig:
    def test_small_has_llm_config(self, tmp_path):
        _create_repo(tmp_path, 5)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert "llm_max_qps" in profile
        assert "llm_max_concurrent" in profile

    def test_small_limiter_values(self, tmp_path):
        _create_repo(tmp_path, 5)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile["llm_max_qps"] == 5.0
        assert profile["llm_max_concurrent"] == 3

    def test_medium_limiter_values(self, tmp_path):
        _create_repo(tmp_path, 50)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile["llm_max_qps"] == 3.0
        assert profile["llm_max_concurrent"] == 3

    def test_large_limiter_values(self, tmp_path):
        _create_repo(tmp_path, 500)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile["llm_max_qps"] == 3.0
        assert profile["llm_max_concurrent"] == 5

    def test_xlarge_limiter_values(self, tmp_path):
        _create_repo(tmp_path, 2500)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile["llm_max_qps"] == 2.0
        assert profile["llm_max_concurrent"] == 3


class TestScalabilityProfileFeatures:
    def test_small_enables_incremental(self, tmp_path):
        _create_repo(tmp_path, 5)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("enable_incremental") is True

    def test_medium_enables_incremental(self, tmp_path):
        _create_repo(tmp_path, 50)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("enable_incremental") is True

    def test_file_count_and_lines(self, tmp_path):
        _create_repo(tmp_path, 10, lines_per_file=5)
        profile = ScalabilityProfile.detect(str(tmp_path))
        assert profile.get("_file_count", 0) >= 10
        assert profile.get("_total_lines", 0) >= 50
