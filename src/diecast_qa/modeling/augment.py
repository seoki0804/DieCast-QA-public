"""불균형 처리와 합성 데이터 생성 (8.1).

모두 imbalanced-learn 샘플러 인터페이스(fit_resample)를 따르므로, 모델 파이프라인 안에서
학습 데이터에만 적용되고 평가 데이터는 실제 값 그대로 쓴다 (3.2). 부족한 클래스마다 가장 많은
클래스 수만큼 채우므로 1단계(불량 여부)와 2단계(유형 5개)에 똑같이 쓸 수 있다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np
import pandas as pd
from imblearn.over_sampling import ADASYN, SMOTE, BorderlineSMOTE, RandomOverSampler
from scipy.stats import norm, rankdata
from sklearn.base import BaseEstimator

from diecast_qa.config import SEED


class ClassBalancer(BaseEstimator, ABC):
    """클래스마다 부족한 행 수만큼 generate로 새 행을 만들어 붙인다."""

    def __init__(self, random_state: int = SEED) -> None:
        self.random_state = random_state

    def fit_resample(self, X: pd.DataFrame, y) -> tuple[pd.DataFrame, np.ndarray]:
        X = pd.DataFrame(X).reset_index(drop=True)
        y = np.asarray(y)
        rng = np.random.default_rng(self.random_state)
        self.prepare(X)
        counts = pd.Series(y).value_counts()
        frames, labels = [X], [y]
        for cls, n in counts.items():
            missing = counts.max() - n
            if missing > 0:
                new = self.generate(X[y == cls].reset_index(drop=True), missing, rng)
                frames.append(new[X.columns])
                labels.append(np.full(missing, cls))
        return pd.concat(frames, ignore_index=True), np.concatenate(labels)

    def prepare(self, X: pd.DataFrame) -> None:
        """학습 데이터 전체로 계산할 값이 있으면 여기서 (예: 열별 표준편차)."""

    @abstractmethod
    def generate(self, rows: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
        """같은 클래스의 실제 행(rows)을 보고 n개의 새 행을 만든다."""


class NoiseJitter(ClassBalancer):
    """실제 행을 복원 추출하고, columns 열에 (학습 데이터 표준편차 × scale)의 정규 잡음을 더한다.

    columns=None이면 모든 열. 8.1 원인 진단에서는 shot 번호만 / 공정 변수만 바꿔 본다.
    """

    def __init__(
        self, scale: float = 0.05, columns: Sequence[str] | None = None, random_state: int = SEED
    ) -> None:
        super().__init__(random_state)
        self.scale, self.columns = scale, columns

    def prepare(self, X: pd.DataFrame) -> None:
        self.sd_ = X.std()

    def generate(self, rows, n, rng):
        out = rows.iloc[rng.integers(0, len(rows), n)].reset_index(drop=True)
        cols = list(self.columns) if self.columns is not None else list(rows.columns)
        noise = rng.normal(size=(n, len(cols))) * (self.sd_[cols].to_numpy() * self.scale)
        out[cols] = out[cols].to_numpy(float) + noise
        return out


class GaussianCopulaSampler(ClassBalancer):
    """열마다 경험적 분포를 정규 점수로 바꿔 열 사이 상관을 정규 분포로 잡고, 표본을 다시
    각 열의 경험적 분위수로 되돌린다. 값이 하나뿐인 열은 그 값을 그대로 쓴다."""

    def generate(self, rows, n, rng):
        values = rows.to_numpy(float)
        varying = np.ptp(values, axis=0) > 0
        out = np.tile(values[0], (n, 1))
        if varying.any():
            v = values[:, varying]
            z = norm.ppf((rankdata(v, axis=0) - 0.5) / len(v))
            corr = np.atleast_2d(np.corrcoef(z, rowvar=False))
            sample = rng.multivariate_normal(np.zeros(len(corr)), corr, size=n, method="eigh")
            u = norm.cdf(sample)
            out[:, varying] = np.column_stack(
                [np.quantile(v[:, j], u[:, j]) for j in range(v.shape[1])]
            )
        return pd.DataFrame(out, columns=rows.columns)


class CTGANSampler(ClassBalancer):
    """조건부 GAN(CTGAN)으로 행을 만든다. 행이 min_rows보다 적은 클래스는 학습이 불안정하므로
    복원 추출로 대신한다. discrete 열은 범주형으로 다룬다."""

    def __init__(
        self, epochs: int = 150, discrete: Sequence[str] = ("Product_Type", "Cavity"),
        min_rows: int = 30, random_state: int = SEED,
    ) -> None:  # fmt: skip
        super().__init__(random_state)
        self.epochs, self.discrete, self.min_rows = epochs, discrete, min_rows

    def generate(self, rows, n, rng):
        if len(rows) < self.min_rows:
            return rows.iloc[rng.integers(0, len(rows), n)].reset_index(drop=True)
        # PyTorch는 무거워서 CTGAN을 실제로 쓸 때만 불러온다
        import torch
        from ctgan import CTGAN

        torch.manual_seed(self.random_state)
        constant = [c for c in rows.columns if rows[c].nunique() == 1]
        data = rows.drop(columns=constant)
        model = CTGAN(epochs=self.epochs, verbose=False)
        model.set_random_state(self.random_state)
        model.fit(data, discrete_columns=[c for c in self.discrete if c in data.columns])
        out = model.sample(n)
        for c in constant:
            out[c] = rows[c].iloc[0]
        return out


class Snapped(ClassBalancer):
    """다른 생성기가 만든 값을 열마다 같은 클래스의 실제 값 중 가장 가까운 값으로 맞춘다.

    8.1 원인 진단: 실제로 존재하지 않는 값을 만든 것이 문제인지 확인한다.
    """

    def __init__(self, base: ClassBalancer, random_state: int = SEED) -> None:
        super().__init__(random_state)
        self.base = base

    def prepare(self, X):
        self.base.prepare(X)

    def generate(self, rows, n, rng):
        out = self.base.generate(rows, n, rng)
        for c in rows.columns:
            grid = np.unique(rows[c].to_numpy(float))
            gap = np.abs(out[c].to_numpy(float)[:, None] - grid[None, :])
            out[c] = grid[gap.argmin(axis=1)]
        return out


class AdaptiveSMOTE(SMOTE):
    """가장 작은 클래스 크기에 맞춰 k_neighbors를 줄이는 SMOTE (2단계 학습 fold에 아주 작은 유형이
    있을 때 오류 대신 동작하게 한다)."""

    def fit_resample(self, X, y):
        smallest = pd.Series(np.asarray(y)).value_counts().min()
        if smallest < 2:
            return RandomOverSampler(random_state=self.random_state).fit_resample(X, y)
        self.k_neighbors = min(5, smallest - 1)
        return super().fit_resample(X, y)


SAMPLERS = {
    "ros": lambda: RandomOverSampler(random_state=SEED),
    "smote": lambda: AdaptiveSMOTE(random_state=SEED),
    "bsmote": lambda: BorderlineSMOTE(random_state=SEED),
    "adasyn": lambda: ADASYN(random_state=SEED),
    "noise": lambda: NoiseJitter(),
    "copula": lambda: GaussianCopulaSampler(),
    "ctgan": lambda: CTGANSampler(),
}
