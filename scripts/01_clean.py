"""1단계: 원본 CSV → data/processed/parts.csv, results/preprocess_report.json (기획서 3장)."""

from diecast_qa.pipeline import PreprocessPipeline


def main() -> None:
    pipeline = PreprocessPipeline()
    result = pipeline.run()
    pipeline.save(result)

    parts = result.parts
    print(result.report.summary())
    print(f"제품 {len(parts):,}개, 불량 {parts['defect'].sum():,}개 ({parts['defect'].mean():.1%})")
    print("2단계 클래스 수", parts.loc[parts["defect"] == 1, "type5"].value_counts().to_dict())
    print(f"저장: {pipeline.paths.parts_csv}")


if __name__ == "__main__":
    main()
