from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.eda.compare import ProcessComparison
from diecast_qa.eda.descriptive import DescriptiveStats
from diecast_qa.eda.pareto import ParetoAnalysis
from diecast_qa.eda.strata import StratifiedRates
from diecast_qa.eda.type_mix import TypeMixAnalysis

DEFAULT_ANALYSES = (
    DescriptiveStats,
    ParetoAnalysis,
    StratifiedRates,
    TypeMixAnalysis,
    ProcessComparison,
)

__all__ = [
    "DEFAULT_ANALYSES",
    "Analysis",
    "AnalysisResult",
    "DescriptiveStats",
    "ParetoAnalysis",
    "ProcessComparison",
    "StratifiedRates",
    "TypeMixAnalysis",
]
