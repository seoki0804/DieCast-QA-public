import pandas as pd
import pytest

from diecast_qa.config import Paths
from diecast_qa.data import PartsBuilder, RawDataLoader, ShotCleaner
from diecast_qa.pipeline import PreprocessPipeline, PreprocessResult


@pytest.fixture(scope="session")
def result() -> PreprocessResult:
    return PreprocessPipeline().run()


@pytest.fixture(scope="session")
def base_parts() -> pd.DataFrame:
    """파생 변수를 붙이기 전의 제품 테이블."""
    shots, _ = ShotCleaner().clean(RawDataLoader(Paths().raw_csv).load())
    return PartsBuilder().build(shots)
